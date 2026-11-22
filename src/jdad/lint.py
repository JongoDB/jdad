"""Content lint for the knowledge base (stdlib only).

Every practice and source reaches coding agents as text they are told to
follow or cite, so the KB is an instruction channel. These checks catch
content that tries to steer an agent rather than inform it:

- ``injection``: text addressed to an AI agent (``ignore previous
  instructions``, fake ``system:`` turns, chat-template tokens, ``don't tell
  the user``, requests to send secrets). practices/ and sources/.
- ``url``: a URL in practices/ whose host isn't in ``url_allow``.
- ``shell``: a shell command in practices/ (code spans and blocks with
  risky commands, ``$ `` prompts, pipe-to-shell anywhere) not in
  ``shell_allow``.
- ``hidden-unicode``: bidi controls, zero-width and other format
  characters, private-use and stray control characters.
- ``comment``: HTML comments and Markdown link-reference comments, which
  render as nothing but are read by agents.
- ``symlink``: a symlink anywhere in the KB trees.
- ``encoding``: a file that isn't valid UTF-8.

The last four run on practices/, sources/, skills/ and commands/.

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

import hashlib
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

INSTRUCTION_DIRS = ("practices", "sources")
ALL_DIRS = ("practices", "sources", "skills", "commands")
CONFIG_NAME = "kb-lint.toml"

_INJECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE), why)
    for pattern, why in (
        (
            (r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(instructions?|rules|guidelines|"
            r"prompts?|directives|the above|everything above)\b"),
            "tells the reader to drop its instructions",
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
    )
)

_URL_RE = re.compile(r"\b(?:https?://|www\.)([^\s/)>\]'\"`]+)", re.IGNORECASE)
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
_MD_COMMENT_RE = re.compile(r"^\s*\[[^\]]*\]:\s*(#|<>)")
_ALLOWED_CONTROLS = {"\t", "\n", "\r"}


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


def _host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    host = host.lower().split("@")[-1].split(":")[0].rstrip(".")
    return any(host == entry or host.endswith("." + entry) for entry in allowed)


def _describe_char(ch: str) -> str:
    name = unicodedata.name(ch, "UNNAMED")
    return f"U+{ord(ch):04X} {name}"


def _hidden_chars(line: str) -> list[str]:
    found = []
    for ch in line:
        if ch in _ALLOWED_CONTROLS:
            continue
        category = unicodedata.category(ch)
        if category in {"Cf", "Co", "Cs", "Cc"} or ch == "\u00ad":
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


def lint_file(root: Path, path: Path, config: LintConfig) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    top = rel.split("/", 1)[0]
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        return [Finding(rel, 1, "encoding", f"not valid UTF-8 ({exc.reason} at byte {exc.start})")]
    lines = text.splitlines()
    findings: list[Finding] = []
    for number, line in enumerate(lines, start=1):
        hidden = _hidden_chars(line)
        if hidden:
            findings.append(
                Finding(rel, number, "hidden-unicode", "invisible or bidi character(s): " + ", ".join(hidden), line)
            )
        if _HTML_COMMENT_RE.search(line):
            findings.append(Finding(rel, number, "comment", "HTML comment (renders as nothing; agents still read it)", line))
        elif _MD_COMMENT_RE.match(line):
            findings.append(Finding(rel, number, "comment", "Markdown link-reference comment (renders as nothing)", line))
        if top in INSTRUCTION_DIRS:
            for pattern, why in _INJECTION_PATTERNS:
                if pattern.search(line):
                    findings.append(Finding(rel, number, "injection", f"agent-directed text: {why}", line))
                    break
        if top == "practices":
            for match in _URL_RE.finditer(line):
                host = match.group(1)
                if not _host_allowed(host, config.url_allow):
                    findings.append(
                        Finding(rel, number, "url", f"URL host '{host}' is not in url_allow ({CONFIG_NAME})", line)
                    )
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
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                findings.append(Finding(rel, 1, "symlink", "symlinks are not allowed in the KB"))
                continue
            if path.is_file() and path.suffix.lower() == ".md":
                findings.extend(lint_file(root, path, config))
    return [f for f in findings if not config.allows(f)]
