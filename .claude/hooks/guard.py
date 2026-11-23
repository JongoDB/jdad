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
unclosed substitution, nesting too deep, out of time). It also sees
through leading VAR=value assignments (their values are checked too),
( ) subshells, { } groups, if/for/while/case bodies, wrapper options
that take a value (sudo -u USER), backslash-newline continuations, GNU
long-option prefixes (rm --rec --forc), variables the command itself
assigns with NAME=value or export/local/declare/typeset/readonly, or
defaults ("F=-rf; rm $F", "rm ${F:--rf}"), and the input a shell program
(sh, bash, zsh, dash, ksh) gets, treated as code it may run:
here-strings and heredocs on any descriptor, and echo/printf text piped
in. Which descriptor such a shell reads its script from isn't modelled
(it depends on -s, option clusters, --rcfile and paths), so any input
the guard can't see is denied: a file or duplicated descriptor, another
program's output piped in, a script or rc file under dev/ or proc/. So
is printf or echo text with escapes or a format that's run as code (the
guard doesn't decode it). Every value such an assignment gives a
variable counts, and ${NAME+word} on a variable the command doesn't set
may be word. Secret names are matched case-insensitively (.ENV is .env
on macOS).

It is not a sandbox, and it does NOT catch (tested as known gaps):
- code that never appears as shell text: interpreters (python -c
  "shutil.rmtree(...)"), a script file written and then run (bash s.sh),
  a variable set from a file or a command (X=$(cat f)), aliases;
- other destructive commands outside the deny list (find -delete, git
  reset --hard, git clean -fdx, branch deletion with git push origin
  :main, --delete or -d);
- shell forms it doesn't model (JON-1357): $'...' quoting, brace
  expansion ({rm,-rf,x}), words spliced from parts (r$(true)m,
  `echo rm`); variables set by IFS splitting, set -- / "$@", printf -v,
  read or mapfile; code run by source or . (of <(...) or /dev/stdin),
  env -S, trap, PROMPT_COMMAND or BASH_ENV; eval of decoded text; an
  abbreviated --mirror (git push --mirr);
- secret files outside the list above (*.key, *.p12, credentials.json);
- Grep or Glob over a whole directory that contains secret files.
Reads the hook's stdin JSON
(tool_name, tool_input); to deny, prints hookSpecificOutput with
permissionDecision "deny". Stdlib only; tests in tests/test_harness.py.
"""

from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import shlex
import signal
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
WRAPPERS = {"sudo", "env", "command", "builtin", "nohup", "nice", "time", "timeout", "stdbuf", "xargs", "exec",
            "doas", "setsid", "ionice", "chrt", "flock", "watch", "unbuffer", "busybox"}
# Wrappers that take shell code as an argument: watch joins its operands and
# runs them with sh -c; flock runs the value of -c/--command with sh -c.
CODE_WRAPPERS = {"watch", "flock"}
# Wrapper options that take a separate value ("sudo -u USER cmd"): skip both words.
WRAPPER_VALUE_OPTIONS = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T", "--user", "--group", "--chdir", "--host", "--prompt"},
    "env": {"-u", "-C", "--unset", "--chdir"},
    "nice": {"-n", "--adjustment"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "stdbuf": {"-i", "-o", "-e"},
    "doas": {"-u", "-C"},
    "ionice": {"-c", "-n", "-p", "-P", "-u", "--class", "--classdata", "--pid", "--pgid", "--uid"},
    "flock": {"-w", "-E", "--timeout", "--conflict-exit-code"},
    "watch": {"-n", "-d", "-q", "--interval", "--differences", "--equexit"},
    # Not -i, -l, -e: their (optional) value is always attached ("-i{}").
    "xargs": {"-I", "-J", "-R", "-S", "-n", "-P", "-L", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--delimiter", "--arg-file"},
}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Builtins that set variables from NAME=value arguments.
DECLARERS = {"export", "local", "declare", "typeset", "readonly"}
# $NAME, ${NAME}, ${NAME:-default} and the other ${NAME<op>word} forms.
VARIABLE_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-=+?])([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")
# Programs that only print names: a glob argument to them reads nothing.
LISTERS = {"ls", "find", "echo", "printf", "stat", "du", "tree"}
FIND_ACTIONS = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"}
# Free text, not file access: the value of these options, and what
# echo/printf print (apart from a redirect target).
MESSAGE_OPTIONS = {"git": {"-m", "--message"}, "gh": {"-b", "--body", "-t", "--title", "-n", "--notes"}}
TEXT_PROGRAMS = {"echo", "printf"}
MAX_DEPTH = 4
MAX_WORDS = 256  # a simple command longer than this is denied, not analysed
TIME_BUDGET_SECONDS = 5  # the hook denies if analysis takes longer (a timeout would fail open)
# Glob characters inside quotes are literal; the scanner swaps them for
# these markers so only unquoted ones count as globs.
QUOTED_GLOB = {"*": "\x01", "?": "\x02", "[": "\x03"}
_RESTORE = str.maketrans({v: k for k, v in QUOTED_GLOB.items()})
# The "&" in a redirection (2>&1, <&3, &>file) isn't the background operator;
# scan() swaps it for this marker so the splitter keeps the word whole.
REDIRECT_AMP = "\x04"


def restore(text: str) -> str:
    return text.translate(_RESTORE)


REDIRECTS = (">", ">>", "<", "1>", "2>", "&>", ">|")
# A redirection word: optional fd, operator, and (attached) target. A bare
# operator takes the next word as its target.
REDIRECT_WORD_RE = re.compile(r"(\d*)(<<<|<<-|<<|<>|<&|>&|&>>|&>|>>|>\||<|>)(.*)", re.DOTALL)
# Operands that make a shell read its script from stdin.
STDIN_OPERANDS = {"-", "/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"}
MAX_VARIANTS = 8  # possible values of a word or a command checked; more is denied, never truncated
# Shell options whose value is a separate word (not the script).
SHELL_VALUE_OPTIONS = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
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


def scan(command: str) -> tuple[str, list[str], list[str]]:
    """Return (command with heredoc bodies removed, inner commands to check,
    heredoc bodies).

    Inner commands are every $(...), <(...), >(...) and `...` the shell
    would run: outside single quotes, unescaped, including inside unquoted
    heredoc bodies. A heredoc body with a quoted delimiter (<<'EOF') is
    literal data and is skipped. A backslash escapes only outside single
    quotes. A backslash-newline outside single quotes is removed, as bash
    joins the lines ("rm \\" + newline + "-rf x" is "rm -rf x"). Heredoc
    bodies are returned too: a shell reading its code from stdin runs them.
    """
    out: list[str] = []
    inner: list[str] = []
    bodies: list[str] = []
    i, quote, n = 0, None, len(command)
    while i < n:
        c = command[i]
        if quote == "'":
            out.append(QUOTED_GLOB.get(c, c))
            quote = None if c == "'" else quote
            i += 1
        elif c == "\\" and command.startswith("\n", i + 1):
            i += 2  # line continuation: the shell joins the lines
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
        elif c in "<>" and command.startswith("&", i + 1):
            out.append(c + REDIRECT_AMP)
            i += 2
        elif c == "&" and command.startswith(">", i + 1):
            out.append(REDIRECT_AMP + ">")
            i += 2
        elif command.startswith("<<<", i):
            out.append("<<<")
            i += 3
        elif command.startswith("<<", i):
            i = _heredoc(command, i, out, inner, bodies)
        else:
            out.append(c)
            i += 1
    if quote is not None:
        raise Unclear("unclosed quote")
    return "".join(out), inner, bodies


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


def _heredoc(command: str, i: int, out: list[str], inner: list[str], bodies: list[str]) -> int:
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
    rest_out, rest_inner, rest_bodies = scan(command[word_end:line_end])
    out.append(rest_out + "\n")
    inner.extend(rest_inner)
    bodies.extend(rest_bodies)
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
    bodies.append("\n".join(body_lines))
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
    tokens = [token.replace(REDIRECT_AMP, "&") for token in tokens]
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
    # Lower-cased: on a case-insensitive file system (macOS, Windows) .ENV is .env.
    name = PurePath(value.strip().strip("'\"")).name.lower()
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


def _skip_prefix(words: list[str]) -> list[str]:
    """Drop shell keywords and braces (if, do, {, !), "function NAME {" and
    "coproc NAME {", VAR=value assignments and leading redirections. Shared by every caller so
    the parses can't drift apart."""
    while words:
        redirect = REDIRECT_WORD_RE.fullmatch(words[0])
        if words[0] in ("function", "coproc") and len(words) > 2 and words[2] in ("{", "("):
            words = words[2:]
        elif words[0] in KEYWORDS or ASSIGNMENT_RE.fullmatch(words[0]):
            words = words[1:]
        elif redirect:
            # ">/dev/null rm -rf x": a redirection may come before the program.
            words = words[1:] if redirect.group(3) else words[2:]
        else:
            break
    return words


def _strip_wrappers(words: list[str]) -> list[str]:
    """Drop what can precede the real program: the prefix (_skip_prefix)
    and wrapper programs with their options."""
    while words:
        skipped = _skip_prefix(words)
        if skipped is not words:
            words = skipped
            continue
        if not words:
            return words
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
        # GNU getopt accepts any unambiguous prefix: --rec, --forc, even --r and --f.
        if len(arg) > 2 and "--recursive".startswith(arg):
            recursive = True
        elif len(arg) > 2 and "--force".startswith(arg):
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


def _reference_values(match: re.Match, variables: dict[str, list[str]]) -> list[str]:
    """What one $NAME / ${NAME<op>word} can expand to. Every value the command's
    NAME=value and export/local/declare/typeset/readonly assignments
    give the variable counts (order isn't tracked; values set by read,
    mapfile, printf -v, set -- or IFS splitting aren't seen: JON-1357). For a variable the
    command doesn't set, the environment may set it: ${NAME+word} may be
    word, and ${NAME:-word} is word when it's unset."""
    name = match.group(1) or match.group(4)
    op, word = match.group(2), match.group(3) or ""
    values = variables.get(name)
    if op in ("-", ":-", "=", ":="):
        return [v or word for v in values] if values else [word]
    if op in ("+", ":+"):
        return [word] if values else ["", word]
    return list(values) if values else [match.group(0)]


def _expand(word: str, variables: dict[str, list[str]]) -> list[str]:
    """Every expansion of a word (at most MAX_VARIANTS)."""
    variants, pos = [""], 0
    for match in VARIABLE_RE.finditer(word):
        literal = word[pos:match.start()]
        options = _reference_values(match, variables)
        variants = [v + literal + o for v in variants for o in options]
        if len(variants) > MAX_VARIANTS:
            raise Unclear("too many possible values to check")
        pos = match.end()
    out: list[str] = []
    for variant in variants:
        if variant + word[pos:] not in out:
            out.append(variant + word[pos:])
    return out


def _argv_variants(words: list[str], variables: dict[str, list[str]]) -> list[list[str]]:
    """Every argv the words can expand to, each checked on its own (merging
    values into one argv lets one hide another: "F=--; F=-rf; rm $F x").
    Only a word that is nothing but one variable reference ("$FLAGS",
    "${F:--rf}") is split into several words, as the shell splits an
    unquoted expansion; any other word stays one word, so message text
    after -m or --body is still skipped as a whole. More than MAX_VARIANTS
    argvs is denied."""
    argvs: list[list[str]] = [[]]
    for word in words:
        variants = _expand(word, variables)
        if variants == [word]:
            options = [[word]]
        elif VARIABLE_RE.fullmatch(word):
            options = [variant.split() for variant in variants]
        else:
            options = [[variant] for variant in variants]
        argvs = [argv + option for argv in argvs for option in options]
        if len(argvs) > MAX_VARIANTS:
            raise Unclear("too many possible values to check")
    return argvs


def _assignments(words: list[str]) -> list[tuple[str, str]]:
    """NAME=value pairs a simple command sets: leading assignments, and the
    arguments of export/local/declare/typeset/readonly."""
    words = [restore(w) for w in words]
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(words) and words[i] in KEYWORDS:
        i += 1
    while i < len(words) and ASSIGNMENT_RE.fullmatch(words[i]):
        name, value = words[i].split("=", 1)
        pairs.append((name.rstrip("+").split("[")[0], value))
        i += 1
    if i < len(words) and words[i] in DECLARERS:
        for word in words[i + 1:]:
            if ASSIGNMENT_RE.fullmatch(word):
                name, value = word.split("=", 1)
                pairs.append((name.rstrip("+").split("[")[0], value))
    return pairs


def _printed_texts(words: list[str], variables: dict[str, list[str]]) -> list[str] | None:
    """What an echo/printf command prints (joined both ways, since printf
    puts each argument on its own line with '%s\\n'); None for any other
    program."""
    texts: list[str] = []
    for argv in _argv_variants([restore(w) for w in words], variables):
        printed = _printed_argv(_strip_wrappers(argv))
        if printed is None:
            return None
        texts.extend(printed)
    return texts


def _printed_argv(words: list[str]) -> list[str] | None:
    if not words or PurePath(words[0]).name not in TEXT_PROGRAMS:
        return None
    args = words[1:]
    if PurePath(words[0]).name == "echo":
        while args and re.fullmatch(r"-[neE]+", args[0]):
            args = args[1:]
    # printf formats and backslash escapes (printf, echo -e, zsh's echo) can
    # print something other than their text: "printf 'r\\x6d'" prints "rm".
    if any("\\" in a for a in args) or (PurePath(words[0]).name == "printf" and any("%" in a for a in args)):
        raise Unclear("printf/echo text with escapes or a format, run as code")
    return [" ".join(args), "\n".join(args)]


def _as_code(text: str, variables: dict[str, list[str]]) -> list[str]:
    """Shell code plus what echo/printf print inside its substitutions:
    'bash -c "$(printf 'rm -rf x')"' runs the printed text."""
    texts = [text]
    try:
        _, inner, _ = scan(text)
    except Unclear:
        return texts  # bash_reason(text) reports it
    for sub in inner:
        try:
            commands = _commands(scan(sub)[0])
        except Unclear:
            continue  # bash_reason(text) reports it
        for words, _piped in commands:
            texts.extend(_printed_texts(words, variables) or [])  # Unclear propagates: deny
    return texts


def _wrapper_code(wrapper: str, args: list[str]) -> list[str]:
    """Shell code a code-running wrapper passes to sh -c. Option parsing is
    not trusted (optional values, clusters, abbreviations), so this errs
    toward checking more words as code."""
    if wrapper == "flock":
        codes: list[str] = []
        for index, arg in enumerate(args):
            following = args[index + 1] if index + 1 < len(args) else ""
            if arg.startswith("--"):
                name, eq, value = arg.partition("=")
                if len(name) > 2 and "--command".startswith(name):  # --command, --comm, --c...
                    codes.append(value if eq else following)
            elif arg.startswith("-"):
                cluster = re.match(r"-[A-Za-z]*?c(.*)", arg, re.DOTALL)  # -c, -oc, -c'code'
                if cluster:
                    codes.append(cluster.group(1) or following)
        return [code for code in codes if code]
    # watch joins its operands into one command; any word could be where
    # the code starts once an option with an optional value (-d) is misread.
    return [" ".join(args[i:]) for i in range(len(args)) if not args[i].startswith("-")]


def _stdin_code(words: list[str], producer: list[str] | None, bodies: list[str],
                variables: dict[str, list[str]]) -> tuple[list[str], str | None]:
    """If this command runs a shell that reads its code from stdin (or from
    another descriptor, /dev/fd/N), return (code it reads, reason to deny
    when that code can't be seen). Every possible argv is checked."""
    codes: list[str] = []
    for argv in _argv_variants([restore(w) for w in words], variables):
        found, unseen = _stdin_code_argv(argv, producer, bodies, variables)
        if unseen:
            return codes, unseen
        codes.extend(found)
    return codes, None


def _stdin_code_argv(words: list[str], producer: list[str] | None, bodies: list[str],
                     variables: dict[str, list[str]]) -> tuple[list[str], str | None]:
    """Every input a shell program (SHELLS) gets is treated as code it may run
    (source and . aren't shell programs here: JON-1357), wherever the
    redirection is and whichever descriptor it's on: which descriptor a
    shell reads its script from depends on options (-s, clusters, --rcfile)
    and paths the guard can't model reliably, so it doesn't try. Here-strings,
    heredocs and piped echo/printf text are checked as code; any input the
    guard can't see (a file, a duplicated descriptor, another program's
    output) is denied, and so is a script path under dev/ or proc/."""
    rest: list[str] = []
    codes: list[str] = []
    unseen = False
    k = 0
    while k < len(words):
        match = REDIRECT_WORD_RE.fullmatch(words[k])
        if not match:
            rest.append(words[k])
            k += 1
            continue
        fd, op, target = match.groups()
        if not target:  # a bare operator: the next word is its target (or heredoc delimiter)
            target = words[k + 1] if k + 1 < len(words) else ""
            k += 1
        k += 1
        if op.startswith((">", "&")):
            if fd == "0":  # 0>&3, 0>file: stdin replaced by something unseen
                unseen = True
            continue  # otherwise an output redirection
        if op == "<<<":
            codes.append(target)
        elif op in ("<<", "<<-"):
            codes.extend(bodies)
        else:
            unseen = True  # <, <> or <&: a file or descriptor the guard can't see
    rest = _strip_wrappers(rest)
    if not rest or PurePath(rest[0]).name not in SHELLS:
        return [], None
    args, k = rest[1:], 0
    while k < len(args):
        arg = args[k]
        if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):
            break  # -c: the next word is code (checked by _nested_commands), the rest are $0, $1...
        if arg in SHELL_VALUE_OPTIONS:
            value = args[k + 1] if k + 1 < len(args) else ""
            if arg in ("--rcfile", "--init-file") and _device_path(value):
                return [], "a shell reads code from a device path the guard can't see"
            k += 2
            continue
        if not arg.startswith(("-", "+")) and _device_path(arg):
            return [], "a shell reads a script from a device path the guard can't see"
        k += 1
    if producer is not None:
        printed = _printed_texts(producer, variables)
        if printed is None:
            return codes, "a shell reads input from a pipe the guard can't see"
        codes.extend(printed)
    if unseen:
        return codes, "a shell reads input from a file or descriptor the guard can't see"
    return codes, None


def _device_path(arg: str) -> bool:
    """A path with a dev or proc component (absolute or relative, any
    spelling or case), other than stdin itself ("-", /dev/stdin,
    /dev/fd/0), which is checked as input anyway."""
    if arg in STDIN_OPERANDS:
        return False
    path = posixpath.normpath(re.sub(r"/+", "/", arg)).lower()
    if path in ("/dev/stdin", "/dev/fd/0"):
        return False
    return any(part in ("dev", "proc") for part in path.split("/"))


def _token_reason(raw_word: str, lister: bool, redirect: bool) -> str | None:
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


def _scanned_words(program: str, words: list[str], consumed: bool = False) -> list[str]:
    """Words that could name a file (message text is left out). What
    echo/printf print inside $(...) feeds another command, so it counts."""
    if program in TEXT_PROGRAMS and consumed:
        return words[1:]
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


def _nested_commands(program: str, args: list[str], variables: dict[str, list[str]]) -> list[str]:
    nested: list[str] = []
    if program in SHELLS:
        for index, arg in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg):  # -c, -lc, -ec, ...
                rest = [a for a in args[index + 1:] if not a.startswith("-")]
                for code in rest[:1]:
                    nested.extend(_as_code(code, variables))
                break
    elif program == "eval":
        nested.extend(_as_code(" ".join(args), variables))
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
    ...) once the prefix is skipped; None if the program isn't a wrapper."""
    words = _skip_prefix(words)
    if words and PurePath(restore(words[0])).name in WRAPPERS:
        return words[1:]
    return None


def _simple_reason(raw_words: list[str], depth: int, piped: bool = False, scan_tail: bool = True,
                   consumed: bool = False, variables: dict[str, list[str]] | None = None) -> str | None:
    try:
        return _simple_reason_inner(raw_words, depth, piped, scan_tail, consumed, variables or {})
    except Unclear as exc:
        return f"can't check this command safely ({exc})"


def _simple_reason_inner(raw_words: list[str], depth: int, piped: bool, scan_tail: bool,
                         consumed: bool, variables: dict[str, list[str]]) -> str | None:
    if len(raw_words) > MAX_WORDS:
        return f"command too long to check ({len(raw_words)} words, limit {MAX_WORDS})"
    # An assignment's value can name a secret ("f=.env; cat $f"): check it here,
    # since the prefix is skipped below.
    for _name, value in _assignments(raw_words):
        for variant in _expand(value, variables):
            reason = _token_reason(variant, lister=False, redirect=False)
            if reason:
                return reason
    # Flags or the program held in a variable the command set ("F=-rf; rm $F"):
    # every possible argv is checked on its own.
    for argv in _argv_variants(raw_words, variables):
        reason = _argv_reason(argv, depth, piped, scan_tail, consumed, variables)
        if reason:
            return reason
    return None


def _argv_reason(raw_words: list[str], depth: int, piped: bool, scan_tail: bool,
                 consumed: bool, variables: dict[str, list[str]]) -> str | None:
    head = _skip_prefix([restore(w) for w in raw_words])
    if head and PurePath(head[0]).name in CODE_WRAPPERS:
        for code in _wrapper_code(PurePath(head[0]).name, head[1:]):
            for text in _as_code(code, variables):
                reason = bash_reason(text, depth + 1, consumed=piped, variables=variables)
                if reason:
                    return reason
    # Wrapper options vary by tool and platform (attached values, clusters,
    # durations), so rather than trust one parse, check every later word
    # position as a possible program: "sudo -uroot rm -rf x" finds "rm -rf x".
    # This runs once per simple command (scan_tail=False below): every
    # position is already covered, so nested wrappers add nothing and the
    # cost stays quadratic in the word count, not exponential.
    tail = _after_first_wrapper(raw_words) if scan_tail else None
    if tail:
        if depth >= MAX_DEPTH:
            return "command nesting too deep to check"
        for i in range(len(tail)):
            if restore(tail[i]).startswith("-"):
                continue  # an option, not a program
            reason = _simple_reason(tail[i:], depth + 1, piped, scan_tail=False, consumed=consumed, variables=variables)
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
    for inner in _nested_commands(program, args, variables):
        # sh -c / eval / find -exec code whose output is piped or consumed
        # gets no lister exemption either.
        reason = bash_reason(inner, depth + 1, consumed=piped, variables=variables)
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
    for raw_word in _scanned_words(program, raw_words, consumed):
        redirect = raw_word in targets or any(c in raw_word for c in "<>")
        reason = _token_reason(raw_word, lister, redirect)
        if reason:
            return reason
    return None


def bash_reason(command: str, depth: int = 0, consumed: bool = False,
                variables: dict[str, list[str]] | None = None) -> str | None:
    """consumed: the command's output is used (inside $(...) or `...`), so a
    lister's names feed another command and get no exemption.
    variables: what enclosing code assigned, for $NAME expansion."""
    if depth > MAX_DEPTH:
        return "command nesting too deep to check"
    try:
        stripped, inner, bodies = scan(command)
        commands = _commands(stripped)
    except Unclear as exc:
        return f"can't check this command safely ({exc})"
    # Every assignment in the command, wherever it is ("F=-rf; rm $F"). Order
    # isn't tracked; a later assignment counts too, which is the safe side.
    variables = {name: list(values) for name, values in (variables or {}).items()}
    for words, _piped in commands:
        for name, value in _assignments(words):
            known = variables.setdefault(name, [])
            try:
                expanded = _expand(value, variables)
            except Unclear as exc:
                return f"can't check this command safely ({exc})"
            for variant in expanded:  # never truncated; a use with too many values is denied in _expand
                if variant not in known:
                    known.append(variant)
    for sub in inner:
        reason = bash_reason(sub, depth + 1, consumed=True, variables=variables)
        if reason:
            return reason
    producer: list[str] | None = None
    for words, piped in commands:
        reason = _simple_reason(words, depth, piped or consumed, consumed=consumed, variables=variables)
        if reason:
            return reason
        # A shell reading code from stdin runs whatever is piped, here-stringed
        # or heredoc'd into it.
        try:
            codes, unseen = _stdin_code(words, producer, bodies, variables)
            if unseen:
                return unseen
            texts = [text for code in codes for text in _as_code(code, variables)]
        except Unclear as exc:
            return f"can't check this command safely ({exc})"
        for text in texts:
            reason = bash_reason(text, depth + 1, consumed=piped or consumed, variables=variables)
            if reason:
                return reason
        producer = words if piped else None
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


def _out_of_time(_signum, _frame) -> None:
    raise TimeoutError


def main() -> int:
    # A hook that times out fails open, so the guard denies on its own clock first.
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _out_of_time)
        signal.alarm(TIME_BUDGET_SECONDS)
    try:
        return _main()
    except TimeoutError:
        _deny(f"the guard ran out of time ({TIME_BUDGET_SECONDS}s) checking this command")
        return 0


def _deny(reason: str) -> None:
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


def _main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("guard.py: could not parse the hook input; denying to be safe", file=sys.stderr)
        return 2
    reason = decide(event if isinstance(event, dict) else {})
    if reason:
        _deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
