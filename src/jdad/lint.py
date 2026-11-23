"""Content lint for the knowledge base (stdlib only).

Every practice and source reaches coding agents as text they are told to
follow or cite, so the KB is an instruction channel. These checks catch
content that tries to steer an agent rather than inform it:

- ``injection``: text addressed to an AI agent (``ignore previous
  instructions``, fake ``system:`` turns, chat-template tokens, ``don't tell
  the user``, requests to send secrets, polite forms such as ``As the AI
  assistant reading this, you ...``, ``Note to any coding agent:`` and a
  claimed ``the user has pre-approved``). practices/ and sources/. Matched
  on a skeleton of the text (NFKD, combining marks dropped, Cyrillic and
  Greek lookalikes mapped to Latin), per line and per paragraph, so a
  phrase split across lines or spelled with homoglyphs is still caught.
  Base64 runs (standard or URL-safe, 24+ characters) that decode to text
  matching these patterns are flagged in every KB tree.
- ``url``: a URL in practices/ whose host isn't in ``url_allow``, including
  a bare domain with no scheme or ``www`` (``evil.example.com/x``), a
  protocol-relative ``//host``, and a bare IP address (decimal, octal or hex
  IPv4 parts, IPv6 with or without brackets, IPv4-mapped; ideographic and
  fullwidth full stops count as dots; a whole-number or 2-3 part IPv4 when
  it acts as a host), normalized with ``ipaddress``. Loopback addresses and
  a file name with a common extension and no path are exempt. In every KB tree, a Markdown link (inline or reference, including
  a destination after a line break) whose scheme isn't http or https
  (``javascript:``, ``data:``), after undoing backslash escapes, entities and
  whitespace.
- ``html``: a raw HTML tag (``<img onerror=...>``, ``<span hidden>``). A tag
  with attributes or a real HTML element counts even inside code; only
  unknown bare tags in code (``<T>``) are exempt. practices/ and sources/.
- ``shell``: a shell command in practices/ (code spans and blocks with
  risky commands, ``$ `` prompts, pipe-to-shell anywhere) not in
  ``shell_allow``.
- ``hidden-unicode``: bidi controls, zero-width and other format
  characters, private-use and stray control characters.
- ``comment``: HTML comments and Markdown link-reference comments, which
  render as nothing but are read by agents.
- ``homoglyph``: a word mixing ASCII letters with a non-Latin script, or a
  word of non-ASCII letters that folds to ASCII; in practices/, any
  non-ASCII letter.
- ``symlink``: a symlink anywhere in the KB trees.
- ``encoding``: a file that isn't valid UTF-8.
- ``file-type``: a file in any KB tree that isn't named ``*.md`` (lowercase),
  or a KB directory name that exists as a plain file.
- ``size``: a file over MAX_KB_FILE_BYTES (1 MiB); the server refuses to read it.

Hidden-unicode, comment, homoglyph, symlink, encoding, file-type and size run
on practices/, sources/, skills/ and commands/.

Configuration lives in ``kb-lint.toml`` at the KB root. An exception names
the check, the path and the SHA-256 of the exact offending line, so editing
that line voids it::

    url_allow = ["docs.example.com"]
    shell_allow = ["uv"]

    [[allow]]
    check = "injection"
    path = "sources/2027-01-01-prompt-injection-talk.md"
    sha256 = "<sha256 of the line>"
    reason = "the talk quotes an injection string as an example"
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import ipaddress
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from jdad.kb import MAX_KB_FILE_BYTES

INSTRUCTION_DIRS = ("practices", "sources")
ALL_DIRS = ("practices", "sources", "skills", "commands")
CONFIG_NAME = "kb-lint.toml"

_INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE), why)
    for pattern, why in (
        (
            (r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(instructions?|rules|guidelines|"
            r"guidance|directions?|prompts?|directives|the above|everything above)\b"),
            "tells the reader to drop its instructions",
        ),
        (
            (r"\b(ignore|disregard|forget|override|drop|discard|abandon|bypass)\b[^.\n]{0,30}"
            r"\b(previous|prior|earlier|above|preceding|original|initial|existing)\b[^.\n]{0,20}"
            r"\b(context|constraints|polic(y|ies)|commands|orders|messages|training|programming)\b"),
            "tells the reader to drop what it was told before",
        ),
        (r"\b(system|developer)\s+(prompt|message)\b", "refers to the agent's system or developer prompt"),
        (r"\byou\s+are\s+(now|no\s+longer)\b", "tries to reassign the agent's role"),
        (r"\b(new|updated|real|hidden|secret)\s+instructions\b", "claims to carry new instructions"),
        (
            r"\b(do\s+not|don't|never)\s+(tell|inform|show|mention\s+(this\s+)?to|alert)\s+the\s+user\b",
            "asks the agent to hide something from the user",
        ),
        (r"<\|?\s*(im_start|im_end|endoftext|system|assistant)\s*\|?>", "contains a chat-template token"),
        (r"^\s*(system|assistant|developer)\s*:", "imitates a chat turn"),
        (r"^\s*(human|user)\s*:\s*\S", "imitates a chat turn"),
        (
            (r"\b(send|post|upload|exfiltrate|leak|paste)\b[^.\n]{0,40}\b(tokens?|secrets?|credentials?|"
            r"api[ _-]?keys?|private\s+keys?|passwords?|\.env|environment\s+variables)\b"),
            "asks for secrets to be sent somewhere",
        ),
        (r"\bas\s+an\s+(ai|llm|language\s+model|assistant)\b", "addresses the reader as an AI"),
        # Polite forms (Checker's #27 verdict): "As the AI assistant reading
        # this, you ...", "Note to any coding agent: ...", and a claimed
        # pre-approval. Talking about agents ("the agent should retry") passes.
        (
            (r"\bas\s+(the|an?|any)\s+((ai|llm|coding|language|automated)\s+)?"
            r"(assistant|agent|model|llm|ai)\b[^.\n]{0,60}\byou\b"),
            "addresses the reader as an AI",
        ),
        (
            (r"\b(note|message|reminder|notice|attention|psa)\s+(to|for)\s+((any|all|every|the)\s+)?"
            r"((ai|llm|coding|automated)\s+)?(assistants?|agents?|models?|llms?|ais?)\s*[:,-]"),
            "addresses the reader as an AI",
        ),
        (
            (r"\bthe\s+user\s+(has|had)\s+(already\s+(approved|authori[sz]ed|agreed|consented)|"
            r"pre-?(approved|authori[sz]ed))\b"),
            "claims the user has already granted permission",
        ),
    )
)

# The whole URL token; the host is taken with urlsplit, never by hand, so
# userinfo, '#', '?' and '\\' tricks can't make one host look like another.
# Every occurrence of a scheme starts a URL, wherever it sits (inside a word
# or inside another URL's path), and runs to whitespace; trailing punctuation
# is then trimmed. So "[x](https://ok.example)(https://evil.example)" checks
# both hosts, and stopping at "(" can't make
# "https://ok.example(@evil.example" read as ok.example. Bare "www." needs a
# non-host character before it.
# Zero-width lookahead, so matches may overlap: a URL inside another URL's
# token is still its own match.
_URL_RE = re.compile(r"(?=(https?://\S*|(?<![A-Za-z0-9.-])www\.\S+))", re.IGNORECASE)
_MD_NAME_RE = re.compile(r"[^./][^/]*\.md")
_URL_TRAILING = ".,;:!?'\")]}>*_`"
# Characters with no business in the authority of a URL in a KB rule.
_AUTHORITY_BAD = set("@\\'\"`()[]<>{}|^ ")
_PIPE_TO_SHELL_RE = re.compile(
    r"\b(curl|wget|fetch|iwr|invoke-webrequest)\b[^\n|]*\|\s*(sudo\s+)?(ba|z|da|k)?sh\b|\|\s*(iex|invoke-expression)\b",
    re.IGNORECASE,
)
_RISKY_COMMANDS = frozenset(
    {
        "bash", "chmod", "chown", "curl", "dd", "eval", "exec", "iex", "invoke-expression",
        "mkfs", "nc", "ncat", "netcat", "powershell", "pwsh", "rm", "scp", "sh", "ssh",
        "sudo", "wget", "zsh", "base64", "python", "python3", "node", "perl", "ruby",
    }
)
_FENCE_RE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)")
_SHELL_LANGS = frozenset({"sh", "bash", "zsh", "shell", "console", "shell-session", "powershell", "ps1", "pwsh", "cmd", "bat"})
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_HTML_COMMENT_RE = re.compile(r"<!--")
# A tag name right after "<" (browsers treat "< b" as text). "<https://x>"
# autolinks don't match: the name must be followed by space, "/" or ">".
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^\s/>]*(?=[\s/>]|$)")
# Flagged anywhere, inside code spans and fences too, because this lint's
# idea of "code" can differ from a renderer's (escaped backticks, fences
# with odd info strings): a tag with an attribute, or a real HTML element.
# Only harmless unknown tags in code (`List<String>`, `<T>`) are exempt.
# Browsers accept "/" between attributes (<x/src=a/onerror=b>), and a tag
# can continue on the next line, so a tag name at the end of a line counts.
# Shaped like the HTML tokenizer: after the tag name, whitespace or "/"
# then anything but ">" starts an attribute (whatever its first character).
# CommonMark URI autolinks; in practices/ any scheme but http(s) is a url
# finding. Only <http(s)://...> autolinks are exempt from the tag checks
# (the url check still sees them): an email-shaped or other-scheme
# "autolink" can be a tag (<svg/onload=...@x.example>).
_AUTOLINK_RE = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*>")
_HTTP_AUTOLINK_RE = re.compile(r"<https?://[^\s<>]*>", re.IGNORECASE)
# Tag names, like the tokenizer's, run to the first space, "/" or ">".
_HTML_ATTR_TAG_RE = re.compile(r"<[A-Za-z][^\s/>]*(?:[\s/]+[^\s/>]|[\s/]*$)")
_HTML_ELEMENT_RE = re.compile(
    r"</?(a|abbr|audio|b|base|bdo|blink|br|button|canvas|code|del|details|dialog|div|em|embed|"
    r"font|form|frame|frameset|i|iframe|img|input|ins|label|link|mark|marquee|math|meta|"
    r"noscript|object|option|p|picture|pre|q|s|script|select|slot|small|source|span|strong|"
    r"style|sub|summary|sup|svg|table|td|template|textarea|th|tr|u|video)(?=[\s/>]|$)",
    re.IGNORECASE,
)
# Bare domains (no scheme, no www.) in practices/. Every dotted name counts,
# except a common file extension with no path after it (README.md,
# install.sh, Node.js, uv.lock); with a path (get.sh/start) it counts too.
_BARE_DOMAIN_RE = re.compile(
    r"(?<![\w@./:%-])(?!www\.)((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,24}))(/\S*)?",
    re.IGNORECASE,
)
_FILE_EXTENSIONS = frozenset(
    {
        "md", "markdown", "txt", "rst", "toml", "yaml", "yml", "json", "jsonc", "lock", "cfg", "ini",
        "env", "conf", "py", "pyi", "sh", "bash", "zsh", "ps1", "js", "mjs", "cjs", "ts", "tsx", "jsx",
        "rs", "go", "rb", "java", "kt", "swift", "cpp", "hpp", "cs", "php", "pl", "lua", "sql", "html",
        "htm", "css", "scss", "csv", "log", "xml", "svg", "png", "jpg", "jpeg", "gif", "webp", "avif",
        "pdf", "zip", "gz", "tgz", "tar", "mov", "mp4", "wasm", "so", "dll", "exe", "bin", "whl",
        "service", "socket", "timer", "crt", "key", "pem", "pub", "patch", "diff", "tf", "hcl", "vue",
        "svelte", "astro", "dockerfile", "gitignore", "dockerignore", "example", "sample", "bak",
    }
)
# Cyrillic and Greek letters that render like Latin ones: a subset of
# Unicode's confusables.txt, enough for English prose. Code points rather
# than literals, so this file holds no homoglyphs itself.
_CONFUSABLES = {
    0x0430: "a", 0x0435: "e", 0x043E: "o", 0x0440: "p", 0x0441: "c", 0x0443: "y", 0x0445: "x",
    0x0456: "i", 0x0458: "j", 0x0455: "s", 0x0501: "d", 0x04BB: "h", 0x04CF: "l", 0x051B: "q",
    0x051D: "w", 0x0410: "A", 0x0412: "B", 0x0415: "E", 0x041A: "K", 0x041C: "M", 0x041D: "H",
    0x041E: "O", 0x0420: "P", 0x0421: "C", 0x0422: "T", 0x0425: "X", 0x0406: "I", 0x0408: "J",
    0x0405: "S", 0x03B1: "a", 0x03BF: "o", 0x03C1: "p", 0x03BD: "v", 0x03B9: "i", 0x03BA: "k",
    0x03C4: "t", 0x03C5: "u", 0x0391: "A", 0x0392: "B", 0x0395: "E", 0x0396: "Z", 0x0397: "H",
    0x0399: "I", 0x039A: "K", 0x039C: "M", 0x039D: "N", 0x039F: "O", 0x03A1: "P", 0x03A4: "T",
    0x03A5: "Y", 0x03A7: "X",
    # Latin lookalikes NFKD leaves alone (dotless i, script g, alpha, sharp s)
    0x0131: "i", 0x0237: "j", 0x0261: "g", 0x0251: "a", 0x00DF: "ss",
    # Latin small capitals and IPA letters that read as capitals
    0x1D00: "a", 0x0299: "b", 0x1D04: "c", 0x1D05: "d", 0x1D07: "e", 0xA730: "f", 0x0262: "g",
    0x029C: "h", 0x026A: "i", 0x1D0A: "j", 0x1D0B: "k", 0x029F: "l", 0x1D0D: "m", 0x0274: "n",
    0x1D0F: "o", 0x1D18: "p", 0x0280: "r", 0xA731: "s", 0x1D1B: "t", 0x1D1C: "u", 0x1D20: "v",
    0x1D21: "w", 0x028F: "y", 0x1D22: "z",
    # Armenian
    0x0585: "o", 0x057D: "u", 0x0578: "n", 0x0570: "h", 0x0566: "q", 0x0581: "g", 0x0531: "U",
    # Cherokee capitals
    0x13A0: "D", 0x13A1: "R", 0x13A2: "T", 0x13AA: "A", 0x13AB: "J", 0x13AC: "E", 0x13B3: "W",
    0x13B7: "M", 0x13BB: "H", 0x13C0: "G", 0x13C3: "Z", 0x13DA: "S", 0x13DE: "L", 0x13DF: "C",
    0x13E2: "P", 0x13E6: "K", 0x13F4: "B",
}
_LETTER_RUN_RE = re.compile(r"[^\W\d_]+")
# Markdown link destinations: inline [text](dest) and reference [label]: dest.
# Only http(s) or a relative link (no scheme) is allowed; javascript:, data:,
# vbscript: and the rest are flagged, after undoing entity-encoding and
# stripping whitespace and control characters (browsers ignore them).
# Checked on the whole file, since a destination may follow a line break.
_MD_INLINE_DEST_RE = re.compile(r"\]\(\s*(<[^>\n]*>|[^)\s]+)")
_MD_REF_DEST_RE = re.compile(r"^[ ]{0,3}\[[^\]\n]+\]:[ \t]*(?:\n[ \t]*)?(<[^>\n]*>|\S+)", re.MULTILINE)
_MD_BACKSLASH_ESCAPE_RE = re.compile(r"\\([!-/:-@\[-`{-~])")
_SCHEME_RE = re.compile(r"([a-z][a-z0-9+.-]*):")
# Bare IP addresses in practices: dotted IPv4 (four parts, with an optional
# port and path) and IPv6. Version numbers have fewer parts.
# Candidates are wide (decimal, octal or hex parts; IPv6 with or without
# brackets, IPv4-mapped tails) and each is confirmed with `ipaddress`.
_IPV4_PART = r"(?:0x[0-9a-f]+|\d+)"
_BARE_IPV4_RE = re.compile(rf"(?<![\w.])({_IPV4_PART}(?:\.{_IPV4_PART}){{3}})(?::\d{{1,5}})?(/\S*)?(?!\w|\.\w)", re.IGNORECASE)
_BARE_IPV6_RE = re.compile(r"\[([0-9A-Fa-f:.]+)\]|(?<![\w:.])([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?:\.\d{1,3}){0,3})(?![\w:])")
# Short IPv4 forms inet_aton accepts: a whole number (8+ digits) or 2-3 parts
# whose last part spans the remaining bytes. Counted only where they act as a
# host (a port, a path with a letter, or after '@' or 'host:'), and a dotted
# short form only when its last part is over 255, so 3.12 and 2.1.0 pass.
_SHORT_IPV4_RE = re.compile(
    rf"(?<![\w./])({_IPV4_PART}(?:\.{_IPV4_PART}){{0,2}})(:\d{{2,5}}(?:/\S*)?|/[^\s/]*[a-z]\S*)?(?!\w|\.\w)", re.IGNORECASE
)
# Full stops a browser or resolver reads as '.' (U+FF0E and U+FF61 also fold
# under NFKC; U+3002 doesn't).
_IP_DOTS = str.maketrans({"\u3002": ".", "\uff0e": ".", "\uff61": "."})
_PROTOCOL_RELATIVE_RE = re.compile(r"(?<![:\w/])//([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,24})(/\S*)?", re.IGNORECASE)
# Base64 runs long enough to carry a sentence (standard or URL-safe alphabet).
_BASE64_RE = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{24,}={0,2}")

_MD_COMMENT_RE = re.compile(r"^\s*\[[^\]]*\]:\s*(#|<>)")
# Lines are split on "\n" only (a trailing "\r" is dropped first), so every
# other separator and control character reaches the hidden-character check.
_ALLOWED_CONTROLS = {"\t"}
_HIDDEN_CATEGORIES = {"Cf", "Co", "Cs", "Cc", "Zl", "Zp"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    check: str
    message: str
    text: str = ""

    def format(self) -> str:
        return f"{self.path}:{self.line}: [{self.check}] {self.message}"


@dataclass
class LintConfig:
    url_allow: tuple[str, ...] = ()
    shell_allow: tuple[str, ...] = ()
    allow: tuple[tuple[str, str, str], ...] = ()  # (check, path, sha256)

    @classmethod
    def load(cls, root: Path) -> LintConfig:
        path = root / CONFIG_NAME
        if not path.is_file():
            return cls()
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        unknown = set(data) - {"url_allow", "shell_allow", "allow"}
        if unknown:
            raise ValueError(f"{CONFIG_NAME}: unknown keys {sorted(unknown)}")
        allow = []
        for entry in data.get("allow", []):
            missing = {"check", "path", "sha256", "reason"} - set(entry)
            if missing:
                raise ValueError(f"{CONFIG_NAME}: [[allow]] entry is missing {sorted(missing)}")
            allow.append((entry["check"], entry["path"], entry["sha256"].lower()))
        return cls(
            url_allow=tuple(h.lower() for h in data.get("url_allow", [])),
            shell_allow=tuple(c.lower() for c in data.get("shell_allow", [])),
            allow=tuple(allow),
        )

    def allows(self, finding: Finding) -> bool:
        digest = hashlib.sha256(finding.text.encode("utf-8")).hexdigest()
        return (finding.check, finding.path, digest) in self.allow


def _url_problem(url: str, allowed: tuple[str, ...]) -> str | None:
    """Why this URL isn't allowed in practices/, or None if its host is allowlisted."""
    if "\\" in url:
        return f"URL '{url}' contains a backslash (clients disagree on where its host ends)"
    candidate = url if "://" in url else "https://" + url
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
    except ValueError:
        return f"URL '{url}' can't be parsed"
    bad = sorted(set(parts.netloc) & _AUTHORITY_BAD)
    if bad:
        return f"URL '{url}' has {''.join(bad)!r} in its host part (userinfo or parser tricks)"
    if not host:
        return f"URL '{url}' has no host"
    host = host.rstrip(".")
    if any(host == entry or host.endswith("." + entry) for entry in allowed):
        return None
    return f"URL host '{host}' is not in url_allow ({CONFIG_NAME})"


def _describe_char(ch: str) -> str:
    name = unicodedata.name(ch, "UNNAMED")
    return f"U+{ord(ch):04X} {name}"


def _hidden_chars(line: str) -> list[str]:
    found = []
    for ch in line:
        if ch in _ALLOWED_CONTROLS:
            continue
        category = unicodedata.category(ch)
        if category in _HIDDEN_CATEGORIES or ch == "\u00ad":
            found.append(_describe_char(ch))
    return found


def _shell_findings(rel: str, lines: list[str], allow: tuple[str, ...]) -> list[Finding]:
    findings: list[Finding] = []
    in_fence = False
    fence_is_shell = False
    for number, line in enumerate(lines, start=1):
        fence = _FENCE_RE.match(line)
        if fence:
            if in_fence:
                in_fence = False
            else:
                in_fence = True
                fence_is_shell = fence.group(2).lower() in _SHELL_LANGS
            continue
        if _PIPE_TO_SHELL_RE.search(line):
            findings.append(Finding(rel, number, "shell", "pipes a download into a shell", line))
            continue
        snippets: list[str] = []
        if in_fence:
            snippets.append(line)
            if fence_is_shell and line.strip() and not line.strip().startswith("#"):
                first = line.strip().lstrip("$ ").split()[0].lower() if line.strip().lstrip("$ ") else ""
                if first and first not in allow:
                    findings.append(
                        Finding(rel, number, "shell", f"shell command '{first}' in a shell code block", line)
                    )
                    continue
        else:
            if re.match(r"^\s*\$\s+\S", line):
                snippets.append(line.strip()[1:])
            snippets.extend(_INLINE_CODE_RE.findall(line))
        for snippet in snippets:
            words = {w.lower() for w in re.findall(r"[A-Za-z][\w.-]*", snippet)}
            risky = sorted((words & _RISKY_COMMANDS) - set(allow))
            if risky:
                findings.append(
                    Finding(rel, number, "shell", f"shell command(s) {', '.join(risky)} in code", line)
                )
                break
    return findings


def _skeleton(text: str) -> str:
    """Text as the injection patterns see it: compatibility forms folded,
    combining marks dropped, Cyrillic/Greek lookalikes mapped to Latin."""
    folded = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Mn").translate(_CONFUSABLES)


def _fold_accents(word: str) -> str:
    """NFKD with combining marks dropped, nothing else mapped."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", word) if unicodedata.category(ch) != "Mn")


def _homoglyph_words(line: str, *, ascii_only: bool) -> list[str]:
    """Words that look like English but aren't.

    - Any word mixing ASCII letters with letters from a non-Latin script
      (Cyrillic, Greek, Armenian, Cherokee, fullwidth forms, ...).
    - A word made only of non-ASCII letters that folds to ASCII letters
      (an all-Cyrillic "pop").
    - With ascii_only (practices/), any non-ASCII letter at all: practice
      rules are English, so there's nothing to tell apart from a lookalike.
    """
    words = []
    for match in _LETTER_RUN_RE.finditer(line):
        word = match.group(0)
        non_ascii = [ch for ch in word if not ch.isascii()]
        if not non_ascii:
            continue
        has_ascii = len(non_ascii) < len(word)
        non_latin = any(not unicodedata.name(ch, "").startswith("LATIN ") for ch in non_ascii)
        folded = _skeleton(word)
        # Accented Latin (cafe with an accent) folds to ASCII and is fine; a
        # Latin letter that doesn't fold (dotless i, sharp s) is a lookalike.
        mixed = has_ascii and (non_latin or not _fold_accents(word).isascii())
        # All non-ASCII: a lookalike if it folds to ASCII letters, or if it is
        # all Latin-script letters that accents alone can't fold (small caps).
        all_latin = all(unicodedata.name(ch, "").startswith("LATIN ") for ch in word)
        lookalike = not has_ascii and (
            (folded.isascii() and folded.isalpha()) or (all_latin and not _fold_accents(word).isascii())
        )
        if ascii_only or mixed or lookalike:
            words.append(word)
    return words


def _injection_findings(rel: str, lines: list[str]) -> list[Finding]:
    """Per line, then per paragraph (non-blank lines joined with spaces), so
    "ignore all previous" / "instructions" on two lines is still one phrase."""
    findings: list[Finding] = []
    flagged: set[int] = set()
    skeletons = [_skeleton(line) for line in lines]
    for number, skeleton in enumerate(skeletons, start=1):
        for pattern, why in _INJECTION_PATTERNS:
            if pattern.search(skeleton):
                findings.append(Finding(rel, number, "injection", f"agent-directed text: {why}", lines[number - 1]))
                flagged.add(number)
                break
    start = 0
    while start < len(lines):
        if not skeletons[start].strip():
            start += 1
            continue
        end = start
        while end + 1 < len(lines) and skeletons[end + 1].strip():
            end += 1
        if end > start:
            offsets: list[int] = []
            joined = ""
            for index in range(start, end + 1):
                offsets.append(len(joined))
                joined += skeletons[index].strip() + " "

            def line_at(pos: int, offsets: list[int] = offsets, start: int = start) -> int:
                return start + 1 + max(i for i, off in enumerate(offsets) if off <= pos)

            for pattern, why in _INJECTION_PATTERNS:
                for match in pattern.finditer(joined):
                    first, last = line_at(match.start()), line_at(max(match.end() - 1, match.start()))
                    if last > first and not flagged & set(range(first, last + 1)):
                        findings.append(
                            Finding(rel, first, "injection", f"agent-directed text split across lines {first}-{last}: {why}", lines[first - 1])
                        )
                        flagged.update(range(first, last + 1))
        start = end + 1
    return findings


def _link_scheme_findings(rel: str, text: str, lines: list[str]) -> list[Finding]:
    """Markdown link destinations (inline or reference, on the whole file, so a
    destination after a line break counts) whose scheme isn't http or https.
    Backslash escapes and entities are undone and whitespace and control
    characters dropped first, as a renderer would."""
    findings = []
    matches = [*_MD_INLINE_DEST_RE.finditer(text), *_MD_REF_DEST_RE.finditer(text)]
    for match in sorted(matches, key=lambda m: m.start(1)):
        dest = match.group(1)
        raw = dest[1:-1] if dest.startswith("<") and dest.endswith(">") else dest
        raw = _MD_BACKSLASH_ESCAPE_RE.sub(r"\1", raw)
        clean = "".join(ch for ch in html.unescape(raw) if ch > " " and ch != "\x7f").lower()
        scheme = _SCHEME_RE.match(clean)
        if scheme and scheme.group(1) not in ("http", "https"):
            number = text.count("\n", 0, match.start(1)) + 1
            findings.append(
                Finding(rel, number, "url", f"link with scheme '{scheme.group(1)}:' (only http, https or a relative link)", lines[number - 1])
            )
    return findings


def _ipv4_part(part: str) -> int | None:
    """One inet_aton part: decimal, 0x-hex or 0-prefixed octal."""
    try:
        return int(part, 16) if part.lower().startswith("0x") else int(part, 8) if len(part) > 1 and part.startswith("0") else int(part)
    except ValueError:
        return None


def _ipv4_from_parts(text: str) -> ipaddress.IPv4Address | None:
    """IPv4 the way inet_aton reads it: 1-4 parts, each decimal, 0x-hex or
    0-prefixed octal; every part but the last is one byte, and the last
    fills the remaining bytes."""
    values = [_ipv4_part(part) for part in text.split(".")]
    if None in values:
        return None
    if not 1 <= len(values) <= 4 or any(v > 255 for v in values[:-1]) or values[-1] >= 256 ** (5 - len(values)):
        return None
    number = 0
    for value in values[:-1]:
        number = number * 256 + value
    return ipaddress.IPv4Address(number * 256 ** (5 - len(values)) + values[-1])


def _bare_host_problems(line: str, allowed: tuple[str, ...]) -> list[str]:
    """Bare IP addresses and protocol-relative //host forms in practices/.
    Loopback (127.0.0.0/8, ::1) is exempt: "bind to 127.0.0.1" is advice,
    not a place to send anything."""
    problems = []
    line = unicodedata.normalize("NFKC", line).translate(_IP_DOTS)
    for match in _BARE_IPV4_RE.finditer(line):
        address = _ipv4_from_parts(match.group(1))
        if address and not address.is_loopback:
            rest = match.group(0)[len(match.group(1)):].rstrip(_URL_TRAILING)
            problem = _url_problem(f"{address}{rest}", allowed)
            if problem:
                problems.append(f"bare IP address '{match.group(1)}': {problem}")
    for match in _SHORT_IPV4_RE.finditer(line):
        parts = match.group(1).split(".")
        if len(parts) == 1 and not (parts[0].isdigit() and len(parts[0]) >= 8):
            continue  # small numbers and hex words aren't hosts
        if len(parts) > 1 and (_ipv4_part(parts[-1]) or 0) <= 255:
            continue  # 3.12, 2.1.0: read as versions
        address = _ipv4_from_parts(match.group(1))
        if not address or address.is_loopback:
            continue
        before = line[: match.start()].lower()
        if not (match.group(2) or before.endswith(("@", "host:", "host="))):
            continue
        rest = (match.group(2) or "").rstrip(_URL_TRAILING)
        problem = _url_problem(f"{address}{rest}", allowed)
        if problem:
            problems.append(f"bare IP address '{match.group(1)}' ({address}): {problem}")
    for match in _BARE_IPV6_RE.finditer(line):
        candidate = match.group(1) or match.group(2)
        try:
            address = ipaddress.IPv6Address(candidate)
        except ValueError:
            continue
        if address.is_loopback or (address.ipv4_mapped and address.ipv4_mapped.is_loopback):
            continue
        if f"[{address.compressed}]" not in allowed and address.compressed not in allowed:
            problems.append(f"bare IP address '{candidate}' ({address.compressed}) is not in url_allow ({CONFIG_NAME})")
    for match in _PROTOCOL_RELATIVE_RE.finditer(line):
        problem = _url_problem("https:" + match.group(0).rstrip(_URL_TRAILING), allowed)
        if problem:
            problems.append(f"protocol-relative URL: {problem}")
    return problems


def _base64_injection(text: str) -> str | None:
    """Why a base64 run in `text` decodes to agent-directed text, or None.
    Lenient on purpose: every alignment offset, odd lengths trimmed, bad
    bytes dropped rather than skipping the run."""
    for match in _BASE64_RE.finditer(text):
        run = match.group(0).rstrip("=").replace("-", "+").replace("_", "/")
        for offset in range(4):
            token = run[offset:]
            if len(token) % 4 == 1:
                token = token[:-1]
            try:
                raw = base64.b64decode(token + "=" * (-len(token) % 4), validate=True)
            except (binascii.Error, ValueError):
                continue
            decoded = "".join(ch for ch in raw.decode("utf-8", errors="ignore") if ch.isprintable() or ch == " ")
            skeleton = _skeleton(decoded)
            for pattern, why in _INJECTION_PATTERNS:
                if pattern.search(skeleton):
                    return why
    return None


def _base64_injection_findings(rel: str, lines: list[str]) -> list[Finding]:
    """Per line, then per paragraph with line breaks and indentation removed,
    so a payload split across lines is still decoded."""
    findings: list[Finding] = []
    flagged: set[int] = set()
    for number, line in enumerate(lines, start=1):
        why = _base64_injection(line)
        if why:
            findings.append(Finding(rel, number, "injection", f"base64-encoded agent-directed text: {why}", line))
            flagged.add(number)
    start = 0
    while start < len(lines):
        if not lines[start].strip():
            start += 1
            continue
        end = start
        while end + 1 < len(lines) and lines[end + 1].strip():
            end += 1
        if end > start and not flagged & set(range(start + 1, end + 2)):
            why = _base64_injection("".join(line.strip() for line in lines[start : end + 1]))
            if why:
                findings.append(
                    Finding(rel, start + 1, "injection", f"base64-encoded agent-directed text split across lines {start + 1}-{end + 1}: {why}", lines[start])
                )
        start = end + 1
    return findings


def _bare_domain_problems(line: str, allowed: tuple[str, ...]) -> list[str]:
    problems = []
    for match in _BARE_DOMAIN_RE.finditer(line):
        tld, path = match.group(2).lower(), match.group(3)
        if path or tld not in _FILE_EXTENSIONS:
            problem = _url_problem(match.group(0).rstrip(_URL_TRAILING), allowed)
            if problem:
                problems.append(f"bare domain: {problem}")
    return problems


def lint_file(root: Path, path: Path, config: LintConfig) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    top = rel.split("/", 1)[0]
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        return [Finding(rel, 1, "encoding", f"not valid UTF-8 ({exc.reason} at byte {exc.start})")]
    # Not splitlines(): it also splits on \x0b, \x0c, \x1c-\x1e, \x85, U+2028
    # and U+2029, which would hide exactly the characters checked below.
    lines = [line.removesuffix("\r") for line in text.split("\n")]
    findings: list[Finding] = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        fence = bool(_FENCE_RE.match(line))
        if fence:
            in_fence = not in_fence
        hidden = _hidden_chars(line)
        if hidden:
            findings.append(
                Finding(rel, number, "hidden-unicode", "invisible or bidi character(s): " + ", ".join(hidden), line)
            )
        if _HTML_COMMENT_RE.search(line):
            findings.append(Finding(rel, number, "comment", "HTML comment (renders as nothing; agents still read it)", line))
        elif _MD_COMMENT_RE.match(line):
            findings.append(Finding(rel, number, "comment", "Markdown link-reference comment (renders as nothing)", line))
        lookalikes = _homoglyph_words(line, ascii_only=top == "practices")
        if lookalikes:
            what = "non-ASCII letters in a practice" if top == "practices" else "lookalike letters"
            findings.append(Finding(rel, number, "homoglyph", f"{what}: " + ", ".join(ascii(w) for w in lookalikes), line))
        no_links = _HTTP_AUTOLINK_RE.sub("", line)
        if top in INSTRUCTION_DIRS and (
            _HTML_ATTR_TAG_RE.search(no_links)
            or _HTML_ELEMENT_RE.search(no_links)
            or (not in_fence and not fence and _HTML_TAG_RE.search(_INLINE_CODE_RE.sub("", no_links)))
        ):
            findings.append(Finding(rel, number, "html", "raw HTML tag outside code (can hide text or carry handlers)", line))
        if top == "practices":
            for problem in _bare_host_problems(line, config.url_allow):
                findings.append(Finding(rel, number, "url", problem, line))
            for match in _URL_RE.finditer(line):
                problem = _url_problem(match.group(1).rstrip(_URL_TRAILING), config.url_allow)
                if problem:
                    findings.append(Finding(rel, number, "url", problem, line))
            for problem in _bare_domain_problems(line, config.url_allow):
                findings.append(Finding(rel, number, "url", problem, line))
            for link in _AUTOLINK_RE.finditer(line):
                scheme = link.group(0)[1:].split(":", 1)[0].lower()
                if scheme not in ("http", "https"):
                    findings.append(Finding(rel, number, "url", f"autolink with scheme '{scheme}:' (only http and https)", line))
    # In every KB tree, skills and commands included: they may instruct agents
    # in plain words, but never through a javascript: link or an encoded payload.
    findings.extend(_link_scheme_findings(rel, text, lines))
    findings.extend(_base64_injection_findings(rel, lines))
    if top in INSTRUCTION_DIRS:
        findings.extend(_injection_findings(rel, lines))
    if top == "practices":
        findings.extend(_shell_findings(rel, lines, config.shell_allow))
    return findings


def lint_kb(root: Path) -> list[Finding]:
    """Lint the KB trees under ``root``. Returns findings not covered by an exception."""
    root = root.resolve()
    config = LintConfig.load(root)
    findings: list[Finding] = []
    for name in ALL_DIRS:
        base = root / name
        if base.is_symlink():
            findings.append(Finding(name, 1, "symlink", "the directory itself is a symlink"))
            continue
        if not base.exists():
            continue
        if not base.is_dir():
            findings.append(Finding(name, 1, "file-type", f"{name} exists but isn't a directory"))
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                findings.append(Finding(rel, 1, "symlink", "symlinks are not allowed in the KB"))
                continue
            if not path.is_file():
                continue
            # Content checks run on every Markdown file, whatever the case of
            # its extension, so nothing is skipped silently. Only exact ".md"
            # names are allowed: the server serves <id>.md, and plugin loaders
            # differ on case.
            if path.stat().st_size > MAX_KB_FILE_BYTES:
                findings.append(
                    Finding(rel, 1, "size", f"larger than {MAX_KB_FILE_BYTES} bytes; the server won't serve it")
                )
                continue
            if path.name.lower().endswith(".md"):
                findings.extend(lint_file(root, path, config))
            if not _MD_NAME_RE.fullmatch(path.name):
                findings.append(
                    Finding(rel, 1, "file-type", f"only <name>.md files (lowercase extension, no dotfiles) belong in {name}/")
                )
    return [f for f in findings if not config.allows(f)]
