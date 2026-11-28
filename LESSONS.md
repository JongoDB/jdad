# Lessons

Things a reviewer caught that an agent should have known (AGENTS.md R-flow-7). Read this before you plan. Add an entry when Checker or another reviewer catches something new: a dated heading, what went wrong, the rule now, and a link to the PR, card or verdict. Newest last. `tests/test_harness.py` checks the format.

## 2026-11-22: Scripts must work from any directory

- What happened: `deploy/install.sh` and `update.sh` sourced `common.sh` by a relative path, so the documented `sudo ./deploy/install.sh` from the repo root failed (Checker v3 on PR #1, e1ac238).
- Rule: resolve the script's own directory first, `HERE="$(cd "$(dirname "$0")" && pwd)"`, and source relative to it. Test the documented invocation, from the repo root and by absolute path.
- Source: https://github.com/JongoDB/jdad/pull/1 (fixed in fbea379; JON-1330 comment of 14:08 ET)

## 2026-11-22: A test must never do a real install as root

- What happened: run as root, `./verify` could have run `install.sh` for real against the host (Checker v4 on PR #1, fbea379).
- Rule: tests that invoke installers drop privileges first, or skip with a clear message; prove it in a namespace and show the host was left untouched.
- Source: https://github.com/JongoDB/jdad/pull/1 (fixed in 19c734b; JON-1330 comment of 14:22 ET)

## 2026-11-22: Pin SSH host keys; never trust on first use

- What happened: the bootstrap docs risked `ssh-keyscan` or `StrictHostKeyChecking accept-new` for github.com (Checker v4 on PR #1).
- Rule: pin host keys from the provider's published fingerprints and compare `ssh-keygen -lf` output before installing them.
- Source: https://github.com/JongoDB/jdad/pull/1 (19c734b; JON-1330 comment of 14:22 ET)

## 2026-11-22: Test behind the proxy you deploy behind

- What happened: the MCP SDK's DNS-rebinding protection returned 421 for the public Host through the tunnel; local tests only used loopback (Checker v5 on PR #1, 19c734b).
- Rule: allowlist public hosts explicitly and test with a Host-preserving proxy: the listed name gets 200, an unlisted one 421.
- Source: https://github.com/JongoDB/jdad/pull/1 (fixed in 967f6b2; JON-1330 comment of 14:35 ET)

## 2026-11-22: One version, checked by verify

- What happened: the package, plugin and marketplace versions drifted apart (Checker v5 on PR #1).
- Rule: the five version fields move in lockstep, and `./verify` fails when they differ (R-ver-1).
- Source: https://github.com/JongoDB/jdad/pull/1 (967f6b2)

## 2026-11-22: What you didn't run goes on the Unverified list

- What happened: Cloudflare Tunnel and Access were documented as working but never tested live (Checker v5 on PR #1).
- Rule: anything not exercised end to end is listed under Unverified in the PR and on the card (R-flow-6).
- Source: https://github.com/JongoDB/jdad/pull/1 (967f6b2)

## 2026-11-22: Test the rollback against the real previous artifact

- What happened: moving the token to a file broke rollback. Old images read only `JDAD_TOKEN`, so a rollback with the new compose file left the service down, and the PR body claimed the old container "keeps serving" (Checker on PR #9).
- Rule: when a change alters how the app is started or configured, test rollback to an image built from `main` before the change, not just forward deploys.
- Source: https://github.com/JongoDB/jdad/pull/9 (fixed in ee3eb1d)

## 2026-11-22: A lint is not a runtime control

- What happened: symlinks failed the KB lint, but the server still followed one at runtime and served `/etc/hosts`; a review doc then claimed the path was closed (Checker on PRs #8 and #12).
- Rule: if the server can be made to do it, enforce it in the server and test it there. Don't claim a fix you haven't reproduced and re-run.
- Source: https://github.com/JongoDB/jdad/pull/8 (fixed in 0a5b7d0)

## 2026-11-22: Every PR head gets a Linear note

- What happened: all seven Phase 2 PRs failed Checker because the cards had no what-changed-and-why note (Checker on PRs #7 to #13).
- Rule: post a note on the card naming the PR, its head SHA, what changed and why, and an Unverified list; post again whenever the head moves.
- Source: https://github.com/JongoDB/jdad/pull/7 (JON-1340 and the other cards, 2026-11-22 5:03 PM ET)

## 2026-11-22: Check credential constraints before recommending one

- What happened: the protection plan recommended a fine-grained PAT for a collaborator machine user; those can't reach another user's personal repo (Checker on PR #12).
- Rule: confirm the credential type works for the account and repo ownership before writing it into a plan.
- Source: https://github.com/JongoDB/jdad/pull/12 (fixed in 3f120db)

## 2026-11-23: Check every PR's base before READY

- What happened: Checker batch 14 passed six stacked PRs, and Daisy merged them in order. Only #20 reached `main`. #21, #17, #22, #23 and #24 each merged into the branch below, because their bases were never retargeted after #20 landed; their bodies only said "I'll retarget as they land". Landing them took an extra PR (#30) and another Checker pass.
- Rule: before writing a READY line, check each PR's base with `gh pr view N --json baseRefName`. If it isn't `main`, retarget it once the PR below has merged, or say in the READY line that it's stacked and on what. After each merge in a stack, retarget the next PR straight away.
- Source: https://github.com/JongoDB/jdad/pull/30 (Daisy, brief after Checker batch 14; JON-1348 note of 17:37 ET)

## 2026-11-27: Empty fixture directories pass locally and fail in CI

- What happened: `tests/fixtures/review/sources/` was empty in the author's working copy. Git doesn't track empty directories, so it didn't exist in a clean clone, and 14 tests failed in GitHub's `verify` on d3e2701 after the PR had been reported ready (Checker on #38).
- Rule: a fixture directory that must exist but has no files gets a `.gitkeep`; `tests/test_fixture_dirs.py` fails on an empty one. Before READY, check GitHub's `verify` result on the exact head, and run `./verify` in a clean clone when a PR adds files.
- Source: https://github.com/JongoDB/jdad/pull/38 (fixed in d95229d; guard from JON-1393 item 12)

## 2026-11-27: Reproduce "failed before the fix" from committed states

- What happened: #39's body said the new tests with main's `src/` gave `2 failed, 110 passed`. That setup stops at collection with an ImportError, because the tests import the new `UnknownTagError`. The number came from a working tree mid-edit, before the rename, a state no commit has (Checker on #39; fixed in the body, no new commit).
- Rule: commit the tests first, then reproduce the red run in a scratch clone from named SHAs ("tests at <sha>, <file> from <sha>") and copy pytest's summary line exactly.
- Source: https://github.com/JongoDB/jdad/pull/39 (Checker verdict at e8063218)

## 2026-11-27: Post the plan on the card before the first code commit

- What happened: #40 (JON-1393 item 14) had no plan on the Linear card. The first comment about item 14 came 17 seconds after the fix commit, so Checker failed the PR on process (R-flow-2). A retroactive plan was posted on JON-1393 afterwards.
- Rule: for every item, including follow-ups drafted one after another on one card, post the plan (steps, risks, how each acceptance criterion is checked) on the card before the first commit for that item, test commits included. Check the comment's timestamp is earlier than the commit's.
- Source: https://github.com/JongoDB/jdad/pull/40 (Checker verdict at 00986740)

## 2026-11-27: Quote a comment's createdAt; never hand-write when it was posted

- What happened: plan comments on JON-1393 said when they were posted in hand-written ET times that didn't match Linear's `createdAt`: "18:40" for 18:36, "18:44" for 18:37, "19:10" for 19:09 and "19:17" for 19:16. Checker flagged it twice, on #40's re-check and on #41. "Plan before the first commit" is proven by comparing those times with commit times, so a wrong one weakens the evidence even when the order holds.
- Rule: post the comment first, then quote its `createdAt` as Linear returns it, in UTC with the ET conversion (e.g. `2026-11-28T00:09:12Z = 19:09:12 ET`), wherever a card, PR body, status file or note says when it was posted. If the comment's own text states a time, edit it to that value afterwards.
- Source: https://github.com/JongoDB/jdad/pull/41 (Checker's pass at 321121f, relayed by Daisy); first flagged after #40 (JON-1393 comment 4b931742)

## 2026-11-28: A mutant changes only what its label names

- What happened: #43 (JON-1482) claimed 8 of 8 mutants killed. The mutant labelled "preflight skips loading practices" dropped `kb.practices()` and also hard-coded the KB root, so `KB_ROOT` was ignored; that second change is what the tests caught. Dropping only the call passed 1148/1148, and the call can't fail at all (`Path.glob` lists an unreadable `practices/` as empty). Checker failed the PR on the false claim.
- Rule: each mutant edits only the spot its label names (the harness asserts every edit falls on the lines of its one anchor), and a call counts as covered only if some input can make it matter. A survivor that can't be killed is reported as one (N-1 of N, naming the line), not hidden behind a wider mutant.
- Source: https://github.com/JongoDB/jdad/pull/43 (Checker verdict at 41b9a75, relayed by Daisy); fixed at cd330ea
