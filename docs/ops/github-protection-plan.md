# Plan: protect `main` and give the bots their own GitHub identities

For Daisy and Jon to apply (JON-1338). Nothing here has been applied; the builder agent has no permission to change repo settings. Written 2026-11-22.

## Why

Today every bot (builder sessions, Daisy, Checker) acts as `JongoDB`, the repo's only collaborator and admin, and `main` has no protection (the API returns 403 on a private repo without GitHub Pro). Anything that reaches `main` is deployed by `update-docker.sh` and installed by the plugin marketplace. "Nobody merges their own PR" is policy only. Making the repo public (Jon, 2026-11-22) makes rulesets free; separate identities make "someone else approved this" enforceable.

## Order

1. Repo goes public (after the scrub's gating steps: [pre-public scrub](../reviews/2026-11-22-pre-public-scrub.md#recommendation)).
2. **Ruleset phase 1** right away: no direct pushes, no force-push, no deletion, nobody bypasses.
3. **Phase 2** after the first green `verify` run on a PR: require that check.
4. **Bot identities** (below), then **phase 3**: one approval from someone other than the last pusher, and code-owner review for KB content.

## Ruleset

Apply with `gh api -X POST repos/JongoDB/jdad/rulesets --input <file>`. Later phases update the same ruleset with `gh api -X PUT repos/JongoDB/jdad/rulesets/<id> --input <file>`.

**Phase 1, `protect-main`:**

```json
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      }
    }
  ]
}
```

- `bypass_actors: []`: no one bypasses, admins included. Jon's account goes through PRs like everyone else. To undo in an emergency, the admin sets `enforcement` to `disabled` (an audited settings change), not a silent bypass.
- With `required_approving_review_count: 0`, a PR is still required (no direct pushes), but nobody has to approve yet. Approvals come in phase 3, once a second identity exists; until then a required approval would block every merge.
- Merge methods aren't restricted. History has both merge commits and squashes.

**Phase 2:** add the CI check once a run on a PR has passed (so the context name is known to GitHub):

```json
{
  "type": "required_status_checks",
  "parameters": {
    "strict_required_status_checks_policy": false,
    "required_status_checks": [{ "context": "verify", "integration_id": 15368 }]
  }
}
```

`15368` is the GitHub Actions app, so only a check from Actions satisfies `verify`, not a status posted by some token. `strict: false` avoids forcing every PR to be rebased onto `main` before merging; turn it on if PRs start landing green but breaking `main`.

**Phase 3**, after the identities below exist: in the `pull_request` rule set `required_approving_review_count: 1`, `require_last_push_approval: true` (whoever pushed last can't be the approver) and `require_code_owner_review: true`.

**Check each phase:**

- `gh api repos/JongoDB/jdad/rulesets` shows the ruleset as `active`.
- `gh api repos/JongoDB/jdad/rules/branches/main` lists the effective rules.
- Optionally, a direct push of an empty commit to `main` from a scratch clone is rejected. If the rule were broken this would land an empty commit, so it's Daisy's call.

## Identities

| Actor | Identity | Repo access | Why this kind |
| --- | --- | --- | --- |
| Jon | `JongoDB` (personal) | Admin, **not** a bypass actor | The human owner. Code owner for KB content |
| Builder sessions (Claude Code and other coding agents) | GitHub App `jdad-builder` | Contents: write, Pull requests: write, Metadata: read. **No Workflows, no Administration** | Short-lived installation tokens (1 hour), fine-grained, shows as `jdad-builder[bot]`. Without Workflows permission a bot can't change CI that gates it |
| Daisy (KB PRs, merges) | GitHub App `jdad-daisy` | Same as the builder | A separate App keeps attribution clear, and lets one bot's credential be revoked alone |
| Checker (review) | Machine user `jdad-checker` | Write role (no Maintain or Admin); uses only review and comment | Approvals count when the reviewer has write access, and a user can be a code owner while an App can't (see Unverified). GitHub's terms allow one free machine account per person |

**CODEOWNERS** (replace the draft in PR #8 once these exist):

- `practices/`, `sources/`, `skills/`, `commands/`, `kb-lint.toml`: `@JongoDB`. A human approves every change to what agents are told to do (threat model, H4).
- Everything else: `@JongoDB @jdad-checker`. Checker's approval is enough for code, deploy and docs.

**Merging.** With `require_last_push_approval`, the approver can't be the last pusher, so an author bot can't approve its own PR. The ruleset can't stop the author from *merging* once someone else approved. "Daisy merges" stays a working rule: Daisy merges PRs she didn't author, and Jon merges hers.

## Moving each credential

Do one bot at a time, and keep the old credential until the new one has opened, or reviewed, a test PR.

1. **Create** the identity: App (owner `JongoDB`, installed on `JongoDB/jdad` only, permissions as in the table) or machine user (invited with the Write role, 2FA on).
2. **Store** the secret where that bot runs, never in a repo. For an App, the private key lives in the host's secret store, and the bot mints installation tokens from it (`gh` can't do this itself; use a small token helper or the `actions/create-github-app-token` pattern). For the machine user: a **classic** PAT (see below), expiring in 90 days.
3. **Point the bot at it:** a separate `GH_CONFIG_DIR` per bot, or `GH_TOKEN` in the bot's environment only, plus `git config user.name` and `user.email` matching the identity (the App's `<id>+<slug>[bot]@users.noreply.github.com`).
4. **Test:** the bot opens (or reviews) a trivial PR. Check the author or reviewer shown on GitHub.
5. **Revoke** `JongoDB`'s credential on that host (`gh auth logout`; delete any PAT made for it). Note the date on JON-1338.

| Bot | Today | After |
| --- | --- | --- |
| Builder sessions on Jon's Mac | `gh` logged in as `JongoDB` | `jdad-builder` App token via a helper; Jon's own `gh` login stays for Jon |
| Daisy | (Daisy's host; unknown to me) | `jdad-daisy` App token |
| Checker | acts as `JongoDB` | `jdad-checker` machine user PAT |
| Droplet | read-only deploy key "droplet (read-only)" | unchanged (read-only, repo-scoped) |

**Checker's token: a classic PAT, not a fine-grained one (correction, Checker 2026-11-22).** A fine-grained PAT can only reach repositories owned by its resource owner: the user who made it, or an organization that allows such tokens. `JongoDB/jdad` is a personal repository, so `jdad-checker`, which is only a collaborator, can't select it in a fine-grained token. An earlier draft of this plan said to use one; that doesn't work.

- **Recommended: a classic PAT for `jdad-checker`, scope `public_repo` only**, created after the repo is public, expiring in 90 days. A classic token's scope covers every repo the account can reach. `jdad-checker` is a collaborator on `JongoDB/jdad` and nothing else, and `public_repo` excludes private repos, so in practice it reaches this one repo. Keep it that way: don't add `jdad-checker` to other repos, and don't give it org memberships. If it's needed before the repo is public, the scope has to be `repo` (full private-repo access to everything it can reach); swap it for `public_repo` once public. Rotate on the same schedule as the deploy token (`docs/ops/token-rotation.md` in #14).
- **Not recommended now: moving the repo to an organization.** It would allow a fine-grained, single-repo token and org-level rulesets. But a transfer changes the repo URL, which the plugin marketplace entry, the droplet's checkout remote and deploy key, `.mcp.json` docs and every install would follow. Revisit if more bots or repos join.
- The Apps (`jdad-builder`, `jdad-daisy`) are unaffected: installation tokens are already scoped to the installed repo.

## Unverified

- **App approvals.** Whether a GitHub App's approval counts toward `required_approving_review_count` isn't stated in GitHub's docs. Community tests disagree, and seem to depend on the App having write access. That's why Checker is planned as a machine user. Test once with a throwaway PR before relying on it either way.
- **Apps can't approve their own PRs, and can't be code owners.** From community reports and a quoted GitHub staff answer, not official docs.
- The exact ruleset payload was written from the REST docs' parameter list and wasn't sent (no permission, and the repo is private today). If the API rejects a field, the error names it.
- The classic-PAT scope for reviews: `public_repo` should be enough to approve and comment on a public repo. Test it with a throwaway PR before relying on it.
- The integration ID `15368` for GitHub Actions is widely used but not confirmed against this repo; read it from a passing run's check suite before phase 2.

Sources for the App points: [GitHub Docs: approving a PR with required reviews](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews), [NCodeGroup/project-template#460](https://github.com/NCodeGroup/project-template/issues/460), [nateinaction/factory#18](https://github.com/nateinaction/factory/issues/18); rulesets API: [REST API endpoints for rules](https://docs.github.com/en/rest/repos/rules).
