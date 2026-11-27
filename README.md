# cbm-prune

Find Codebase Memory projects whose root paths are missing. The default command
previews the stale entries. With `--delete`, it removes those entries from the
Codebase Memory index.

The preview lists each stale project with its original path, branch when
available, and index size. This includes indexes for Git worktrees whose
directories have been removed. After a cleanup, the command lists the caches
it removed and totals their last reported index sizes. The figures come from
Codebase Memory's database statistics and estimate the space reclaimed.

## Install and run

Install [mise](https://mise.jdx.dev/) and have `codebase-memory-mcp` on your PATH.
The CLI was checked with `codebase-memory-mcp` 0.12.1.

Run these commands from the checkout:

```sh
mise install
mise run install
```

The install task uses uv to put `cbm-prune` on your user PATH. The editable
install reads from this checkout.

```sh
cbm-prune
cbm-prune --delete
```

Use `--bin /path/to/codebase-memory-mcp` or set `CBM_BIN` if the Codebase Memory
executable is installed elsewhere.

## mise tasks

| Task | Action |
| --- | --- |
| `mise run preview` | List stale projects. |
| `mise run prune` | Remove stale projects from the index. |
| `mise run install` | Install the user CLI from this checkout. |
| `mise run check` | Build the package and run its CLI help. |
