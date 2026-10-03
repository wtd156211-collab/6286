"""命令行入口：python -m parsebot <输入.txt> <输出.jsonl>"""

from __future__ import annotations

import sys

from parsebot.core import dumps, parse_line


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("用法: python -m parsebot <输入.txt> <输出.jsonl>", file=sys.stderr)
        return 2

    source_path, output_path = args
    try:
        source = open(source_path, "r", encoding="utf-8-sig", newline="")
    except OSError as error:
        print(f"无法读取输入 {source_path}: {error}", file=sys.stderr)
        return 1

    counts = {"ok": 0, "empty": 0, "reject": 0}
    line_number = 0
    try:
        with source, open(output_path, "w", encoding="utf-8", newline="") as target:
            for line_number, raw in enumerate(source, 1):
                if raw.endswith("\n"):
                    raw = raw[:-1]
                if raw.endswith("\r"):
                    raw = raw[:-1]
                result = parse_line(raw)
                counts[result["status"]] += 1
                target.write(dumps({"line": line_number, **result}) + "\n")
    except (OSError, UnicodeError) as error:
        print(f"批处理失败: {error}", file=sys.stderr)
        return 1

    print(
        f"完成: 共 {line_number} 行，成功 {counts['ok']}，"
        f"空值 {counts['empty']}，拒绝 {counts['reject']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
