import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

TEMP_ROOTS = tuple(
    Path(root) for root in ("/private/tmp", "/tmp", "/private/var/folders", "/var/folders")
)


class CbmError(Exception):
    pass


class Project(NamedTuple):
    name: str
    root: Path
    size_bytes: int
    branch: str | None


@dataclass
class Folder:
    """One root path; several CBM projects can index the same root."""

    label: str
    projects: list[Project] = field(default_factory=list)

    @property
    def size_bytes(self) -> int:
        return sum(project.size_bytes for project in self.projects)


@dataclass
class Group:
    location: str
    folders: dict[Path, Folder] = field(default_factory=dict)

    @property
    def size_bytes(self) -> int:
        return sum(folder.size_bytes for folder in self.folders.values())

    @property
    def project_count(self) -> int:
        return sum(len(folder.projects) for folder in self.folders.values())


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
            binary,
            "list_projects",
            "--format",
            "json",
            "--detail",
            "stats",
            "--offset",
            str(offset),
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


def display_path(path: Path) -> str:
    home = Path.home()
    if path == home:
        return "~"
    if path.is_relative_to(home):
        return f"~/{path.relative_to(home)}"
    return str(path)


def placement(root: Path) -> tuple[str, str]:
    """Return the location heading and the folder label shown under it.

    Temporary directories collapse into one location, because their parents
    are usually unique per session and would each form a one-row group.
    """
    for temp in TEMP_ROOTS:
        if root.is_relative_to(temp) and root != temp:
            return f"{temp} (temporary)", str(root.relative_to(temp))
    return display_path(root.parent), root.name or str(root)


def group_projects(projects: list[Project]) -> list[Group]:
    groups: dict[str, Group] = {}
    for project in projects:
        location, label = placement(project.root)
        group = groups.setdefault(location, Group(location))
        group.folders.setdefault(project.root, Folder(label)).projects.append(project)
    for group in groups.values():
        group.folders = dict(
            sorted(group.folders.items(), key=lambda item: (-item[1].size_bytes, item[1].label))
        )
        for folder in group.folders.values():
            folder.projects.sort(key=lambda project: (-project.size_bytes, project.name))
    return sorted(groups.values(), key=lambda group: (-group.size_bytes, group.location))


def format_size(size_bytes: int) -> str:
    for unit, power in (("TiB", 40), ("GiB", 30), ("MiB", 20), ("KiB", 10)):
        if size_bytes >= 1 << power:
            return f"{size_bytes / (1 << power):.1f} {unit}"
    return f"{size_bytes} B"


def exact_size(size_bytes: int) -> str:
    return f"{format_size(size_bytes)} ({size_bytes:,} bytes)"


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def shorten(text: str, width: int) -> str:
    """Cut the middle of text so both ends of a path stay visible."""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    head = (width - 1) // 2
    return f"{text[:head]}…{text[len(text) - (width - 1 - head) :]}"


class Output:
    """Writes aligned plain text, adding colour and bars only on a terminal."""

    BAR_WIDTH = 20
    SIZE_WIDTH = 9

    def __init__(self, stream=None) -> None:
        self.stream = stream or sys.stdout
        self.rich = self.stream.isatty() and "NO_COLOR" not in os.environ
        self.width = max(60, shutil.get_terminal_size((100, 24)).columns)

    def style(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.rich and text else text

    def line(self, text: str = "") -> None:
        print(text, file=self.stream)

    def bar(self, size_bytes: int, largest: int) -> str:
        if not self.rich or not largest:
            return ""
        filled = max(1, round(self.BAR_WIDTH * size_bytes / largest)) if size_bytes else 0
        return (
            "  " + self.style("█" * filled, "36") + self.style("░" * (self.BAR_WIDTH - filled), "2")
        )

    def summary(self, groups: list[Group], heading: str) -> None:
        """One row per location; the rows sum to the total row."""
        counts = ("PROJECTS", "FOLDERS")
        fixed = 2 + sum(len(name) + 2 for name in counts) + self.SIZE_WIDTH + 2
        fixed += self.BAR_WIDTH + 2 if self.rich else 0
        longest = max([len(group.location) for group in groups] + [len(heading)])
        width = max(20, min(longest, 60, self.width - fixed))
        largest = max(group.size_bytes for group in groups)

        def row(label: str, projects: str, folders: str, size: str) -> str:
            return (
                f"  {shorten(label, width):<{width}}  {projects:>{len(counts[0])}}"
                f"  {folders:>{len(counts[1])}}  {size:>{self.SIZE_WIDTH}}"
            )

        self.line(self.style(row(heading, *counts, "SIZE"), "1"))
        for group in groups:
            self.line(
                row(
                    group.location,
                    str(group.project_count),
                    str(len(group.folders)),
                    format_size(group.size_bytes),
                )
                + self.bar(group.size_bytes, largest)
            )
        total = sum(group.size_bytes for group in groups)
        projects = sum(group.project_count for group in groups)
        folders = sum(len(group.folders) for group in groups)
        self.line(self.style(row("Total", str(projects), str(folders), format_size(total)), "1"))

    def folders(self, groups: list[Group], names: bool) -> None:
        for group in groups:
            self.line()
            self.line(
                self.style(group.location, "1")
                + self.style(
                    f"  {plural(group.project_count, 'project')} · {format_size(group.size_bytes)}",
                    "2",
                )
            )
            for folder in group.folders.values():
                copies = len(folder.projects)
                suffix = f"  ×{copies}" if copies > 1 else ""
                label = shorten(folder.label, self.width - self.SIZE_WIDTH - 4 - len(suffix))
                self.line(
                    f"  {format_size(folder.size_bytes):>{self.SIZE_WIDTH}}  {label}"
                    + self.style(suffix, "33")
                )
                if names:
                    for project in folder.projects:
                        branch = f" [{project.branch}]" if project.branch else ""
                        text = f"{project.name}{branch}  {format_size(project.size_bytes)}"
                        indent = " " * (self.SIZE_WIDTH + 6)
                        self.line(indent + self.style(shorten(text, self.width - len(indent)), "2"))


def preview(out: Output, count: int, stale: list[Project], args: argparse.Namespace) -> None:
    groups = group_projects(stale)
    total = sum(project.size_bytes for project in stale)
    out.line(
        out.style("Dry run.", "1;33")
        + f" {len(stale)} of {count} indexed projects have a missing root path."
    )
    out.line(f"Reclaimable cache space: {out.style(exact_size(total), '1')}")
    out.line()
    out.summary(groups, "LOCATION")
    if args.list or args.verbose:
        out.folders(groups, names=args.verbose)
    out.line()
    hints = [] if args.list or args.verbose else ["--list to show each folder"]
    if not args.verbose:
        hints.append("--verbose to add project names")
    hints.append("--delete to remove them")
    out.line(out.style(f"Use {', '.join(hints)}.", "2"))


def delete_project(binary: str, project: Project) -> None:
    reply = cbm_json(binary, "--json", "delete_project", "--project", project.name)
    if reply.get("isError") is not False:
        raise CbmError(json.dumps(reply, ensure_ascii=False))


def prune(out: Output, binary: str, stale: list[Project], args: argparse.Namespace) -> int:
    errors = Output(sys.stderr)
    progress = errors.stream.isatty()
    total = sum(project.size_bytes for project in stale)
    out.line(f"Deleting {plural(len(stale), 'stale project')} ({format_size(total)}).")

    deleted: list[Project] = []
    skipped: list[Project] = []
    failed: list[tuple[Project, str]] = []
    for number, project in enumerate(stale, 1):
        if progress:
            errors.stream.write(f"\r\033[K  {number}/{len(stale)}  {shorten(project.name, 60)}")
            errors.stream.flush()
        try:
            if not root_is_missing(project.root):
                skipped.append(project)
                continue
            delete_project(binary, project)
        except (CbmError, OSError) as error:
            failed.append((project, str(error)))
        else:
            deleted.append(project)
    if progress:
        errors.stream.write("\r\033[K")

    freed = sum(project.size_bytes for project in deleted)
    out.line(
        out.style(f"Removed {len(deleted)} of {len(stale)}", "1;32")
        + f" stale projects. Freed {out.style(exact_size(freed), '1')}."
    )
    if deleted:
        groups = group_projects(deleted)
        out.line()
        out.summary(groups, "REMOVED FROM")
        if args.list or args.verbose:
            out.folders(groups, names=args.verbose)
    if skipped:
        out.line()
        out.line(out.style(f"Skipped {len(skipped)} (root exists again):", "33"))
        for project in skipped:
            out.line(f"  {project.name}  {display_path(project.root)}")
    if failed:
        errors.line()
        errors.line(errors.style(f"FAILED {len(failed)}:", "1;31"))
        for project, error in failed:
            errors.line(f"  {project.name}  {display_path(project.root)}")
            errors.line(f"    {error}")
    return int(bool(failed))


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
    parser.add_argument(
        "-l", "--list", action="store_true", help="list each stale folder under its location"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="like --list, and add each project name and branch",
    )
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

    out = Output()
    if not stale:
        out.line(f"{plural(count, 'indexed project')} and no stale entries.")
        return 0
    if args.delete:
        return prune(out, binary, stale, args)
    preview(out, count, stale, args)
    return 0
