"""验收测试：只读 samples/，引擎输出须与期望文件逐字节一致。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / "samples" / "inputs"
EXPECTED = ROOT / "samples" / "expected"

sys.path.insert(0, str(ROOT))

from parsebot import dumps, parse_line  # noqa: E402

CASES = ["common", "mixed", "ambiguous", "invalid", "scale"]


def read_lines(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        lines = []
        for raw in handle:
            if raw.endswith("\n"):
                raw = raw[:-1]
            if raw.endswith("\r"):
                raw = raw[:-1]
            lines.append(raw)
        return lines


def run_case(case: str) -> list[str]:
    rendered = []
    for number, text in enumerate(read_lines(INPUTS / f"{case}.txt"), 1):
        rendered.append(dumps({"line": number, **parse_line(text)}))
    return rendered


class SamplesTest(unittest.TestCase):
    def test_expected_match(self):
        for case in CASES:
            with self.subTest(case=case):
                expected = (EXPECTED / f"{case}.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                self.assertEqual(expected, run_case(case))

    def test_line_count_matches_input(self):
        for case in CASES:
            with self.subTest(case=case):
                inputs = read_lines(INPUTS / f"{case}.txt")
                expected = (EXPECTED / f"{case}.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
                self.assertEqual(len(inputs), len(expected))

    def test_determinism(self):
        self.assertEqual(run_case("scale"), run_case("scale"))

    def test_result_schema(self):
        for case in CASES:
            for line in (EXPECTED / f"{case}.jsonl").read_text(
                encoding="utf-8"
            ).splitlines():
                record = json.loads(line)
                keys = list(record)
                self.assertEqual(keys[0], "line")
                self.assertEqual(keys[1], "status")
                if record["status"] == "ok":
                    self.assertEqual(
                        keys, ["line", "status", "value", "unit", "normalized"]
                    )
                elif record["status"] == "empty":
                    self.assertEqual(keys, ["line", "status", "code"])
                    self.assertEqual(record["code"], "EMPTY")
                else:
                    self.assertEqual(record["status"], "reject")
                    if "candidates" in record:
                        self.assertEqual(record["code"], "AMBIGUOUS_UNIT")
                        self.assertEqual(
                            record["candidates"], sorted(record["candidates"])
                        )


class CliTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "parsebot", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_end_to_end_bytes(self):
        for case in ["common", "mixed", "ambiguous", "invalid"]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "out.jsonl"
                process = self.run_cli(str(INPUTS / f"{case}.txt"), str(output))
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(
                    output.read_bytes(), (EXPECTED / f"{case}.jsonl").read_bytes()
                )

    def test_usage_error(self):
        process = self.run_cli()
        self.assertEqual(process.returncode, 2)

    def test_unreadable_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            process = self.run_cli(
                str(Path(tmp) / "missing.txt"), str(Path(tmp) / "o.jsonl")
            )
            self.assertEqual(process.returncode, 1)


if __name__ == "__main__":
    unittest.main()
