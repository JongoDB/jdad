# Pre-public scrub, 2026-11-22

- Why: Jon decided on 2026-11-22 (3:16 PM ET) to make `JongoDB/jdad` public, with the rule "no proprietary or sensitive data in the repo; the KB is not confidential". This is the check before that happens. Card: JON-1338.
- Scope: the full git history (every branch and every GitHub pull-request ref), plus every PR title, body, comment and review, because those become public with the repo.
- Nothing was changed: no history rewrite, no setting, no visibility change.
- Result: **no real secret in history or in PR text.** One scanner hit is a false positive. Nothing proprietary found. Three things need a decision or an order of operations before the switch; see [Recommendation](#recommendation).

## Secret scans

The scan target was a fresh `git clone --mirror` of `https://github.com/JongoDB/jdad.git`: 29 refs (12 `refs/heads`, 17 `refs/pull`), 39 commits.

| Tool | How it ran | Result |
| --- | --- | --- |
| gitleaks 8.30.1 (host install) | `gitleaks git --log-opts="--all" --redact`, then again with `--all -m` so merge commits are diffed too (29 and 39 commits) | 1 finding (reported twice with `-m`), a false positive (below) |
| trufflehog 3.100.0 (`trufflesecurity/trufflehog@sha256:8fd07ea46a3f…5a6b`) | `git file:///repo --no-verification`, in a container with `--network none`, on a non-bare copy where each PR ref was also a branch (29 branches) | 0 findings, 551 chunks |
| gitleaks `dir` and trufflehog `filesystem` | over the text of all 11 PRs: titles, bodies, comments, reviews | 0 findings |
| pattern grep | `Bearer <16+ chars>` and 64-hex strings in PR text | only image digests in pasted build logs (PR #2) |

`--no-verification` means no candidate string was sent to any provider to test it.

**The one hit.** `generic-api-key` at `docs/evidence/p0.5/droplet.txt:55`, commit 9d4bebdb6d, only on the PR #5 branch (`docs/p0.5-deployed`). The line is `key:  <64 hex>` under `cert pubkey sha256 vs key pubkey sha256`: the SHA-256 of the private key's **public** half, printed to show it equals the certificate's (line 54 has the same value). The certificate is public by definition, so this is **not a secret**.

## Sensitivity review

Searched with `git log --all -p` over every blob in history.

| Item | Where | Sensitive? |
| --- | --- | --- |
| Commit identities | `JongoDB <…@users.noreply.github.com>` (35), `GitHub <noreply@github.com>` (11, merges), `Daisy <…@grokbot>` (32, not a routable domain) | No personal email in history |
| Jon's name | `plugin.json` / `marketplace.json` author, ADRs, ROADMAP decisions | Intended to be public as the author. Jon should confirm he's fine with his name on the decisions recorded in ROADMAP and the ADRs |
| IP addresses | Loopback, `0.0.0.0`, Cloudflare's published ranges (fixtures), RFC 5737 documentation addresses, and `192.168.1.20` (a made-up LAN example in an old README, gone from `main`) | No |
| The droplet's public IP | not found anywhere | n/a |
| Hostnames | `jdad-mcp.jondevs.com` (159), `*.jondevs.com` (the cert SAN in the evidence) | Public DNS anyway |
| Internal paths | `/home/ubuntu/.config/jdad/tls` (evidence: the droplet's default user), `/root/.local`, `/home/...` in docs | Generic; no |
| Internal references | Linear IDs (`JON-13xx`) and the workspace slug `jongodb`; "Daisy", "Checker", "Grok Bot chat"; a Linear link-back bot comment on each PR | Not secret: Linear links will 404 for the public. The PR link-back comments repeat card descriptions; those cards hold nothing sensitive today |
| Origin certificate details | `docs/evidence/p0.5/droplet.txt` (PR #5 branch): SHA-256 fingerprint, SANs, validity | **Origin-discovery key** while the origin is open; see Recommendation 2 |
| Cloudflare response headers | `cf-ray` IDs (show the PDX and EWR colos), NEL report URLs | Sent to every visitor anyway; no |
| GitHub SSH host keys | README | Published by GitHub; no |
| Anything proprietary (company names, customer data, internal code) | none found | No |

### Third-party text and licence risk

- `sources/2026-11-22-breakingbreach-app-performance.md`: the 31 item titles from an Instagram reel (about 120 words of short phrases such as "Fix N+1 queries"), with the author and link. That's a factual list with attribution, not creative prose; low risk.
- `docs/research/*.md`: original summaries with short attributed quotes. The longest total per file is 74 words (`claude-code.md`); no block quotes. Low risk.
- The ingestion rule in `CLAUDE.md` asks for "a verbatim (or as-close-as-possible) record" of each source. That's fine for lists like the one above. **For future sources (talk transcripts, articles), verbatim copies of a whole work in a public repo would be a real copyright problem.** P1.3 should change the rule to "the extractable practices, in short quotes or paraphrase, with the link", and the KB lint (PR #8) could warn on very long `sources/` files.
- **No LICENSE file.** Public without a licence means "all rights reserved": people can read it, but can't reuse the code or the rules. This doesn't block going public. Jon should pick a licence (for example MIT for code, CC BY 4.0 for `practices/` and docs).

## The red-team report and the P0.5 evidence

**History is the problem, not `HEAD`.** Moving a file out of the repo after the fact doesn't unpublish it: every commit stays readable once the repo is public. The real choices are to fix first, or to rewrite history, and the brief rules out a rewrite without a decision.

- **H3** (`docs/reviews/2026-11-22-red-team.md`, on `main` since caf3d94) explains that the origin answers on 443 from anywhere and that the certificate SAN lets scanners link the IP to the zone. **M3** gives the symlink path through `_resolve_file` and the listing tools.
- **`docs/evidence/p0.5/droplet.txt`** (PR #5, not merged, but its branch becomes public too) has the certificate's exact SHA-256 fingerprint. That is the search key to find the droplet's IP in internet-wide scan data while 443 is open.
- **M3** needs repo write access to exploit, and PR #8 removes it (the resolver serves only `<id>.md`, symlinks fail the lint, listing tools are linted). Low risk once #8 merges.
- **H3** matters until the host firewall from PR #7 is applied and checked from outside. After that, a non-Cloudflare client can't complete a handshake, so the report and the fingerprint describe a closed path. The IP may already be in scan history, but it no longer answers.

## Recommendation

1. **Go public only after the gating fixes land:**
   - PR #7 is merged, Daisy has applied `deploy/firewall-cloudflare.sh install` on the droplet, and the "from outside Cloudflare, 443 times out" check in PR #7 passes over IPv4 (and IPv6 if the droplet has it).
   - PR #8 is merged (H4, which also closes M3's path).
   - Then add one line under H3 and M3 in the red-team report: "Fixed in #7 (firewall applied <date>) / #8". No redaction needed.
2. **PR #5 (Daisy's):** before merging, consider replacing the certificate fingerprint and the two public-key hashes in `droplet.txt` with a sentence ("the certificate's public key matches the key file; fingerprint recorded off-repo"). They prove nothing that sentence doesn't, and they're the scan-search key. This is optional once step 1 is done, and it's Daisy's PR.
3. **If Jon wants the repo public before step 1:** the only clean option is a history rewrite to drop the red-team report and the evidence branch. That's destructive and needs Jon's explicit decision. I don't recommend it; waiting for #7 and #8 is shorter.
4. **Licence** (Jon's call; doesn't block going public) and the **verbatim-sources rule** change (P1.3).
5. **Right after the switch:** apply the `main` ruleset and start the bot-identity work in [docs/ops/github-protection-plan.md](../ops/github-protection-plan.md). Branch protection is free only once the repo is public, and until then "nobody merges their own PR" is policy only.

## Unverified

- That GitHub's PR text API returns everything that becomes public. I scanned titles, bodies, comments and reviews; I didn't scan inline review-comment threads or the Linear link-back previews.
- Whether the droplet's IP is already in public scan data. I didn't look it up, so the IP never entered any search.
- The licence and copyright points are a reading of the content, not legal advice.
- gitleaks and trufflehog are pattern and entropy tools; they don't prove absence. The manual review covered the categories listed above.
