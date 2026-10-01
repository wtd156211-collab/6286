"""parsebot 测试：单元口径 + samples 逐字节验收 + CLI + 规模与确定性。

只读 samples/，临时文件写 tempfile。
"""

import hashlib
import io
import os
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import parsebot  # noqa: E402
from parsebot import dump_result, format_decimal, parse_line  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
CASES = ["common", "mixed", "ambiguous", "invalid"]


def run_engine_bytes(input_path):
    """模拟 CLI 的流式口径，返回 JSONL 字节。"""
    output = io.StringIO()
    with open(input_path, "r", encoding="utf-8-sig", newline="") as stream:
        for line_number, raw in enumerate(stream, 1):
            text = raw.rstrip("\n")
            if text.endswith("\r"):
                text = text[:-1]
            record = {"line": line_number}
            record.update(parse_line(text))
            output.write(dump_result(record) + "\n")
    return output.getvalue().encode("utf-8")


class ParseLineTest(unittest.TestCase):
    def ok(self, text, value, unit, normalized):
        record = parse_line(text)
        self.assertEqual(record["status"], "ok", text)
        self.assertEqual(record["value"], Decimal(value) if not isinstance(value, list)
                         else [Decimal(v) for v in value], text)
        self.assertEqual(record["unit"], unit, text)
        self.assertEqual(record["normalized"], normalized, text)
        self.assertNotIn("code", record)
        self.assertNotIn("candidates", record)

    def reject(self, text, code, candidates=None):
        record = parse_line(text)
        self.assertEqual(record["status"], "reject", text)
        self.assertEqual(record["code"], code, text)
        if candidates is None:
            self.assertNotIn("candidates", record)
        else:
            self.assertEqual(record["candidates"], candidates, text)

    def test_arabic_and_multipliers(self):
        self.ok("1.5万", "15000", None, "15000")
        self.ok("1.5 万", "15000", None, "15000")
        self.ok("3亿", "300000000", None, "300000000")
        self.ok("1,234,567", "1234567", None, "1234567")
        self.ok("0.50", "0.5", None, "0.5")
        self.ok("12,345", "12345", None, "12345")

    def test_chinese_numbers(self):
        self.ok("十五", "15", None, "15")
        self.ok("一百零五", "105", None, "105")
        self.ok("一万两千三百", "12300", None, "12300")
        self.ok("一亿二千万", "120000000", None, "120000000")
        self.ok("三点五", "3.5", None, "3.5")
        self.ok("两千", "2000", None, "2000")
        self.ok("三公里", "3000", "m", "3000 m")

    def test_units_all_dimensions(self):
        self.ok("1千米", "1000", "m", "1000 m")
        self.ok("1厘米", "0.01", "m", "0.01 m")
        self.ok("1毫米", "0.001", "m", "0.001 m")
        self.ok("1千克", "1", "kg", "1 kg")
        self.ok("1克", "0.001", "kg", "0.001 kg")
        self.ok("1吨", "1000", "kg", "1000 kg")
        self.ok("2小时", "7200", "s", "7200 s")
        self.ok("10分钟", "600", "s", "600 s")
        self.ok("2天", "172800", "s", "172800 s")
        self.ok("50%", "50", "%", "50 %")
        self.ok("百分之五十", "50", "%", "50 %")
        self.ok("百分之15", "15", "%", "15 %")

    def test_case_insensitive_and_spacing(self):
        self.ok("5 km", "5000", "m", "5000 m")
        self.ok("3 KM", "3000", "m", "3000 m")
        self.ok("500G", "0.5", "kg", "0.5 kg")
        self.ok("2 H", "7200", "s", "7200 s")
        self.ok("6T", "6000", "kg", "6000 kg")

    def test_ranges(self):
        self.ok("3~5米", ["3", "5"], "m", "3~5 m")
        self.ok("3到5千米", ["3000", "5000"], "m", "3000~5000 m")
        self.ok("1000～2000米", ["1000", "2000"], "m", "1000~2000 m")
        self.ok("3-5", ["3", "5"], None, "3~5")
        self.ok("500米~1千米", ["500", "1000"], "m", "500~1000 m")
        self.ok("3~5", ["3", "5"], None, "3~5")
        self.ok("3米~5", ["3", "5"], "m", "3~5 m")
        self.ok("3~5米", ["3", "5"], "m", "3~5 m")
        self.ok("50%~60", ["50", "60"], "%", "50~60 %")
        self.ok("5~5", ["5", "5"], None, "5~5")

    def test_ambiguous_unit(self):
        self.reject("3m", "AMBIGUOUS_UNIT", ["m", "min"])
        self.reject("5M", "AMBIGUOUS_UNIT", ["m", "min"])
        self.ok("3 米", "3", "m", "3 m")
        self.reject("3米2", "AMBIGUOUS_UNIT", ["m", "m^2"])
        self.reject("3m2", "AMBIGUOUS_UNIT", ["m", "m^2"])
        self.reject("3M2", "AMBIGUOUS_UNIT", ["m", "m^2"])
        self.reject("三米二", "AMBIGUOUS_UNIT", ["m", "m^2"])
        # 区间左段先报错
        self.reject("2m~5m", "AMBIGUOUS_UNIT", ["m", "min"])

    def test_ambiguous_number(self):
        self.reject("1,23", "AMBIGUOUS_NUMBER")
        self.reject("12,34,56", "AMBIGUOUS_NUMBER")
        self.reject("123,", "AMBIGUOUS_NUMBER")

    def test_range_failures(self):
        self.reject("3米~5千克", "UNIT_MISMATCH")
        self.reject("5~3", "INVALID_RANGE")
        self.reject("10千米~5千米", "INVALID_RANGE")
        self.reject("3米~5%", "UNIT_MISMATCH")

    def test_out_of_range_and_negative(self):
        self.reject("-5", "OUT_OF_RANGE")
        self.reject("20000亿", "OUT_OF_RANGE")
        self.reject("10000000000001", "OUT_OF_RANGE")
        self.ok("1000000000000", "1000000000000", None, "1000000000000")

    def test_unparseable(self):
        for text in ["+5", "１２３", "壹佰", "米", "5米千克", "1.2.3",
                     "1e3", "abc", "十万火急", "两两万", "百分之50%", "百分之1.5万"]:
            self.reject(text, "UNPARSEABLE")

    def test_empty(self):
        for text in ["", "   ", "\t", "\u3000", " \t\u3000"]:
            self.assertEqual(parse_line(text), {"status": "empty", "code": "EMPTY"})

    def test_determinism_same_input(self):
        text = "3到5千米"
        self.assertEqual(parse_line(text), parse_line(text))
        self.assertEqual(dump_result({"line": 1, **parse_line(text)}),
                         dump_result({"line": 1, **parse_line(text)}))

    def test_format_decimal(self):
        self.assertEqual(format_decimal(Decimal("0.300")), "0.3")
        self.assertEqual(format_decimal(Decimal("1E+5")), "100000")
        self.assertEqual(format_decimal(Decimal("0")), "0")


class SamplesByteTest(unittest.TestCase):
    def test_expected_byte_for_byte(self):
        for case in CASES:
            with self.subTest(case=case):
                actual = run_engine_bytes(os.path.join(SAMPLES, "inputs", case + ".txt"))
                with open(os.path.join(SAMPLES, "expected", case + ".jsonl"), "rb") as stream:
                    expected = stream.read()
                self.assertEqual(actual, expected)
                self.assertTrue(expected.endswith(b"\n"))
                with open(os.path.join(SAMPLES, "inputs", case + ".txt"),
                          encoding="utf-8") as stream:
                    self.assertEqual(actual.count(b"\n"), stream.read().count("\n"))

    def test_key_order_and_compact_json(self):
        record = {"line": 9, **parse_line("3m")}
        self.assertEqual(dump_result(record),
                         '{"line":9,"status":"reject","code":"AMBIGUOUS_UNIT",'
                         '"candidates":["m","min"]}')
        record = {"line": 3, **parse_line("3000米")}
        self.assertEqual(dump_result(record),
                         '{"line":3,"status":"ok","value":3000,"unit":"m","normalized":"3000 m"}')
        record = {"line": 7, **parse_line("")}
        self.assertEqual(dump_result(record), '{"line":7,"status":"empty","code":"EMPTY"}')


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "parsebot", *args],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )

    def test_usage_error(self):
        result = self.run_cli("only-one-arg")
        self.assertEqual(result.returncode, 2)
        self.assertIn("用法", result.stderr)

    def test_unreadable_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = os.path.join(temp_dir, "out.jsonl")
            result = self.run_cli(os.path.join(temp_dir, "missing.txt"), output)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(os.path.exists(output))

    def test_end_to_end_exit_zero_with_rejects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = os.path.join(temp_dir, "out.jsonl")
            result = self.run_cli(
                os.path.join(SAMPLES, "inputs", "ambiguous.txt"), output)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(output, "rb") as stream:
                expected = stream.read()
            with open(os.path.join(SAMPLES, "expected", "ambiguous.jsonl"), "rb") as stream:
                self.assertEqual(expected, stream.read())


class ScaleTest(unittest.TestCase):
    def run_cli(self, source, target):
        return subprocess.run(
            [sys.executable, "-m", "parsebot", source, target],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )

    def test_scale_budget_and_determinism(self):
        source = os.path.join(SAMPLES, "inputs", "scale.txt")
        with open(source, "rb") as stream:
            self.assertEqual(sum(1 for _ in stream), 100000)
        with open(os.path.join(SAMPLES, "expected", "scale.jsonl"), "rb") as stream:
            expected_bytes = stream.read()
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = [os.path.join(temp_dir, "run%d.jsonl" % i) for i in (1, 2)]
            start = time.perf_counter()
            first = self.run_cli(source, outputs[0])
            elapsed = time.perf_counter() - start
            second = self.run_cli(source, outputs[1])
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertLess(elapsed, 30.0)
            hashes = []
            for output in outputs:
                with open(output, "rb") as stream:
                    data = stream.read()
                hashes.append(hashlib.sha256(data).digest())
                self.assertEqual(sum(1 for _ in data.splitlines()), 100000)
                self.assertEqual(data, expected_bytes)
            self.assertEqual(hashes[0], hashes[1])


if __name__ == "__main__":
    unittest.main()
