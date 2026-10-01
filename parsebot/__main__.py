"""命令行：python -m parsebot <输入.txt> <输出.jsonl>。

逐行流式解析、逐行写出，不把整批攒在内存里。
退出码：整批跑完（含拒绝行）0；输入不可读 1；用法错 2。
"""

import sys

from . import dump_result, parse_line


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) != 3:
        print("用法: python -m parsebot <输入.txt> <输出.jsonl>", file=sys.stderr)
        return 2

    source, target = argv[1], argv[2]
    try:
        input_file = open(source, "r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        print("输入不可读: %s: %s" % (source, exc), file=sys.stderr)
        return 1

    counts = {"ok": 0, "empty": 0, "reject": 0}
    codes = {}
    try:
        with input_file, open(target, "w", encoding="utf-8", newline="") as output_file:
            for line_number, raw in enumerate(input_file, 1):
                text = raw.rstrip("\n")
                if text.endswith("\r"):
                    text = text[:-1]
                record = {"line": line_number}
                record.update(parse_line(text))
                output_file.write(dump_result(record) + "\n")
                status = record["status"]
                counts[status] += 1
                if status != "ok":
                    code = record["code"]
                    codes[code] = codes.get(code, 0) + 1
    except OSError as exc:
        print("写出失败: %s: %s" % (target, exc), file=sys.stderr)
        return 1

    total = sum(counts.values())
    detail = ", ".join("%s=%d" % (code, codes[code]) for code in sorted(codes))
    print(
        "共 %d 行：ok=%d empty=%d reject=%d%s"
        % (total, counts["ok"], counts["empty"], counts["reject"], "（" + detail + "）" if detail else ""),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
