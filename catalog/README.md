# Catalog

The one source for JDAD's skills and rules (roadmap P1.4, [ADR 0001](../docs/adr/0001-canonical-skill-format-and-compilers.md)). Edit these files, not the per-tool copies.

## `skills/<name>/SKILL.md`

An [Agent Skills](https://agentskills.io) skill. The frontmatter uses only the spec's keys:

| Key | Required | Rule |
| --- | --- | --- |
| `name` | yes | Equals the directory name; lowercase letters, digits and single hyphens; at most 64 characters |
| `description` | yes | 1 to 1024 characters. Say what the skill does and when to use it, so it auto-triggers |
| `license` | no | A license name or a pointer to a bundled file |
| `compatibility` | no | At most 500 characters |
| `metadata` | no | A mapping. Tool-specific extras go here, e.g. `metadata.claude.disable-model-invocation` |
| `allowed-tools` | no | Space-separated tool names |

Any other top-level key fails. The body (after the frontmatter) stays under 500 lines.

## `rules/<name>.md`

An always-on or glob-scoped rule for tools that support them (Cursor `.mdc` and others, compiled in P1.5). Frontmatter keys: `description` (required), `globs` (a string or a list) and `alwaysApply` (`true` or `false`). There are none yet.

## Checks

`./verify` runs `python -m jdad.catalog validate` (`src/jdad/catalog.py`, stdlib only) and the reference validator, `agentskills validate` from `skills-ref==0.1.1`, on every skill.

Until P1.5's `jdad build` generates them, the plugin's `skills/<name>/SKILL.md` files are hand copies. `tests/test_catalog.py` fails if one differs from its catalog source.
