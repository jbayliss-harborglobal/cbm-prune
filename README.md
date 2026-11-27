# cbm-prune

Find Codebase Memory projects whose root paths are missing, such as indexes of
Git worktrees that were since removed, and show how much cache space they use.
The default command is a dry run. With `--delete`, it removes those projects
from the Codebase Memory index.

## Run it

You need [uv](https://docs.astral.sh/uv/) and `codebase-memory-mcp` on your
PATH. The CLI was checked with `codebase-memory-mcp` 0.12.1.

The repository is private, so uv fetches it over SSH with your GitHub access.
Run it once without installing:

```sh
uvx --from git+ssh://git@github.com/jbayliss-harborglobal/cbm-prune cbm-prune
```

Or install it as a user command:

```sh
uv tool install git+ssh://git@github.com/jbayliss-harborglobal/cbm-prune
cbm-prune
```

`uv tool upgrade cbm-prune` fetches the latest `main`.

## Output

The preview prints a headline with the stale project count and the total
reclaimable size, then one row per location:

```text
Dry run. 114 of 123 indexed projects have a missing root path.
Reclaimable cache space: 88.8 GiB (95,307,169,792 bytes)

  LOCATION                                      PROJECTS  FOLDERS       SIZE
  ~/.t3/worktrees/Integration as a Service            86       64   70.6 GiB
  ~/Projects                                           9        9    9.8 GiB
  /private/tmp (temporary)                             6        6    4.4 GiB
  Total                                              114       92   88.8 GiB
```

A location is the parent directory of each missing root. Roots under temporary
directories share one location. Several projects can index the same root, so
`FOLDERS` can be smaller than `PROJECTS`. Sizes are the index sizes that
Codebase Memory reports. On a terminal, each row also gets a bar.

| Option | Effect |
| --- | --- |
| `-l`, `--list` | List each missing folder under its location, with `×N` when N projects index it. |
| `-v`, `--verbose` | Like `--list`, and add each project name and branch. |
| `--delete` | Delete the stale projects, then show the same table for what was removed. Skipped and failed projects are listed by name. The exit status is 1 if any deletion failed. |
| `--bin PATH` | Use this `codebase-memory-mcp` executable. `CBM_BIN` sets the default. |

A project is skipped if its root exists again when it is about to be deleted.

## Develop

Install [mise](https://mise.jdx.dev/), then run these from the checkout:

```sh
mise install
mise run hooks
mise run install
```

`mise run install` puts an editable `cbm-prune` on your PATH that reads from
this checkout.

| Task | Action |
| --- | --- |
| `mise run preview` | Run the checkout's CLI with `--list`. |
| `mise run prune` | Run the checkout's CLI with `--delete`. |
| `mise run check` | Run every CI check: ruff, ty, tests and package build. |
| `mise run format` | Format code with ruff. |
| `mise run hooks` | Turn on the commit message check for this clone. |

Contribution rules for branches, commits and pull requests are in
[AGENTS.md](AGENTS.md).
