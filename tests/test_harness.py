"""The harness this repo dogfoods (roadmap P1.6): deny rules, the PreToolUse
guard, the Stop hook, `./verify --fast`, and LESSONS.md.

Hooks are driven with the JSON Claude Code sends on stdin, so this needs no
Claude Code install, login or network.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / ".claude" / "hooks" / "guard.py"
STOP = REPO_ROOT / ".claude" / "hooks" / "stop_verify.py"
SETTINGS = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())


def run_hook(script: Path, event: dict | str, env: dict | None = None) -> subprocess.CompletedProcess:
    data = event if isinstance(event, str) else json.dumps(event)
    return subprocess.run(
        [sys.executable, str(script)], input=data, capture_output=True, text=True, timeout=120, env=env, check=False
    )


def decision(event: dict) -> str:
    result = run_hook(GUARD, event)
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return "allow"
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecisionReason"]
    return out["permissionDecision"]


def _nested_sh(levels: int) -> str:
    import shlex

    command = "ls"
    for _ in range(levels):
        command = "sh -c " + shlex.quote(command)
    return command


def bash(command: str) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}


def read(path: str, tool: str = "Read") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"file_path": path}}


# ---- settings.json -----------------------------------------------------------


def test_settings_declare_the_deny_rules() -> None:
    deny = set(SETTINGS["permissions"]["deny"])
    for rule in (
        "Read(**/.env*)",
        "Read(**/*.pem)",
        "Read(**/id_*)",
        "Bash(rm -rf *)",
        "Bash(git push --force*)",
        "Bash(git push * --force*)",
        "Bash(git push -f*)",
    ):
        assert rule in deny, rule
    assert "allow" not in SETTINGS["permissions"], "this repo grants no blanket allows"


def test_settings_hooks_point_at_executable_scripts() -> None:
    hooks = SETTINGS["hooks"]
    commands = [h["command"] for group in hooks["PreToolUse"] + hooks["Stop"] for h in group["hooks"]]
    assert commands == ['"$CLAUDE_PROJECT_DIR"/.claude/hooks/guard.py', '"$CLAUDE_PROJECT_DIR"/.claude/hooks/stop_verify.py']
    assert set(hooks["PreToolUse"][0]["matcher"].split("|")) >= {"Read", "Edit", "Write", "Grep", "Glob", "Bash"}
    for script in (GUARD, STOP):
        assert os.access(script, os.X_OK), f"{script.name} isn't executable"


# ---- PreToolUse guard ------------------------------------------------------


@pytest.mark.parametrize(
    "event",
    [
        read("README.md"),
        read("/repo/src/jdad/server.py"),
        read("deploy/jdad.env.example"),
        bash("uv run pytest -q"),
        bash("git push -u origin feat/dogfood-harness"),
        bash("rm build/old.txt"),
        bash("rm -r build"),
        bash("python3 - <<'EOF'\nprint('docs mention .env and id_rsa')\nEOF"),
        bash('git commit -q -m "deny reading .env*, *.pem and id_* files"'),
        bash("git commit --message='mention x.pem'"),
        bash('gh pr comment 1 --body "the guard denies .env reads" --title "id_rsa note"'),
        bash('echo "never read .env"'),
        bash("ls *"),
        bash("cat *.md"),
        bash("bash -lc 'uv run pytest'"),
        bash('gh pr comment 1 --body "now \\$(cat .env) and \\`rm -rf x\\` are denied"'),  # escaped: never run
        bash("python3 - <<'EOF'\nx = '$(cat .env)'\nEOF"),  # quoted heredoc body is literal
        bash("find . -name '*.pem'"),  # listing names only
        bash("cat *.md *.txt"),
        bash("for d in catalog/skills/*/; do echo $d; done"),  # "*/" matches directories only
        bash("echo $((1 << 2))"),
        bash("FOO=1 make test"),
        bash("(cd src && ls)"),
        bash("for f in *.py; do echo $f; done"),
        bash("if [ -f x ]; then rm -r build; fi"),
        bash("timeout 5 uv run pytest"),
        bash("sudo -u x ls"),
        bash("find . | xargs -I{} echo {}"),
        bash("find . -print0 | xargs -0 -n1 echo"),
        bash("timeout -s KILL 5 git push origin feat/x"),
    ],
    ids=["readme", "abs-src", "env-example-name", "pytest", "normal-push", "rm-file", "rm-r", "heredoc-body",
         "commit-message", "commit-message-eq", "gh-body", "echo-text", "ls-star", "cat-md-glob", "bash-lc-ok",
         "escaped-substitution", "quoted-heredoc-literal", "find-names", "cat-md-txt",
         "dir-glob-loop", "arith-shift", "env-assign-ok", "subshell-ok", "for-loop-ok", "if-rm-r-ok", "timeout-ok", "sudo-u-ok", "xargs-I-ok", "xargs-0-n1-ok", "timeout-push-ok"],
)
def test_guard_allows(event: dict) -> None:
    assert decision(event) == "allow"


@pytest.mark.parametrize(
    "event",
    [
        read(".env"),
        read("/repo/src/jdad/.env.local"),
        read("x.pem"),
        read("deploy/tls/origin.pem"),
        read("~/.ssh/id_ed25519"),
        read("id_ed25519.pub"),
        read(".env", tool="Edit"),
        read("secrets/key.pem", tool="Write"),
        {"tool_name": "Grep", "tool_input": {"pattern": "TOKEN", "path": ".env"}},
        bash("cat .env"),
        bash("source .env && ./run"),
        bash("cp ~/.ssh/id_ed25519 /tmp/k"),
        bash("rm -rf /tmp/x"),
        bash("rm -fr build"),
        bash("rm -r -f build"),
        bash("rm --recursive --force build"),
        bash("sudo rm -Rf /"),
        bash("echo hi && rm -rf build"),
        bash("sh -c 'rm -rf build'"),
        bash("timeout 5 rm -rf build"),
        bash("git push --force"),
        bash("git push -f origin main"),
        bash("git push origin main --force"),
        bash("git push --force-with-lease origin feat/x"),
        bash("git push origin +main"),
        bash("git -C /repo push -f"),
        bash("git add .env"),
        bash("git show HEAD:.env"),
        bash("echo TOKEN=x > .env"),
        bash("printf x >> deploy/key.pem"),
        bash('git commit -m "msg" -- id_ed25519'),
        # automated security review of 390dcbac / 4d7b343
        bash("cat <<EOF; cat .env\nbody\nEOF"),  # rest of the heredoc's opening line
        bash('echo "<<EOF"\ncat .env\nEOF'),  # "<<" inside quotes isn't a heredoc
        bash("cat <<EOF\nrm -rf build"),  # no closing delimiter: nothing is stripped
        bash('git commit -m "$(cat .env)"'),  # substitution in a skipped message
        bash("echo `rm -rf build`"),
        bash('gh pr comment 1 --body "$(cat ~/.ssh/id_ed25519)"'),
        bash("bash -lc 'rm -rf build'"),
        bash("sh -ec 'git push -f'"),
        bash("eval 'rm -rf build'"),
        bash(_nested_sh(6)),  # past the nesting limit: deny
        # fifth review round
        bash("echo hi # <<'EOF'\nrm -rf build\nEOF"),  # "<<" in a comment isn't a heredoc
        bash("((a<<2))\nrm -rf build\n2"),  # arithmetic shift, not a heredoc
        bash("cat <<E\"O\"F\nEOF\nrm -rf build\nE"),  # the delimiter is the whole word EOF
        bash("find . -name '*.pem' | xargs cat"),  # a lister piped on reads the files
        bash("ls > x.pem"),  # a redirect target is never exempt
        # Checker batch 3: assignments, subshells, groups and compound commands
        bash("FOO=1 rm -rf build"),
        bash("GIT_DIR=.git git push -f"),
        bash("A=1 B=2 env C=3 rm -rf build"),
        bash("(rm -rf build)"),
        bash("{ rm -rf build; }"),
        bash("if true; then rm -rf build; fi"),
        bash("if (rm -rf build); then :; fi"),
        bash("for d in a b; do rm -rf $d; done"),
        bash("while true; do git push --force; done"),
        bash("until false; do { git push -f; }; done"),
        bash("! rm -rf build"),
        bash("case x in x) rm -rf build;; esac"),
        bash("f() { rm -rf build; }; f"),
        bash("(cd src && rm -rf build)"),
        bash("(cat .env)"),
        bash("{ cat x.pem; }"),
        bash("sudo -u x FOO=1 rm -rf build"),  # a wrapper option's value isn't the program
        bash("nice -n 5 rm -rf build"),
        bash("timeout -s KILL 5 git push -f"),
        bash("find . | xargs -I{} rm -rf {}"),
        # review of the batch-3 fix
        bash("find . | xargs -i rm -rf {}"),  # -i's value is attached, never the next word
        bash("find . | xargs -l rm -rf"),
        bash("function f { rm -rf build; }"),
        bash("sudo -nu root rm -rf build"),  # clustered short options ending in a value option
        bash("timeout 1.5 rm -rf build"),
        bash("timeout 1.5s git push -f"),
        bash("env -- rm -rf build"),
        # second review of the batch-3 fix: wrappers fail closed, braces don't split
        bash("sudo -uroot rm -rf build"),
        bash("find . | xargs -Ia rm -rf a"),
        bash("find . | xargs -J % rm -rf %"),
        bash("timeout 1e1 rm -rf build"),
        bash("timeout inf git push -f"),
        bash("env -- FOO=1 rm -rf build"),
        bash("rm -r } build -f"),
        bash("coproc w { rm -rf build; }"),
        # third review: one prefix skipper, fail closed at limits
        bash("function f { timeout 1e1 rm -rf build; }"),
        bash("coproc w { sudo -uroot rm -rf build; }"),
        bash("sudo " * 300 + "rm -rf build"),  # too long to check: deny, quickly
        bash("ls " + "a " * 400),  # any simple command over the word cap is denied
        # sixth review round
        bash("echo a\\ # ; rm -rf build"),  # "#" after an escaped space isn't a comment
        bash("cat <<\"E\\OF\"\nEOF\nrm -rf build\nE\\OF"),  # backslash in a quoted delimiter: deny
        bash("cat $(ls *.pem)"),  # a lister inside a substitution: its output is used
        bash("sh -c 'ls *m' | xargs cat"),  # nested lister whose output is piped on
        bash("cat $(eval 'ls *m')"),  # ("*m" could match x.pem; "ls *m" as one word isn't a secret name)
        bash("cat .e*"),
        bash("cat *.pem"),
        bash("cp ~/.ssh/id_* /tmp"),
        bash('echo "\\\\$(cat .env)"'),  # escaped backslash, then a live substitution
        # third and fourth review rounds
        bash("cat <<EOF\n$(cat .env)\nEOF"),  # unquoted heredoc bodies expand: scanned
        bash("cat <<EOF\n'\n$(cat .env)\nEOF"),  # quotes in an unquoted body don't hide it
        bash("cat <<<x\nrm -rf build\nx"),  # here-string, not a heredoc
        bash('echo "a \\" <<\'EOF\'"\nrm -rf build\nEOF'),  # escaped quote: "<<" is still quoted
        bash("echo '\\'$(cat .env)"),  # backslash is literal inside single quotes
        bash("echo `cat .env \\\\`"),  # escaped backslash, then the closing backtick
        bash("echo $(cat .env"),  # unclosed substitution: deny
        bash("echo `cat x"),  # unclosed backtick: deny
        bash("echo $(echo $(cat .env))"),  # nested
        bash("cat *m"),  # suffix could match *.pem
        bash("cat .{env,x}"),  # brace expansion to a secret name
        bash("cat {a,id_rsa}"),
        bash("find . -name '*.pem' -exec cat {} +"),
        bash("find . -type d -exec rm -rf {} +"),
    ],
    ids=lambda e: (e["tool_input"].get("command") or e["tool_input"].get("file_path") or e["tool_name"])[:40],
)
def test_guard_denies_before_execution(event: dict) -> None:
    assert decision(event) == "deny"


def test_guard_denies_on_unparsable_input() -> None:
    result = run_hook(GUARD, "not json")
    assert result.returncode == 2 and "denying" in result.stderr


# ---- Stop hook -------------------------------------------------------------


def _fake_project(tmp_path: Path, passing: bool) -> Path:
    project = tmp_path / ("pass" if passing else "fail")
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_x.py").write_text(f"def test_x():\n    assert {passing}\n")
    verify = project / "verify"
    verify.write_text(f'#!/usr/bin/env bash\n[[ "$1" == --fast ]] || exit 9\nexec "{sys.executable}" -m pytest -q -p no:cacheprovider tests\n')
    verify.chmod(0o755)
    return project


@pytest.mark.parametrize(("passing", "code"), [(True, 0), (False, 2)])
def test_stop_hook_blocks_only_on_failure(tmp_path: Path, passing: bool, code: int) -> None:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(_fake_project(tmp_path, passing))}
    result = run_hook(STOP, {"hook_event_name": "Stop", "stop_hook_active": False}, env)
    assert result.returncode == code, result.stderr
    if not passing:
        assert "./verify --fast failed" in result.stderr and "assert False" in result.stderr


def test_stop_hook_never_loops(tmp_path: Path) -> None:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(_fake_project(tmp_path, passing=False))}
    result = run_hook(STOP, {"hook_event_name": "Stop", "stop_hook_active": True}, env)
    assert result.returncode == 0
    assert "not blocking again" in result.stderr


# ---- ./verify --fast --------------------------------------------------------


@pytest.fixture
def stub_verify(tmp_path: Path) -> tuple[Path, dict]:
    """A copy of ./verify with a stub `uv` that fails ruff or pytest on demand."""
    work = tmp_path / "repo"
    work.mkdir()
    shutil.copy2(REPO_ROOT / "verify", work / "verify")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    stub = bin_dir / "uv"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{log}"\n'
        'case "$*" in\n'
        '  *ruff*) exit "${FAIL_RUFF:-0}" ;;\n'
        '  *pytest*) exit "${FAIL_PYTEST:-0}" ;;\n'
        "  *) exit 97 ;;\n"
        "esac\n"
    )
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return work, {"env": env, "log": log}


def _fast(work: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(work / "verify"), *args], capture_output=True, text=True, env=env, check=False)


def test_verify_fast_runs_ruff_then_pytest(stub_verify) -> None:
    work, ctx = stub_verify
    result = _fast(work, ctx["env"], "--fast")
    assert result.returncode == 0 and "verify --fast: ok" in result.stdout
    calls = ctx["log"].read_text().splitlines()
    assert [("ruff" in c, "pytest" in c) for c in calls] == [(True, False), (False, True)]


@pytest.mark.parametrize("failing", ["FAIL_RUFF", "FAIL_PYTEST"])
def test_verify_fast_fails_when_either_fails(stub_verify, failing: str) -> None:
    work, ctx = stub_verify
    result = _fast(work, {**ctx["env"], failing: "1"}, "--fast")
    assert result.returncode != 0
    assert "verify --fast: ok" not in result.stdout


def test_verify_rejects_unknown_flags(stub_verify) -> None:
    work, ctx = stub_verify
    assert _fast(work, ctx["env"], "--fats").returncode == 2


# ---- LESSONS.md ------------------------------------------------------------


def test_lessons_have_dates_and_links() -> None:
    text = (REPO_ROOT / "LESSONS.md").read_text()
    entries = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    assert len(entries) >= 5
    for entry in entries:
        heading = entry.splitlines()[0]
        assert re.match(r"\d{4}-\d{2}-\d{2}: \S", heading), heading
        assert re.search(r"^- Source: https://github\.com/JongoDB/jdad/(pull|issues)/\d+", entry, re.MULTILINE), heading
        assert "- Rule:" in entry, heading


@pytest.mark.parametrize(
    "command",
    [
        "X=rm; $X -rf build",
        "cmd='rm -rf build'; eval \"$cmd\"",
        "python3 -c 'import shutil; shutil.rmtree(\"build\")'",
        "echo cm0gLXJmIGJ1aWxk | base64 -d | sh",
        "alias r='rm -rf'; r build",
        "find . -delete",
    ],
)
def test_known_gaps_are_documented_not_caught(command: str) -> None:
    """The guard docstring lists these as out of reach. If one starts being
    caught, move it to the deny list and update the docstring."""
    assert decision(bash(command)) == "allow"


def test_nested_wrappers_are_checked_in_linear_time() -> None:
    """Every-position scanning runs once per simple command, so stacked
    wrappers can't make the hook slow enough to time out (a timeout fails open)."""
    import time

    start = time.monotonic()
    assert decision(bash("sudo env timeout 5 " * 60 + "echo ok")) in ("allow", "deny")
    assert time.monotonic() - start < 2.0
