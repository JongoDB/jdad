#!/usr/bin/env python3
"""PreToolUse guard for this repo (AGENTS.md R-sec-2, CLAUDE.md R-cc-5).

Denies, before the tool runs:
- reading or writing secret-shaped files: `.env*`, `*.pem`, `id_*` (SSH keys);
- `rm` with both recursive and force flags (`rm -rf`, `rm -fr`, `rm -r -f`, ...);
- `git push` with `--force`, `-f`, `--force-with-lease` or a `+refspec`.

It repeats the deny rules in .claude/settings.json on purpose: those match
command text, while this scans the command with a small quote-aware
scanner (command substitutions, heredocs, compound commands, `sh -c`,
`eval`, `find -exec`, wrappers) and fails closed when it can't tell (an
unclosed substitution, nesting too deep). It also sees through leading
VAR=value assignments, ( ) subshells, { } groups, if/for/while/case
bodies and wrapper options that take a value (sudo -u USER).

It is not a sandbox, and it does NOT catch (tested as known gaps):
- a command name held in a variable (X=rm; $X -rf build) or an eval of a
  variable's contents;
- code that never appears as shell text: interpreters (python -c
  "shutil.rmtree(...)"), decoded payloads (base64 -d | sh), a script
  written and then run, aliases;
- other destructive commands outside the deny list (find -delete, git
  reset --hard, git clean -fdx);
- Grep or Glob over a whole directory that contains secret files.
Reads the hook's stdin JSON
(tool_name, tool_input); to deny, prints hookSpecificOutput with
permissionDecision "deny". Stdlib only; tests in tests/test_harness.py.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shlex
import sys
from pathlib import PurePath

SECRET_GLOBS = (".env*", "*.pem", "id_*")
# Names a glob is tested against (plus candidates built from the glob's own
# literal text): could the shell expand it to a secret-shaped file?
SECRET_SAMPLES = (
    ".env", ".env.local", ".env.production", ".envrc", "x.pem", "key.pem",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "id_ed25519.pub", "id_rsa-cert.pub",
)
PATH_TOOLS = {"Read", "Edit", "Write", "NotebookEdit", "MultiEdit"}
SEARCH_TOOLS = {"Grep", "Glob"}
OPERATOR_CHARS = ";&|\n"
# Subshell and grouping parens also end a simple command. ($(...), <(...),
# >(...) and ((...)) are taken out by scan() before splitting.)
SPLIT_CHARS = OPERATOR_CHARS + "()"
# Words that can come before the real program in a simple command.
KEYWORDS = {"if", "then", "elif", "else", "fi", "do", "done", "while", "until", "for", "select",
            "case", "esac", "in", "function", "{", "}", "!", "coproc"}
ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=.*", re.DOTALL)
WRAPPERS = {"sudo", "env", "command", "builtin", "nohup", "nice", "time", "timeout", "stdbuf", "xargs", "exec"}
# Wrapper options that take a separate value ("sudo -u USER cmd"): skip both words.
WRAPPER_VALUE_OPTIONS = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group", "--chdir", "--host", "--prompt"},
    "env": {"-u", "-C", "--unset", "--chdir"},
    "nice": {"-n", "--adjustment"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
    # Not -i, -l, -e: their (optional) value is always attached ("-i{}").
    "xargs": {"-I", "-J", "-R", "-S", "-n", "-P", "-L", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--delimiter", "--arg-file"},
}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Programs that only print names: a glob argument to them reads nothing.
LISTERS = {"ls", "find", "echo", "printf", "stat", "du", "tree"}
FIND_ACTIONS = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"}
# Free text, not file access: the value of these options, and what
# echo/printf print (apart from a redirect target).
MESSAGE_OPTIONS = {"git": {"-m", "--message"}, "gh": {"-b", "--body", "-t", "--title", "-n", "--notes"}}
TEXT_PROGRAMS = {"echo", "printf"}
MAX_DEPTH = 4
# Glob characters inside quotes are literal; the scanner swaps them for
# these markers so only unquoted ones count as globs.
QUOTED_GLOB = {"*": "\x01", "?": "\x02", "[": "\x03"}
_RESTORE = str.maketrans({v: k for k, v in QUOTED_GLOB.items()})


def restore(text: str) -> str:
    return text.translate(_RESTORE)


REDIRECTS = (">", ">>", "<", "1>", "2>", "&>", ">|")
WORD_START = " \t\n;|&("


def _word_start(command: str, i: int) -> bool:
    """Does command[i] start a word? Not if the separator before it is
    escaped (an escaped space, or a backslash-newline continuation)."""
    if i == 0:
        return True
    if command[i - 1] not in WORD_START:
        return False
    backslashes, j = 0, i - 2
    while j >= 0 and command[j] == "\\":
        backslashes, j = backslashes + 1, j - 1
    return backslashes % 2 == 0


class Unclear(Exception):
    """The scanner can't tell what the shell would run: deny."""


# ---- quote-aware scanning --------------------------------------------------


def _match_paren(text: str, start: int) -> int:
    """Index of the ')' closing the '(' at text[start], aware of quotes."""
    depth, i, quote = 0, start, None
    while i < len(text):
        c = text[i]
        if quote == "'":
            if c == "'":
                quote = None
        elif c == "\\":
            i += 1
        elif quote == '"':
            if c == '"':
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise Unclear("unclosed substitution")


def _match_backtick(text: str, start: int) -> int:
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "`":
            return i
        i += 1
    raise Unclear("unclosed backtick")


def _body_substitutions(body: str) -> list[str]:
    """$(...) and `...` in an unquoted heredoc body (quotes are literal there)."""
    inner, p = [], 0
    while p < len(body):
        if body[p] == "\\":
            p += 2
        elif body.startswith("$(", p):
            end = _match_paren(body, p + 1)
            inner.append(body[p + 2:end])
            p = end + 1
        elif body[p] == "`":
            end = _match_backtick(body, p)
            inner.append(body[p + 1:end])
            p = end + 1
        else:
            p += 1
    return inner


def scan(command: str) -> tuple[str, list[str]]:
    """Return (command with heredoc bodies removed, inner commands to check).

    Inner commands are every $(...), <(...), >(...) and `...` the shell
    would run: outside single quotes, unescaped, including inside unquoted
    heredoc bodies. A heredoc body with a quoted delimiter (<<'EOF') is
    literal data and is skipped. A backslash escapes only outside single
    quotes.
    """
    out: list[str] = []
    inner: list[str] = []
    i, quote, n = 0, None, len(command)
    while i < n:
        c = command[i]
        if quote == "'":
            out.append(QUOTED_GLOB.get(c, c))
            quote = None if c == "'" else quote
            i += 1
        elif c == "\\":
            out.append(command[i:i + 2])
            i += 2
        elif c == "$" and command.startswith("(", i + 1):
            end = _match_paren(command, i + 1)
            inner.append(command[i + 2:end])
            out.append(command[i:end + 1])
            i = end + 1
        elif c == "`":
            end = _match_backtick(command, i)
            inner.append(command[i + 1:end])
            out.append(command[i:end + 1])
            i = end + 1
        elif quote == '"':
            out.append(QUOTED_GLOB.get(c, c))
            quote = None if c == '"' else quote
            i += 1
        elif c in "<>" and command.startswith("(", i + 1):
            end = _match_paren(command, i + 1)
            inner.append(command[i + 2:end])
            out.append(command[i:end + 1])
            i = end + 1
        elif c in "'\"":
            quote = c
            out.append(c)
            i += 1
        elif c == "#" and _word_start(command, i):
            # A comment runs to the end of the line; nothing in it is run,
            # and a "<<" in it doesn't start a heredoc.
            end = command.find("\n", i)
            i = n if end < 0 else end
        elif command.startswith("((", i) and _word_start(command, i):
            # Arithmetic: "<<" is a shift here, not a heredoc.
            end = _match_paren(command, i)
            inner.extend(_body_substitutions(command[i + 2:end]))
            out.append(command[i:end + 1])
            i = end + 1
        elif command.startswith("<<<", i):
            out.append("<<<")
            i += 3
        elif command.startswith("<<", i):
            i = _heredoc(command, i, out, inner)
        else:
            out.append(c)
            i += 1
    if quote is not None:
        raise Unclear("unclosed quote")
    return "".join(out), inner


def _delimiter(command: str, i: int) -> tuple[str, bool, int]:
    """Parse a heredoc delimiter word at command[i:]: (word, quoted, end).
    Any quoting anywhere in the word makes the body literal, as in bash."""
    n, word, quoted = len(command), [], False
    while i < n and command[i] not in " \t\n;|&<>()":
        c = command[i]
        if c == "'":
            end = command.find("'", i + 1)
            if end < 0:
                raise Unclear("unclosed quote in a heredoc delimiter")
            word.append(command[i + 1:end])
            quoted, i = True, end + 1
        elif c == '"':
            j = i + 1
            while j < n and command[j] != '"':
                j += 2 if command[j] == "\\" else 1
            if j >= n:
                raise Unclear("unclosed quote in a heredoc delimiter")
            if "\\" in command[i + 1:j]:
                raise Unclear("backslash in a quoted heredoc delimiter")
            word.append(command[i + 1:j])
            quoted, i = True, j + 1
        elif c == "\\":
            word.append(command[i + 1:i + 2])
            quoted, i = True, i + 2
        elif c in "$`":
            raise Unclear("expansion in a heredoc delimiter")
        else:
            word.append(c)
            i += 1
    if not word:
        raise Unclear("heredoc with no delimiter")
    return "".join(word), quoted, i


def _heredoc(command: str, i: int, out: list[str], inner: list[str]) -> int:
    start = i + 2
    dash = command.startswith("-", start)
    start += 1 if dash else 0
    while start < len(command) and command[start] in " \t":
        start += 1
    delimiter, quoted, word_end = _delimiter(command, start)
    out.append(command[i:word_end])
    line_end = command.find("\n", word_end)
    if line_end < 0:
        return word_end
    # The rest of the opening line is ordinary shell text.
    rest_out, rest_inner = scan(command[word_end:line_end])
    out.append(rest_out + "\n")
    inner.extend(rest_inner)
    strip = "\t" if dash else ""
    body_lines, j, n = [], line_end + 1, len(command)
    while j < n:
        k = command.find("\n", j)
        k = n if k < 0 else k
        line = command[j:k]
        if line.lstrip(strip) == delimiter:
            j = k
            break
        body_lines.append(line)
        j = k + 1
    else:
        raise Unclear("heredoc never closed")
    if not quoted:  # the body expands: $(...) and `...` run
        inner.extend(_body_substitutions("\n".join(body_lines)))
    return j


def _commands(command: str) -> list[tuple[list[str], bool]]:
    """Split into simple commands, respecting quotes. Each comes with
    whether its output is piped into the next command."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=SPLIT_CHARS)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""  # scan() already removed real comments; "#" here is text
    try:
        tokens = list(lex)
    except ValueError as exc:
        raise Unclear(f"can't split the command ({exc})") from None
    commands: list[tuple[list[str], bool]] = []
    current: list[str] = []
    for token in tokens:
        if token and set(token) <= set(SPLIT_CHARS):
            if current:
                commands.append((current, token in ("|", "|&")))
            current = []
        else:
            current.append(token)
    if current:
        commands.append((current, False))
    return commands


# ---- checks ----------------------------------------------------------------


def secret_name(value: str) -> str | None:
    name = PurePath(value.strip().strip("'\"")).name
    for pattern in SECRET_GLOBS:
        if name and fnmatch.fnmatchcase(name, pattern):
            return pattern
    return None


def _expand_braces(word: str) -> list[str]:
    match = re.search(r"\{([^{}]*,[^{}]*)\}", word)
    if not match:
        return [word]
    out: list[str] = []
    for part in match.group(1).split(","):
        out.extend(_expand_braces(word[: match.start()] + part + word[match.end():]))
    return out[:64]


def glob_could_match_secret(token: str) -> bool:
    """Could the shell expand this glob to a secret-shaped name? Tested
    against sample secret names and names built from the glob's literal
    head and tail (".env" + tail, "id_rsa" + tail, head + ".pem"). A leading
    "*" or "?" doesn't match dotfiles, as in the shell."""
    if token.endswith("/"):
        return False  # "dir/*/" expands to directories only
    name = PurePath(token).name
    if not any(c in name for c in "*?["):
        return False
    head = re.split(r"[*?\[]", name, maxsplit=1)[0]
    tail = re.split(r"[*?\]]", name)[-1]
    candidates = set(SECRET_SAMPLES) | {".env" + tail, "id_rsa" + tail, head + ".pem", head + "x.pem", head}
    for sample in candidates:
        if sample.startswith(".") and not name.startswith("."):
            continue
        if fnmatch.fnmatchcase(sample, name) and _realistic_secret(sample):
            return True
    return False


def _realistic_secret(name: str) -> bool:
    """A secret file a glob could really reach. Literal names use the broader
    SECRET_GLOBS (any id_* name); for globs that would deny every *.ext."""
    return (
        fnmatch.fnmatchcase(name, ".env*")
        or fnmatch.fnmatchcase(name, "*.pem")
        or re.fullmatch(r"id_(rsa|dsa|ecdsa|ed25519)(\.pub|-cert\.pub)?", name) is not None
    )


def _strip_wrappers(words: list[str]) -> list[str]:
    """Drop what can precede the real program: shell keywords and braces
    (if, do, {, !), VAR=value assignments, and wrapper programs."""
    while words:
        if words[0] in ("function", "coproc") and len(words) > 2 and words[2] in ("{", "("):
            words = words[2:]  # "function NAME {", "coproc NAME {": drop the name too
            continue
        if words[0] in KEYWORDS or ASSIGNMENT_RE.fullmatch(words[0]):
            words = words[1:]
            continue
        wrapper = PurePath(words[0]).name
        if wrapper not in WRAPPERS:
            return words
        words = words[1:]
        takes_value = WRAPPER_VALUE_OPTIONS.get(wrapper, set())
        while words and (words[0].startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*|\d+(\.\d+)?[smhd]?", words[0])):
            option = words[0]
            if option == "--":
                words = words[1:]
                break
            # A short-option cluster ("-nu") takes a value if its last letter does.
            last = "-" + option[-1] if option.startswith("-") and not option.startswith("--") else option
            words = words[2:] if option in takes_value or last in takes_value else words[1:]
    return words


def _rm_reason(args: list[str]) -> str | None:
    recursive = force = False
    for arg in args:
        if arg == "--":
            break
        if arg == "--recursive":
            recursive = True
        elif arg == "--force":
            force = True
        elif arg.startswith("-") and not arg.startswith("--"):
            recursive |= "r" in arg or "R" in arg
            force |= "f" in arg
    return "rm with both recursive and force flags" if recursive and force else None


def _push_reason(args: list[str]) -> str | None:
    for arg in args:
        if arg.startswith("--force") or arg == "--mirror":
            return f"git push {arg}"
        if arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:]:
            return f"git push {arg}"
        if arg.startswith("+") and len(arg) > 1:
            return f"git push with a force refspec ({arg})"
    return None


def _scanned_words(program: str, words: list[str]) -> list[str]:
    """Words that could name a file (message text is left out)."""
    if program in TEXT_PROGRAMS:
        redirects = (">", ">>", "<", "1>", "2>", "&>")
        return [w for prev, w in zip([""] + words, words, strict=False) if prev in redirects or any(c in w for c in "<>")]
    options = MESSAGE_OPTIONS.get(program, set())
    out, skip = [], False
    for word in words:
        if skip:
            skip = False
        elif word in options:
            skip = True
        elif not any(word.startswith(o + "=") for o in options if o.startswith("--")):
            out.append(word)
    return out


def _nested_commands(program: str, args: list[str]) -> list[str]:
    nested: list[str] = []
    if program in SHELLS:
        for index, arg in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):  # -c, -lc, -ec, ...
                rest = [a for a in args[index + 1:] if not a.startswith("-")]
                nested.extend(rest[:1])
                break
    elif program == "eval":
        nested.append(" ".join(args))
    elif program == "find":
        for index, arg in enumerate(args):
            if arg in ("-exec", "-execdir", "-ok", "-okdir"):
                cmd = []
                for a in args[index + 1:]:
                    if a in (";", "+", "\\;"):
                        break
                    cmd.append(shlex.quote(a))
                nested.append(" ".join(cmd))
    return nested


def _after_first_wrapper(words: list[str]) -> list[str] | None:
    """The words after the first wrapper program (sudo, env, timeout, xargs,
    ...), skipping leading keywords and assignments; None if there's none."""
    for i, word in enumerate(words):
        if word in KEYWORDS or ASSIGNMENT_RE.fullmatch(word):
            continue
        return words[i + 1:] if PurePath(restore(word)).name in WRAPPERS else None
    return None


def _simple_reason(raw_words: list[str], depth: int, piped: bool = False) -> str | None:
    # Wrapper options vary by tool and platform (attached values, clusters,
    # durations), so rather than trust one parse, check every later word
    # position as a possible program: "sudo -uroot rm -rf x" finds "rm -rf x".
    tail = _after_first_wrapper(raw_words)
    if tail and depth < MAX_DEPTH:
        for i in range(len(tail)):
            if restore(tail[i]).startswith("-"):
                continue  # an option, not a program
            reason = _simple_reason(tail[i:], depth + 1, piped)
            if reason:
                return reason
    raw_words = _strip_wrappers([restore(w) for w in raw_words[:1]] + raw_words[1:])
    if not raw_words:
        return None
    words = [restore(w) for w in raw_words]
    if words[0].startswith("-"):
        return f"can't tell which program runs (an option, {words[0]!r}, is left where the program should be)"
    program = PurePath(words[0]).name
    args = words[1:]
    for inner in _nested_commands(program, args):
        # sh -c / eval / find -exec code whose output is piped or consumed
        # gets no lister exemption either.
        reason = bash_reason(inner, depth + 1, consumed=piped)
        if reason:
            return reason
    reason = _rm_reason(args) if program == "rm" else None
    if reason:
        return reason
    if program == "git":
        rest = args
        while rest and rest[0].startswith("-"):  # git -C dir push ...
            rest = rest[2:] if rest[0] in ("-C", "-c") else rest[1:]
        if rest and rest[0] == "push":
            reason = _push_reason(rest[1:])
            if reason:
                return reason
    # A lister prints names only; piped on (find ... | xargs cat) it doesn't.
    lister = program in LISTERS and not piped and not (program == "find" and any(a in FIND_ACTIONS for a in args))
    targets = {raw_words[k + 1] for k, w in enumerate(raw_words[:-1]) if w in REDIRECTS}
    for raw_word in _scanned_words(program, raw_words):
        redirect = raw_word in targets or any(c in raw_word for c in "<>")
        for candidate in _expand_braces(raw_word):
            for raw_token in re.split(r"[<>=:]", candidate):
                if not raw_token:
                    continue
                globbing = any(c in raw_token for c in "*?[")  # unquoted only
                token = restore(raw_token)
                if lister and not redirect and any(c in token for c in "*?["):
                    continue  # a pattern argument to ls/find/echo lists names only
                pattern = secret_name(token)
                if pattern:
                    return f"touches a secret-shaped file ({pattern}): {token}"
                if globbing and glob_could_match_secret(token):
                    return f"glob {token} could match a secret-shaped file"
    return None


def bash_reason(command: str, depth: int = 0, consumed: bool = False) -> str | None:
    """consumed: the command's output is used (inside $(...) or `...`), so a
    lister's names feed another command and get no exemption."""
    if depth > MAX_DEPTH:
        return "command nesting too deep to check"
    try:
        stripped, inner = scan(command)
        commands = _commands(stripped)
    except Unclear as exc:
        return f"can't check this command safely ({exc})"
    for sub in inner:
        reason = bash_reason(sub, depth + 1, consumed=True)
        if reason:
            return reason
    for words, piped in commands:
        reason = _simple_reason(words, depth, piped or consumed)
        if reason:
            return reason
    return None


def decide(event: dict) -> str | None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if tool in PATH_TOOLS:
        for key in ("file_path", "notebook_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str) and secret_name(value):
                return f"{tool} of a secret-shaped file ({secret_name(value)}) is denied in this repo"
    if tool in SEARCH_TOOLS:
        for key in ("path", "pattern", "glob"):
            value = tool_input.get(key)
            if isinstance(value, str) and secret_name(value):
                return f"{tool} over a secret-shaped file is denied in this repo"
    if tool == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str):
            reason = bash_reason(command)
            if reason:
                return f"Bash denied in this repo: {reason}"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("guard.py: could not parse the hook input; denying to be safe", file=sys.stderr)
        return 2
    reason = decide(event if isinstance(event, dict) else {})
    if reason:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"{reason} (AGENTS.md R-sec-2).",
                }
            },
            sys.stdout,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
