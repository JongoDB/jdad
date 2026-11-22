#!/usr/bin/env python3
"""PreToolUse guard for this repo (AGENTS.md R-sec-2, CLAUDE.md R-cc-5).

Denies, before the tool runs:
- reading or writing secret-shaped files: `.env*`, `*.pem`, `id_*` (SSH keys);
- `rm` with both recursive and force flags (`rm -rf`, `rm -fr`, `rm -r -f`, ...);
- `git push` with `--force`, `-f`, `--force-with-lease` or a `+refspec`.

It repeats the deny rules in .claude/settings.json on purpose. Those match
command text; this parses each segment of a compound command, `sh -c`
strings and wrapper commands, and it can be tested offline
(tests/test_harness.py). Reads stdin JSON (tool_name, tool_input) and, to
deny, prints hookSpecificOutput.permissionDecision = "deny". Stdlib only.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shlex
import sys
from pathlib import PurePath

SECRET_GLOBS = (".env*", "*.pem", "id_*")
PATH_TOOLS = {"Read", "Edit", "Write", "NotebookEdit", "MultiEdit"}
SEARCH_TOOLS = {"Grep", "Glob"}
OPERATOR_CHARS = ";&|\n"
# Free text, not file access: the value of these options (git commit -m,
# gh pr comment --body, ...), and everything echo/printf print except a
# redirect target. Without this a commit message naming ".env" is denied.
MESSAGE_OPTIONS = {
    "git": {"-m", "--message"},
    "gh": {"-b", "--body", "-t", "--title", "-n", "--notes"},
}
TEXT_PROGRAMS = {"echo", "printf"}
WRAPPERS = {"sudo", "env", "command", "builtin", "nohup", "nice", "time", "timeout", "stdbuf", "xargs", "exec"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Heredoc bodies are data (a script or a document), not arguments: drop them
# before looking for secret-shaped words. A script that opens a file itself
# is out of reach of any command-text check (the sandbox is the control).
HEREDOC_OPEN = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# Programs that only list names; a glob argument to them reads nothing.
LISTERS = {"ls", "find", "echo", "printf", "stat", "du", "tree"}
EXAMPLE_SECRETS = (".env", ".env.local", "x.pem", "id_ed25519")
MAX_DEPTH = 3


def _strip_heredoc_bodies(command: str) -> str:
    """Drop heredoc bodies only: the lines after the opening line, up to the
    closing delimiter. The opening line is kept and scanned. A "<<" inside
    quotes on its line, or a heredoc that is never closed, strips nothing."""
    out, pos = [], 0
    while True:
        match = HEREDOC_OPEN.search(command, pos)
        if not match:
            break
        line_start = command.rfind("\n", 0, match.start()) + 1
        before = command[line_start:match.start()]
        if before.count("'") % 2 or before.count('"') % 2:
            pos = match.end()
            continue
        body_start = command.find("\n", match.end())
        if body_start < 0:
            break
        close = re.compile(r"\n[ \t]*" + re.escape(match.group(2)) + r"[ \t]*(?=\n|$)").search(command, body_start)
        if not close:
            break
        out.append(command[pos:body_start])
        pos = close.end()
    out.append(command[pos:])
    return "".join(out)


def _substitutions(command: str) -> list[str]:
    """Commands inside $(...), <(...), >(...) or backticks."""
    inner = re.findall(r"[$<>]\(([^()]*(?:\([^()]*\)[^()]*)*)\)", command)
    inner += re.findall(r"`([^`]*)`", command)
    return inner


def secret_name(value: str) -> str | None:
    name = PurePath(value.strip().strip("'\"")).name
    for pattern in SECRET_GLOBS:
        if name and fnmatch.fnmatchcase(name, pattern):
            return pattern
    return None


def _commands(command: str) -> list[list[str]]:
    """Split a command line into simple commands, respecting quotes, so a
    ';' or newline inside a quoted message doesn't start a new command."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=OPERATOR_CHARS)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    commands: list[list[str]] = []
    current: list[str] = []
    try:
        tokens = list(lex)
    except ValueError:  # unbalanced quotes: fall back to a plain split
        tokens = re.split(r"\s+|([;&|\n]+)", command)
    for token in tokens:
        if not token:
            continue
        if set(token) <= set(OPERATOR_CHARS):
            if current:
                commands.append(current)
            current = []
        else:
            current.append(token)
    if current:
        commands.append(current)
    return commands


def _scanned_words(program: str, words: list[str]) -> list[str]:
    """The words that could name a file (message text is left out)."""
    if program in TEXT_PROGRAMS:
        out = []
        for previous, word in zip([""] + words, words, strict=False):
            if previous in (">", ">>", "<", "1>", "2>", "&>") or any(c in word for c in "<>"):
                out.append(word)
        return out
    options = MESSAGE_OPTIONS.get(program, set())
    out, skip = [], False
    for word in words:
        if skip:
            skip = False
            continue
        if word in options:
            skip = True
            continue
        if any(word.startswith(option + "=") for option in options if option.startswith("--")):
            continue
        out.append(word)
    return out


def _strip_wrappers(words: list[str]) -> list[str]:
    while words:
        head = PurePath(words[0]).name
        if head in WRAPPERS:
            words = words[1:]
            while words and (words[0].startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*|\d+[smhd]?", words[0])):
                words = words[1:]
            continue
        return words
    return words


def _rm_reason(args: list[str]) -> str | None:
    recursive = force = False
    for arg in args:
        if arg == "--":
            break
        if arg in ("--recursive",):
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


def bash_reason(command: str, depth: int = 0) -> str | None:
    if depth > MAX_DEPTH:
        return "command nesting too deep to check"
    command = _strip_heredoc_bodies(command)
    # Substitutions run even inside message text or echo arguments, and a
    # backtick span can cross words, so find them in the raw string.
    for sub in _substitutions(command):
        inner = bash_reason(sub, depth + 1)
        if inner:
            return inner
    for words in _commands(command):
        words = _strip_wrappers(words)
        if not words:
            continue
        program = PurePath(words[0]).name
        args = words[1:]
        inner_command = None
        if program in SHELLS:
            for index, arg in enumerate(args):
                if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):  # -c, -lc, -ec, ...
                    rest = [a for a in args[index + 1:] if not a.startswith("-")]
                    inner_command = rest[0] if rest else None
                    break
        elif program == "eval":
            inner_command = " ".join(args)
        if inner_command is not None:
            inner = bash_reason(inner_command, depth + 1)
            if inner:
                return inner

        if program == "rm":
            reason = _rm_reason(args)
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
        for word in _scanned_words(program, words):
            for token in re.split(r"[<>=:]", word):
                pattern = secret_name(token) if token else None
                if pattern:
                    return f"touches a secret-shaped file ({pattern}): {token}"
                if token and program not in LISTERS and any(c in token for c in "*?["):
                    name = PurePath(token).name
                    hits = [s for s in EXAMPLE_SECRETS if fnmatch.fnmatchcase(s, name) and (name.startswith(".") or not s.startswith("."))]
                    if hits:
                        return f"glob {token} could match a secret-shaped file ({hits[0]})"
    return None


def decide(event: dict) -> str | None:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if tool in PATH_TOOLS:
        for key in ("file_path", "notebook_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                pattern = secret_name(value)
                if pattern:
                    return f"{tool} of a secret-shaped file ({pattern}) is denied in this repo"
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
