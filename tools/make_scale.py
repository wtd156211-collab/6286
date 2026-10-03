"""按固定配方生成 samples/inputs/scale.txt（十万条，确定性）。"""

from pathlib import Path

TOTAL = 100_000

CHINESE_NUMBERS = ["三公里", "一百二十", "两万五千", "零点五", "十万", "九千九百九十九"]


def make_line(index: int) -> str:
    slot = index % 20
    if slot == 0:
        return f"{index % 9000 + 1}米"
    if slot == 1:
        return f"{index % 500 + 1}小时"
    if slot == 2:
        return f"{index % 100}.5千克"
    if slot == 3:
        return CHINESE_NUMBERS[index % len(CHINESE_NUMBERS)]
    if slot == 4:
        return f"{index % 100}%"
    if slot == 5:
        return f"{index % 50 + 1}~{index % 50 + 51}千米"
    if slot == 6:
        return "3m"
    if slot == 7:
        return f"{index % 9 + 1},23"
    if slot == 8:
        return ""
    if slot == 9:
        return "5斤"
    if slot == 10:
        return f"{index % 90 + 10}分钟"
    if slot == 11:
        return f"{index % 200 + 1}克~{index % 200 + 201}克"
    if slot == 12:
        return f"{index % 900 + 100},123"
    if slot == 13:
        return "壹佰"
    if slot == 14:
        return f"{index % 60 + 1}到{index % 60 + 61}分钟"
    if slot == 15:
        return f"{index % 40 + 1}.25公里"
    if slot == 16:
        return "10M2"
    if slot == 17:
        return f"{index % 1000000 + 1}"
    if slot == 18:
        return "　"
    return f"{index % 30 + 1}天"


def main() -> None:
    target = Path(__file__).resolve().parent.parent / "samples" / "inputs" / "scale.txt"
    with target.open("w", encoding="utf-8", newline="") as handle:
        for index in range(TOTAL):
            handle.write(make_line(index) + "\n")
    print(f"写出 {target} 共 {TOTAL} 行")


if __name__ == "__main__":
    main()
