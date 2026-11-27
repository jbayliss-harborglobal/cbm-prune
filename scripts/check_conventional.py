"""Reject commit subjects and pull request titles that are not Conventional Commits.

The rules are in AGENTS.md, "Commits and pull requests". Stdlib only, so the
git hook and CI can run it with any Python 3.11+.

Usage:
  check_conventional.py commit-msg <file>     git commit-msg hook
  check_conventional.py pr-title "<title>"    one pull request title
  check_conventional.py range <base>..<head>  every commit subject in a range
"""

import re
import subprocess
import sys

TYPES = "feat|fix|perf|refactor|style|test|docs|build|ci|chore|revert"
# A scope is lower case. A comma joins two scopes, as in `fix(cli,docs): ...`.
SUBJECT = re.compile(rf"^(?:{TYPES})(?:\([a-z0-9][a-z0-9._/,-]*\))?!?: \S")
# Subjects that git writes itself. They stay as written.
GENERATED = re.compile(r'^(?:Merge |Revert "|(?:fixup|squash|amend)! )')

HELP = (
    "Use a Conventional Commit line: type(scope): summary\n"
    f"  type is one of: {TYPES.replace('|', ', ')}\n"
    "  scope is optional and lower case, for example cli, ci or docs\n"
    "  example: fix(cli): keep sizes aligned in narrow terminals\n"
    'See AGENTS.md, "Commits and pull requests".'
)


def subject_error(subject: str) -> str | None:
    if GENERATED.match(subject) or SUBJECT.match(subject):
        return None
    return f"'{subject}' is not a Conventional Commit subject."


def title_error(title: str) -> str | None:
    # The title becomes the merge commit subject, so a generated-looking title
    # such as "Merge branch ..." is refused too.
    if GENERATED.match(title) or not SUBJECT.match(title):
        return f"'{title}' is not a Conventional Commit title."
    return None


def first_line(message: str) -> str:
    for line in message.splitlines():
        if line.strip() and not line.startswith("#"):
            return line.strip()
    return ""


def fail(*lines: str) -> int:
    print("\n".join(lines), file=sys.stderr)
    return 1


def check_range(revisions: str) -> int:
    log = subprocess.run(
        ["git", "log", "--format=%h %s", revisions],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    errors = [
        f"Commit {sha}: {error}"
        for sha, _, subject in (line.partition(" ") for line in log.splitlines())
        if (error := subject_error(subject))
    ]
    return fail(*errors, HELP) if errors else 0


def main(argv: list[str]) -> int:
    match argv:
        case ["commit-msg", path]:
            with open(path, encoding="utf-8") as file:
                error = subject_error(first_line(file.read()))
            return fail(f"Commit rejected: {error}", HELP) if error else 0
        case ["pr-title", title]:
            error = title_error(title.strip())
            return fail(error, HELP) if error else 0
        case ["range", revisions]:
            return check_range(revisions)
    return fail(__doc__ or "")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
