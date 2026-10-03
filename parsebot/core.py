"""把一格自由文本解析成「数值 + 标准单位」。

只使用标准库。解析失败统一抛出 :class:`ParseFailure`，带稳定原因码。
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

__all__ = ["parse_line", "dumps"]

MAX_VALUE = Decimal(10) ** 12

STD_UNIT = {
    "length": "m",
    "mass": "kg",
    "time": "s",
    "percent": "%",
}

# 单位写法 -> (量纲, 相对标准单位系数)。注意：裸 m/M 不放在表里，按歧义拒绝。
UNIT_TABLE: dict[str, tuple[str, Decimal]] = {
    "米": ("length", Decimal("1")),
    "千米": ("length", Decimal("1000")),
    "公里": ("length", Decimal("1000")),
    "km": ("length", Decimal("1000")),
    "厘米": ("length", Decimal("0.01")),
    "cm": ("length", Decimal("0.01")),
    "毫米": ("length", Decimal("0.001")),
    "mm": ("length", Decimal("0.001")),
    "千克": ("mass", Decimal("1")),
    "公斤": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1")),
    "克": ("mass", Decimal("0.001")),
    "g": ("mass", Decimal("0.001")),
    "吨": ("mass", Decimal("1000")),
    "t": ("mass", Decimal("1000")),
    "秒": ("time", Decimal("1")),
    "s": ("time", Decimal("1")),
    "分钟": ("time", Decimal("60")),
    "min": ("time", Decimal("60")),
    "小时": ("time", Decimal("3600")),
    "h": ("time", Decimal("3600")),
    "天": ("time", Decimal("86400")),
    "d": ("time", Decimal("86400")),
    "%": ("percent", Decimal("1")),
}

CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CN_SECTION_UNITS = {"十": 10, "百": 100, "千": 1000}
CN_TOKEN_CHARS = set(CN_DIGITS) | set(CN_SECTION_UNITS) | {"万", "亿", "点"}

STRIP_CHARS = " \t\u3000"

_AMBIGUOUS_COMPOUND = re.compile(r"\d+(?:\.\d+)?(?:米|[mM])\d")
_ARABIC_TOKEN = re.compile(r"[0-9,.]+")
_ARABIC_PLAIN = re.compile(r"\d+(?:\.\d+)?")
_ARABIC_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_ASCII_DIGITS = set("0123456789")


class ParseFailure(Exception):
    """携带原因码的解析失败。"""

    def __init__(self, code: str, candidates: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.candidates = candidates


def parse_line(text: str) -> dict:
    """解析一行文本，返回不含 ``line`` 的结果对象。"""
    stripped = text.strip(STRIP_CHARS)
    if not stripped:
        return {"status": "empty", "code": "EMPTY"}
    try:
        split = _find_connector(stripped)
        if split is None:
            value, dimension, factor = _parse_segment(stripped)
            normalized_value = value * factor
            _check_bounds(normalized_value)
            return _success(normalized_value, dimension)

        left_text, right_text = split
        left_value, left_dim, left_factor = _parse_segment(left_text)
        right_value, right_dim, right_factor = _parse_segment(right_text)

        if left_dim is None and right_dim is not None:
            left_dim, left_factor = right_dim, right_factor
        elif right_dim is None and left_dim is not None:
            right_dim, right_factor = left_dim, left_factor
        elif left_dim is not None and right_dim is not None and left_dim != right_dim:
            raise ParseFailure("UNIT_MISMATCH")

        lower = left_value * left_factor
        upper = right_value * right_factor
        _check_bounds(lower)
        _check_bounds(upper)
        if upper < lower:
            raise ParseFailure("INVALID_RANGE")
        return _range_success(lower, upper, left_dim)
    except ParseFailure as failure:
        result: dict = {"status": "reject", "code": failure.code}
        if failure.candidates is not None:
            result["candidates"] = failure.candidates
        return result


def _find_connector(text: str) -> tuple[str, str] | None:
    """返回第一个左右都不为空的连接符切出的两段。"""
    for index, char in enumerate(text):
        if char in "~～" or char in ("到", "-"):
            left = text[:index].strip(STRIP_CHARS)
            right = text[index + 1 :].strip(STRIP_CHARS)
            if left and right:
                return left, right
    return None


def _parse_segment(segment: str) -> tuple[Decimal, str | None, Decimal]:
    """解析单段，返回 (原始数值, 量纲, 单位系数)；无量纲时量纲为 None。"""
    if _AMBIGUOUS_COMPOUND.fullmatch(segment):
        raise ParseFailure("AMBIGUOUS_UNIT", ["m", "m^2"])

    if segment.startswith("-"):
        rest = segment[1:]
        if not rest or rest[0] in "-+":
            raise ParseFailure("UNPARSEABLE")
        _parse_segment(rest)
        raise ParseFailure("OUT_OF_RANGE")

    if segment.startswith("百分之"):
        value = _parse_pure_number(segment[3:])
        return value, "percent", Decimal("1")

    first = segment[:1]
    if first in _ASCII_DIGITS:
        token = _ARABIC_TOKEN.match(segment).group(0)
        value = _arabic_token_value(token)
        rest = segment[len(token) :]
        if rest[:1] in ("万", "亿"):
            value *= 10000 if rest[0] == "万" else 100000000
            rest = rest[1:]
        elif rest[:2] in (" 万", " 亿"):
            value *= 10000 if rest[1] == "万" else 100000000
            rest = rest[2:]
        unit_text = rest.lstrip(STRIP_CHARS)
    elif first in CN_TOKEN_CHARS:
        index = 0
        while index < len(segment) and segment[index] in CN_TOKEN_CHARS:
            index += 1
        value = _parse_chinese_number(segment[:index])
        unit_text = segment[index:].lstrip(STRIP_CHARS)
    else:
        raise ParseFailure("UNPARSEABLE")

    if not unit_text:
        return value, None, Decimal("1")
    dimension, factor = _lookup_unit(unit_text)
    return value, dimension, factor


def _arabic_token_value(token: str) -> Decimal:
    if "," in token:
        if not _ARABIC_GROUPED.fullmatch(token):
            raise ParseFailure("AMBIGUOUS_NUMBER")
        token = token.replace(",", "")
    elif not _ARABIC_PLAIN.fullmatch(token):
        raise ParseFailure("UNPARSEABLE")
    return Decimal(token)


def _parse_pure_number(text: str) -> Decimal:
    """只解析纯数字（百分之前缀后），不允许单位与倍数。"""
    if not text:
        raise ParseFailure("UNPARSEABLE")
    if text[0] in _ASCII_DIGITS:
        token = _ARABIC_TOKEN.match(text).group(0)
        if token != text:
            raise ParseFailure("UNPARSEABLE")
        return _arabic_token_value(token)
    if text[0] in CN_TOKEN_CHARS and all(char in CN_TOKEN_CHARS for char in text):
        return _parse_chinese_number(text)
    raise ParseFailure("UNPARSEABLE")


def _lookup_unit(unit_text: str) -> tuple[str, Decimal]:
    if unit_text in UNIT_TABLE:
        return UNIT_TABLE[unit_text]
    lowered = unit_text.lower()
    if lowered == "m":
        raise ParseFailure("AMBIGUOUS_UNIT", ["m", "min"])
    if lowered in UNIT_TABLE:
        return UNIT_TABLE[lowered]
    raise ParseFailure("UNPARSEABLE")


def _parse_chinese_number(token: str) -> Decimal:
    if token.count("点") > 1:
        raise ParseFailure("UNPARSEABLE")
    if "点" in token:
        integer_text, fraction_text = token.split("点")
        if not integer_text or not fraction_text:
            raise ParseFailure("UNPARSEABLE")
        fraction = ""
        for char in fraction_text:
            if char not in CN_DIGITS:
                raise ParseFailure("UNPARSEABLE")
            fraction += str(CN_DIGITS[char])
        return Decimal(_parse_chinese_integer(integer_text)) + Decimal("0." + fraction)
    return Decimal(_parse_chinese_integer(token))


def _parse_chinese_integer(text: str) -> int:
    if text.count("亿") > 1 or text.count("万") > 1:
        raise ParseFailure("UNPARSEABLE")
    if "亿" in text:
        high_text, low_text = text.split("亿")
        if not high_text:
            raise ParseFailure("UNPARSEABLE")
        high = _parse_wan_section(high_text)
        low = _parse_wan_section(low_text) if low_text else 0
        return high * 100000000 + low
    return _parse_wan_section(text)


def _parse_wan_section(text: str) -> int:
    if not text:
        raise ParseFailure("UNPARSEABLE")
    if "万" in text:
        high_text, low_text = text.split("万")
        if not high_text:
            raise ParseFailure("UNPARSEABLE")
        high = _parse_small_section(high_text)
        low = _parse_small_section(low_text) if low_text else 0
        return high * 10000 + low
    return _parse_small_section(text)


def _parse_small_section(text: str) -> int:
    """解析 0..9999 的一节，要求节内单位严格递减。"""
    if not text:
        raise ParseFailure("UNPARSEABLE")
    total = 0
    digit = None
    previous_unit = None
    for char in text:
        if char == "零":
            digit = None
        elif char in CN_DIGITS:
            if digit is not None:
                raise ParseFailure("UNPARSEABLE")
            digit = CN_DIGITS[char]
        elif char in CN_SECTION_UNITS:
            unit = CN_SECTION_UNITS[char]
            if previous_unit is not None and unit >= previous_unit:
                raise ParseFailure("UNPARSEABLE")
            if digit is None:
                if unit != 10:
                    raise ParseFailure("UNPARSEABLE")
                digit = 1
            total += digit * unit
            previous_unit = unit
            digit = None
        else:
            raise ParseFailure("UNPARSEABLE")
    if digit is not None:
        total += digit
    return total


def _check_bounds(value: Decimal) -> None:
    if value < 0 or value > MAX_VALUE:
        raise ParseFailure("OUT_OF_RANGE")


def _as_number(value: Decimal) -> int | Decimal:
    if value == value.to_integral_value():
        return int(value)
    return value


def _format_value(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _success(value: Decimal, dimension: str | None) -> dict:
    unit = STD_UNIT[dimension] if dimension is not None else None
    normalized = _format_value(value)
    if unit is not None:
        normalized += " " + unit
    return {
        "status": "ok",
        "value": _as_number(value),
        "unit": unit,
        "normalized": normalized,
    }


def _range_success(lower: Decimal, upper: Decimal, dimension: str | None) -> dict:
    unit = STD_UNIT[dimension] if dimension is not None else None
    normalized = _format_value(lower) + "~" + _format_value(upper)
    if unit is not None:
        normalized += " " + unit
    return {
        "status": "ok",
        "value": [_as_number(lower), _as_number(upper)],
        "unit": unit,
        "normalized": normalized,
    }


def dumps(obj: object) -> str:
    """按固定键序、紧凑格式序列化解析结果。"""
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, Decimal):
        return format(obj.normalize(), "f")
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(dumps(item) for item in obj) + "]"
    if isinstance(obj, dict):
        return (
            "{"
            + ",".join(
                json.dumps(str(key), ensure_ascii=False) + ":" + dumps(value)
                for key, value in obj.items()
            )
            + "}"
        )
    raise TypeError(f"不支持的类型: {type(obj)!r}")
