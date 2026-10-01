"""生成 samples/inputs/scale.txt：固定配方 + 固定种子的十万条混合样本。

只依赖标准库。重复运行产出逐字节相同的输入文件，供时限与确定性验收使用。
"""

import random
import sys

_DIGS = "零一二三四五六七八九"
_SECTION_UNITS = ["千", "百", "十", ""]


def _sec4(value):
    """1..9999 -> 中文（节内读法）。"""
    result = ""
    digits = [value // 1000, (value // 100) % 10, (value // 10) % 10, value % 10]
    started = False
    zero_pending = False
    for digit, unit in zip(digits, _SECTION_UNITS):
        if digit == 0:
            if started:
                zero_pending = True
            continue
        if zero_pending:
            result += "零"
            zero_pending = False
        if digit == 1 and unit == "十" and not started:
            result += "十"
        else:
            result += _DIGS[digit] + unit
        started = True
    return result


def int_to_cn(value):
    """0..99999999 -> 解析库认可的中文数字。"""
    if value == 0:
        return "零"
    sections = [value // 10 ** 8 % 10000, value // 10 ** 4 % 10000, value % 10000]
    big = ["亿", "万", ""]
    parts = []
    zero_pending = False
    for section_value, section_unit in zip(sections, big):
        if section_value == 0:
            if parts:
                zero_pending = True
            continue
        if zero_pending or (parts and section_value < 1000):
            parts.append("零")
        parts.append(_sec4(section_value) + section_unit)
        zero_pending = False
    return "".join(parts)


# 单位写法（标准单位, 量纲, 系数字符串, 可选写法列表）。
_LENGTH_UNITS = ["米", "千米", "公里", "km", "KM", "厘米", "cm", "毫米", "mm"]
_MASS_UNITS = ["千克", "公斤", "kg", "克", "g", "G", "吨", "t", "T"]
_TIME_UNITS = ["秒", "s", "分钟", "min", "小时", "h", "天", "d"]
_ALL_UNITS = _LENGTH_UNITS + _MASS_UNITS + _TIME_UNITS

# 写法 -> 系数（与 README 换算表一致）。
_COEF = {
    "米": "1", "千米": "1000", "公里": "1000", "km": "1000", "KM": "1000",
    "厘米": "0.01", "cm": "0.01", "毫米": "0.001", "mm": "0.001",
    "千克": "1", "公斤": "1", "kg": "1", "克": "0.001", "g": "0.001", "G": "0.001",
    "吨": "1000", "t": "1000", "T": "1000",
    "秒": "1", "s": "1", "分钟": "60", "min": "60", "小时": "3600",
    "h": "3600", "天": "86400", "d": "86400",
}
_DIM_OF = {u: ("L" if u in _LENGTH_UNITS else "M" if u in _MASS_UNITS else "T") for u in _ALL_UNITS}

_INVALID_POOL = [
    "+5", "１２３", "壹佰", "米", "5米千克", "1.2.3", "1e3", "abc",
    "十万火急", "两两万", "3.14.15", "公里9", "5kgkg", "5.厘米",
]
_WHITESPACE = ["   ", "\t", "\u3000", " \t ", "\t\u3000"]
_CONNECTORS = ["~", "～", "到", "-"]


def _arabic_number(rng, max_value=10 ** 11):
    kind = rng.randrange(6)
    if kind == 0:
        return str(rng.randrange(0, max_value))
    if kind == 1:
        return "%d.%d" % (rng.randrange(0, max_value), rng.randrange(0, 1000))
    if kind == 2:
        value = rng.randrange(1000, max(max_value, 1001))
        text = "{:,}".format(value)
        return text
    if kind == 3:
        return "%d.5" % rng.randrange(0, max_value)
    if kind == 4:
        return "0.%03d" % rng.randrange(0, 1000)
    return str(rng.randrange(0, 100))


def _chinese_number(rng):
    return int_to_cn(rng.randrange(0, 10 ** 8))


def _number(rng):
    if rng.random() < 0.6:
        return _arabic_number(rng), "ar"
    return _chinese_number(rng), "cn"


def _gen_with_unit(rng):
    if rng.random() < 0.6:
        number, kind = _arabic_number(rng, 10 ** 9), "ar"
    else:
        number, kind = int_to_cn(rng.randrange(0, 10 ** 7)), "cn"
    unit = rng.choice(_ALL_UNITS)
    gap = rng.choice(["", " ", "", "  "]) if kind == "ar" else ""
    return number + gap + unit


def _gen_plain(rng):
    number, _ = _number(rng)
    return number


def _gen_multiplier(rng):
    suffix = rng.choice(["万", "亿"])
    number = _arabic_number(rng, 10 ** 5 if suffix == "万" else 101)
    gap = rng.choice(["", " ", ""])
    # 保证 数值×倍数×单位系数 不越过 10^12。
    units = ["", "米", "千米", "厘米", "毫米", "千克", "公斤", "克", "秒", "分钟"]
    unit = rng.choice(units)
    prefix_gap = " " if unit and rng.random() < 0.3 else ""
    return number + gap + suffix + prefix_gap + unit


def _gen_chinese_unit(rng):
    number = int_to_cn(rng.randrange(0, 10 ** 7))
    unit = rng.choice([""] + _ALL_UNITS)
    return number + unit


def _gen_percent(rng):
    if rng.random() < 0.5:
        return _arabic_number(rng, 10 ** 4) + "%"
    number = _chinese_number(rng) if rng.random() < 0.5 else _arabic_number(rng, 1000)
    return "百分之" + number


def _gen_range(rng):
    unit = rng.choice([""] + _ALL_UNITS)
    connector = rng.choice(_CONNECTORS)
    low_kind = rng.random()
    high_num = rng.randrange(1, 10 ** 6)
    low_num = rng.randrange(0, high_num + 1)
    if rng.random() < 0.08:
        low_num, high_num = high_num, rng.randrange(0, max(low_num, 1))
    if low_kind < 0.5:
        left = str(low_num)
        right = str(high_num)
    else:
        left = int_to_cn(low_num)
        right = int_to_cn(high_num)
    # 单位放右边、左边或两端。
    placement = rng.randrange(3)
    gap = rng.choice(["", " ", "  "])
    if placement == 0:
        return left + gap + connector + gap + right + (gap if unit else "") + unit
    if placement == 1:
        return left + (gap if unit else "") + unit + gap + connector + gap + right
    return (
        left + (gap if unit else "") + unit
        + gap + connector + gap
        + right + (gap if unit else "") + unit
    )


def _gen_ambiguous_m(rng):
    number = _arabic_number(rng, 10 ** 6)
    return number + rng.choice(["m", "M", " m", " M"])


def _gen_shorthand(rng):
    number = _arabic_number(rng, 1000)
    middle = rng.choice(["米", "m", "M"])
    tail = rng.choice("0123456789零一二三四五六七八九两")
    return number + middle + tail


def _gen_bad_comma(rng):
    kind = rng.randrange(3)
    if kind == 0:
        return "%d,%d" % (rng.randrange(1, 10 ** 4), rng.randrange(0, 100))
    if kind == 1:
        return "%d,%d,%d" % (rng.randrange(1, 100), rng.randrange(0, 100), rng.randrange(0, 100))
    return "%d,%d,%d" % (rng.randrange(1, 10 ** 5), rng.randrange(100, 1000), rng.randrange(0, 100))


def _gen_out_of_range(rng):
    kind = rng.randrange(3)
    if kind == 0:
        return str(10 ** 12 + rng.randrange(1, 10 ** 6))
    if kind == 1:
        return "-" + str(rng.randrange(1, 10 ** 6))
    return str(rng.randrange(10001, 50000)) + "亿"


# (权重, 生成函数)
_RECIPE = [
    (25, _gen_with_unit),
    (12, _gen_plain),
    (10, _gen_multiplier),
    (13, _gen_chinese_unit),
    (8, _gen_percent),
    (15, _gen_range),
    (5, _gen_ambiguous_m),
    (3, _gen_shorthand),
    (3, _gen_bad_comma),
    (2, lambda r: r.choice(_INVALID_POOL)),
    (2, lambda r: r.choice(_WHITESPACE)),
    (2, _gen_out_of_range),
]


def generate(count, seed):
    rng = random.Random(seed)
    weights = [weight for weight, _ in _RECIPE]
    for _ in range(count):
        index = rng.choices(range(len(_RECIPE)), weights=weights, k=1)[0]
        yield _RECIPE[index][1](rng)


def main(argv):
    count = int(argv[1]) if len(argv) > 1 else 100000
    seed = int(argv[2]) if len(argv) > 2 else 20261001
    target = argv[3] if len(argv) > 3 else None
    stream = open(target, "w", encoding="utf-8", newline="\n") if target else sys.stdout
    try:
        for line in generate(count, seed):
            stream.write(line + "\n")
    finally:
        if target:
            stream.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
