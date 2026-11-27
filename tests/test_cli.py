"""End-to-end checks of the cbm-prune CLI against a fake codebase-memory-mcp."""

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

FAKE_CBM = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys
    from pathlib import Path

    root = Path(__file__).parent
    args = sys.argv[1:]
    if args[1] == "list_projects":
        offset = args[-1]
        if offset == "0":
            entries = [("wt-a", "gone/wt-a", 3072), ("wt-a-again", "gone/wt-a", 1024),
                       ("restored", "gone/restored", 4096), ("live", ".", 32768)]
            cursor = {{"has_more": True, "next_offset": 4}}
        elif os.environ.get("BAD_CURSOR"):
            print(json.dumps({{"projects": [], "has_more": True, "next_offset": 4}}))
            sys.exit()
        else:
            (root / "gone" / "restored").mkdir(parents=True, exist_ok=True)
            entries = [("failed", "other/missing", 1024), ("later", "other/gone-too", 512)]
            cursor = {{"has_more": False}}
        print(json.dumps(dict(cursor, projects=[
            dict(name=name, root_path=str(root / path), size_bytes=size, branch="fixture")
            for name, path, size in entries
        ])))
    else:
        name = args[-1]
        with (root / "calls").open("a") as calls:
            print(name, file=calls)
        print(json.dumps({{"isError": name == "failed"}}))
    """
)


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.fake = self.root / "fake-cbm"
        self.fake.write_text(FAKE_CBM.format(python=sys.executable))
        self.fake.chmod(0o755)
        self.calls = self.root / "calls"

    def run_cli(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, cbm_prune; sys.exit(cbm_prune.main())",
                "--bin",
                str(self.fake),
                *args,
            ],
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "COLUMNS": "80", **env},
        )

    def deleted_names(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_preview_groups_by_location_without_deleting(self) -> None:
        result = self.run_cli("--list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("5 of 6 indexed projects", result.stdout)
        self.assertIn("(9,728 bytes)", result.stdout)
        self.assertRegex(result.stdout, r"Total +5 +4 +9\.5 KiB")
        self.assertRegex(result.stdout, r"4\.0 KiB  \S*gone/wt-a  ×2")
        self.assertNotIn("live", result.stdout)
        self.assertNotIn("\033[", result.stdout)
        self.assertEqual(self.deleted_names(), [])

    def test_verbose_shows_project_names(self) -> None:
        result = self.run_cli("--verbose")

        self.assertIn("wt-a-again [fixture]", result.stdout)

    def test_delete_reports_removed_skipped_and_failed(self) -> None:
        result = self.run_cli("--delete")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.deleted_names(), ["wt-a", "wt-a-again", "failed", "later"])
        self.assertIn("Removed 3 of 5 stale projects", result.stdout)
        self.assertIn("(4,608 bytes)", result.stdout)
        self.assertRegex(result.stdout, r"Skipped 1 .*\n  restored ")
        self.assertRegex(result.stderr, r"FAILED 1:\n  failed ")

    def test_invalid_pagination_stops_before_deleting(self) -> None:
        result = self.run_cli("--delete", BAD_CURSOR="1")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid next offset", result.stderr)
        self.assertEqual(self.deleted_names(), [])


if __name__ == "__main__":
    unittest.main()
