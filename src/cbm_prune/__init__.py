import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


class CbmError(Exception):
    pass


class Project(NamedTuple):
    name: str
    root: Path
    size_bytes: int
    branch: str | None


def cbm_json(binary: str, *arguments: str) -> dict:
    command = subprocess.run(
        [binary, "cli", *arguments], capture_output=True, text=True, check=False
    )
    if command.returncode:
        detail = command.stderr.strip() or command.stdout.strip()
        raise CbmError(detail or f"CBM exited with status {command.returncode}")

    try:
        response = json.loads(command.stdout)
    except json.JSONDecodeError as error:
        raise CbmError("CBM did not return valid JSON") from error
    if not isinstance(response, dict):
        raise CbmError("CBM did not return a JSON object")
    return response


def parse_project(entry: object) -> Project | None:
    if not isinstance(entry, dict):
        raise CbmError("Invalid project in CBM list response")
    name = entry.get("name")
    root = entry.get("root_path")
    if root is None or root == "":
        return None
    if not isinstance(name, str) or not name or not isinstance(root, str):
        raise CbmError("Invalid project name or root path in CBM list response")
    path = Path(root)
    if not path.is_absolute():
        raise CbmError(f"CBM returned a relative root path for {name}")
    size_bytes = entry.get("size_bytes")
    branch = entry.get("branch")
    if type(size_bytes) is not int or size_bytes < 0:
        raise CbmError(f"CBM returned an invalid index size for {name}")
    if branch is not None and not isinstance(branch, str):
        raise CbmError(f"CBM returned an invalid branch for {name}")
    return Project(name, path, size_bytes, branch)


def scan_projects(binary: str) -> tuple[int, list[Project]]:
    count = offset = 0
    stale = []
    while True:
        page = cbm_json(
            binary, "list_projects", "--format", "json", "--detail", "stats",
            "--offset", str(offset),
        )
        entries = page.get("projects")
        has_more = page.get("has_more")
        if not isinstance(entries, list) or not isinstance(has_more, bool):
            raise CbmError("Invalid project list or pagination in CBM list response")
        count += len(entries)
        for entry in entries:
            project = parse_project(entry)
            if project is not None and root_is_missing(project.root):
                stale.append(project)
        if not has_more:
            return count, stale
        next_offset = page.get("next_offset")
        if type(next_offset) is not int or next_offset <= offset:
            raise CbmError("Invalid next offset in CBM list response")
        offset = next_offset


def root_is_missing(root: Path) -> bool:
    try:
        root.stat()
    except (FileNotFoundError, NotADirectoryError):
        return True
    return False


def format_size(size_bytes: int) -> str:
    for unit, power in (("TiB", 40), ("GiB", 30), ("MiB", 20), ("KiB", 10)):
        if size_bytes >= 1 << power:
            return f"{size_bytes / (1 << power):.2f} {unit} ({size_bytes:,} bytes)"
    return f"{size_bytes:,} bytes"


def show_candidates(count: int, stale: list[Project]) -> None:
    print(f"{len(stale)} of {count} indexed projects have a missing root path:")
    for project in stale:
        branch = f" [{project.branch}]" if project.branch else ""
        print(f"  {project.name}{branch}  {format_size(project.size_bytes)}")
        print(f"    {project.root}")
    total = sum(project.size_bytes for project in stale)
    print(f"Candidate cache space (CBM-reported index size): {format_size(total)}")


def delete_project(binary: str, project: Project) -> None:
    reply = cbm_json(binary, "--json", "delete_project", "--project", project.name)
    if reply.get("isError") is not False:
        raise CbmError(json.dumps(reply, ensure_ascii=False))


def prune_projects(binary: str, stale: list[Project]) -> int:
    deleted = []
    failures = 0
    for project in stale:
        try:
            if not root_is_missing(project.root):
                print(f"skipped  {project.name} (root exists again)")
                continue
            delete_project(binary, project)
        except (CbmError, OSError) as error:
            print(f"FAILED   {project.name}: {error}", file=sys.stderr)
            failures += 1
        else:
            deleted.append(project)
            print(f"deleted  {project.name}  {format_size(project.size_bytes)}")
    total = sum(project.size_bytes for project in deleted)
    print(f"Removed {len(deleted)} of {len(stale)} candidate project caches.")
    print(f"Removed cache space (CBM-reported index size): {format_size(total)}")
    return int(bool(failures))


def cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove codebase-memory-mcp projects whose root paths are missing."
    )
    parser.add_argument(
        "--bin",
        default=os.environ.get("CBM_BIN", "codebase-memory-mcp"),
        help="codebase-memory-mcp executable (default: $CBM_BIN or PATH)",
    )
    parser.add_argument("--delete", action="store_true", help="delete stale projects")
    return parser


def main() -> int:
    parser = cli_parser()
    args = parser.parse_args()

    binary = shutil.which(args.bin)
    if binary is None:
        parser.exit(1, f"cbm-prune: binary not found: {args.bin}\n")
    try:
        count, stale = scan_projects(binary)
    except (CbmError, OSError) as error:
        parser.exit(1, f"cbm-prune: {error}\n")

    if not stale:
        print(f"{count} indexed projects and no stale entries.")
        return 0
    stale.sort(key=lambda project: (-project.size_bytes, project.name))
    show_candidates(count, stale)
    if args.delete:
        return prune_projects(binary, stale)
    print("\nDry run. Re-run with --delete to remove them.")
    return 0
