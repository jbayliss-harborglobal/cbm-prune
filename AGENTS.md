# Agent Instructions

These instructions apply to every agent working in this repository.

## Project

`cbm-prune` is a single-module, stdlib-only Python CLI in
`src/cbm_prune/__init__.py`. It calls `codebase-memory-mcp cli` and never
reads the Codebase Memory cache files directly. Keep it free of runtime
dependencies.

- Preview is the default. Only `--delete` changes the index, and agents never
  run `--delete` against a real index unless the user asks in that session.
- The preview is the review for a destructive command. Its summary must account
  for every stale project, and group rows must sum to the total row.
- Colour and bars appear only on a terminal with `NO_COLOR` unset. Piped output
  stays plain text.

## Checks

Run `mise run check` before committing. It runs the same steps as CI:
`ruff check`, `ruff format --check`, `ty check`, the unittest suite in
`tests/`, and `uv build`. `mise run format` applies ruff formatting.

Tests use a fake `codebase-memory-mcp` script, so they never touch the real
index. Add a test case there for any change to scanning, grouping or deletion.

## Branches

- `main` is the only long-lived branch. There is no `dev` branch.
- Cut one short-lived branch from `main` per change, named
  `<type>/<short-slug>`, for example `fix/narrow-terminal-sizes`.
- Open a pull request into `main`. A human approves and merges it. Agents never
  approve, enable auto-merge for, or merge a pull request into `main`.
- Pull requests merge with a merge commit only. Squash and rebase merging are
  turned off in the repository settings. Never force-push `main`.
- GitHub deletes the remote branch when its pull request merges. Delete the
  local branch and any worktree for it afterwards.

## Commits and pull requests

Every commit subject and every pull request title is a
[Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/) line:
`type(scope): summary`.

- `type` is one of `feat`, `fix`, `perf`, `refactor`, `style`, `test`, `docs`,
  `build`, `ci`, `chore` or `revert`.
- `scope` is optional and lower case, for example `cli`, `ci` or `docs`.
- `summary` is the outcome in the imperative mood, with no full stop.
- For a breaking change, write `!` before the colon: `feat(cli)!: ...`.

The pull request title becomes the merge commit subject on `main`.

`scripts/check_conventional.py` applies these rules in two places:

- The `commit-msg` hook in `.githooks/` rejects a bad subject. Turn it on once
  per clone with `mise run hooks`.
- The `conventional` CI job checks the pull request title and every commit
  subject in the pull request. It runs again when the title is edited.
