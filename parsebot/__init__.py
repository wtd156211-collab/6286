"""parsebot：把运营表格里的一格文本解析成「数值 + 标准单位」。

只用标准库，十进制精确运算。入口是 :func:`parse_line`，命令行与网页都走它。
解析不了的文本以 ``status="reject"`` 明确拒绝并携带原因码；拿不准的写法
（短单位两义、数字+米+数字的连写）列入 ``candidates``，绝不猜一个交上去。
"""

import json
import re
from decimal import Decimal

__all__ = ["parse_line", "dump_result", "format_decimal", "Reject"]

# 第 1 步允许去掉的首尾空白：半角空格、Tab、全角空格。
_WS = " \t\u3000"

_MAX_VALUE = Decimal(10) ** 12

_LENGTH = "length"
_MASS = "mass"
_TIME = "time"
_PERCENT = "percent"

# 单位写法 -> (标准单位, 量纲, 系数)。注意 m 不放进直接解析：它两义，见 _resolve_unit。
_UNIT_TABLE = {
    "米": ("m", _LENGTH, Decimal(1)),
    "千米": ("m", _LENGTH, Decimal(1000)),
    "公里": ("m", _LENGTH, Decimal(1000)),
    "km": ("m", _LENGTH, Decimal(1000)),
    "厘米": ("m", _LENGTH, Decimal("0.01")),
    "cm": ("m", _LENGTH, Decimal("0.01")),
    "毫米": ("m", _LENGTH, Decimal("0.001")),
    "mm": ("m", _LENGTH, Decimal("0.001")),
    "千克": ("kg", _MASS, Decimal(1)),
    "公斤": ("kg", _MASS, Decimal(1)),
    "kg": ("kg", _MASS, Decimal(1)),
    "克": ("kg", _MASS, Decimal("0.001")),
    "g": ("kg", _MASS, Decimal("0.001")),
    "吨": ("kg", _MASS, Decimal(1000)),
    "t": ("kg", _MASS, Decimal(1000)),
    "秒": ("s", _TIME, Decimal(1)),
    "s": ("s", _TIME, Decimal(1)),
    "分钟": ("s", _TIME, Decimal(60)),
    "min": ("s", _TIME, Decimal(60)),
    "小时": ("s", _TIME, Decimal(3600)),
    "h": ("s", _TIME, Decimal(3600)),
    "天": ("s", _TIME, Decimal(86400)),
    "d": ("s", _TIME, Decimal(86400)),
    "%": ("%", _PERCENT, Decimal(1)),
}

_CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_SMALL = {"十": 10, "百": 100, "千": 1000}
_CN_BIG = {"万": 10 ** 4, "亿": 10 ** 8}
_CN_CHARS = set(_CN_DIGITS) | set(_CN_SMALL) | set(_CN_BIG) | {"点"}
_CN_TOKEN_RE = re.compile(r"[零一二三四五六七八九十百千万亿两点]+")

_ARABIC_TOKEN_RE = re.compile(r"[0-9][0-9,.]*")
_STRICT_COMMA_RE = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?$")
_PLAIN_NUMBER_RE = re.compile(r"\d+(\.\d+)?$")

# 连写的「数字 + 米|m|M + 一位数字」，如 3米2 / 3m2：可能是 3.2 米或 3 平方米。
_SHORTHAND_RE = re.compile(r"(\S+?)(米|m|M)([0-9零一二三四五六七八九两])\Z")

_CONNECTORS = ("~", "～", "到", "-")


class Reject(Exception):
    """解析拒绝，携带原因码（歧义写法另带候选含义）。"""

    def __init__(self, code, candidates=None):
        super().__init__(code)
        self.code = code
        self.candidates = candidates


def format_decimal(value):
    """最短十进制写法，不用科学计数法、不加千分位。"""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def dump_result(rec):
    """把结果对象序列化成紧凑 JSON：键序沿用 dict，Decimals 按最短十进制直出。"""
    parts = []
    for key, val in rec.items():
        head = json.dumps(key, ensure_ascii=False) + ":"
        if isinstance(val, Decimal):
            parts.append(head + format_decimal(val))
        elif isinstance(val, list):
            parts.append(
                head
                + "["
                + ",".join(
                    format_decimal(x) if isinstance(x, Decimal) else json.dumps(x, ensure_ascii=False)
                    for x in val
                )
                + "]"
            )
        else:
            parts.append(head + json.dumps(val, ensure_ascii=False))
    return "{" + ",".join(parts) + "}"


# --------------------------------------------------------------------------- #
# 数值
# --------------------------------------------------------------------------- #

def _arabic_value(token):
    """校验阿拉伯数字 token，逗号必须严格三位一组，否则按歧义逗号拒绝。"""
    if "," in token:
        if _STRICT_COMMA_RE.match(token):
            return Decimal(token.replace(",", ""))
        raise Reject("AMBIGUOUS_NUMBER")
    if _PLAIN_NUMBER_RE.match(token):
        return Decimal(token)
    raise Reject("UNPARSEABLE")


def _cn_int(text):
    """按节算中文整数：亿×10^8 + 万×10^4 + 个位；不合法的写法返回 None。"""
    total = 0
    section = 0
    number = -1
    previous = None
    for ch in text:
        if ch in _CN_DIGITS:
            # 两个数字连用只允许「零」占位（一百零五），其余（两两万）非法。
            if previous is not None and previous in _CN_DIGITS and previous != "零":
                return None
            number = _CN_DIGITS[ch]
        elif ch in _CN_SMALL:
            if previous is None and ch != "十":
                return None  # 开头的百/千没有隐式 1，只有「十五」这类合法
            if previous in _CN_SMALL or previous in _CN_BIG:
                return None
            section += (number if number != -1 else 1) * _CN_SMALL[ch]
            number = -1
        elif ch in _CN_BIG:
            current = section + (number if number != -1 else 0)
            if current == 0:
                return None  # 万/亿前面必须有内容
            total += current * _CN_BIG[ch]
            section = 0
            number = -1
        previous = ch
    return total + section + (number if number != -1 else 0)


def _chinese_value(token):
    """校验并计算中文数字（含「点」小数），非法返回 None。"""
    if token.count("点") > 1:
        return None
    if "点" in token:
        int_text, frac_text = token.split("点")
        if not int_text or not frac_text:
            return None
        fraction = []
        for ch in frac_text:
            if ch == "两" or ch not in _CN_DIGITS:
                return None
            fraction.append(str(_CN_DIGITS[ch]))
        int_value = _cn_int(int_text)
        if int_value is None:
            return None
        return Decimal("%d.%s" % (int_value, "".join(fraction)))
    value = _cn_int(token)
    return None if value is None else Decimal(value)


def _try_number(text, *, allow_suffix):
    """整段 text 必须恰好是一个数字；失败返回 None（不抛拒绝）。"""
    if not text:
        return None
    ch = text[0]
    if "0" <= ch <= "9":
        match = _ARABIC_TOKEN_RE.match(text)
        token = match.group(0)
        rest = text[len(token):]
        if rest not in (("",) if not allow_suffix else ("", "万", "亿")):
            return None
        try:
            value = _arabic_value(token)
        except Reject:
            return None
        if rest == "万":
            value *= 10 ** 4
        elif rest == "亿":
            value *= 10 ** 8
        return value
    if ch in _CN_CHARS and _CN_TOKEN_RE.fullmatch(text):
        return _chinese_value(text)
    return None


# --------------------------------------------------------------------------- #
# 单位与单段解析
# --------------------------------------------------------------------------- #

def _resolve_unit(unit_text):
    if unit_text == "":
        return None
    if unit_text == "m" or unit_text == "M":
        # 米（长度）或分钟（时间），绝不替上游挑一个。
        raise Reject("AMBIGUOUS_UNIT", ["m", "min"])
    key = unit_text.lower() if unit_text.isascii() else unit_text
    info = _UNIT_TABLE.get(key)
    if info is None:
        raise Reject("UNPARSEABLE")
    return info


def _parse_segment(seg):
    """解析区间的一段，返回 ``(数值, 单位信息|None)``。"""
    # ③ 先查歧义连写：3米2 / 3m2 / 三米二 这类。
    match = _SHORTHAND_RE.fullmatch(seg)
    if match is not None and _try_number(match.group(1), allow_suffix=True) is not None:
        raise Reject("AMBIGUOUS_UNIT", ["m", "m^2"])

    # 百分之 只作前缀，接纯数字，不带单位与倍数。
    if seg.startswith("百分之"):
        number = _try_number(seg[3:].strip(_WS), allow_suffix=False)
        if number is None or number < 0:
            raise Reject("UNPARSEABLE")
        return number, _UNIT_TABLE["%"]

    negative = False
    body = seg
    if body.startswith("-"):
        negative = True
        body = body[1:]
    if not body:
        raise Reject("UNPARSEABLE")

    multiplier = 1
    first = body[0]
    if "0" <= first <= "9":
        token_match = _ARABIC_TOKEN_RE.match(body)
        token = token_match.group(0)
        rest = body[len(token):]
        value = _arabic_value(token)
        # 倍数后缀：紧跟或空一格写一个 万/亿。
        if rest[:1] in ("万", "亿"):
            multiplier = _CN_BIG[rest[0]]
            rest = rest[1:]
        elif rest[:1] == " " and rest[1:2] in ("万", "亿"):
            multiplier = _CN_BIG[rest[1]]
            rest = rest[2:]
        unit_text = rest.strip(" ")
    elif first in _CN_CHARS:
        token_match = _CN_TOKEN_RE.match(body)
        token = token_match.group(0)
        rest = body[len(token):]
        value = _chinese_value(token)
        if value is None:
            raise Reject("UNPARSEABLE")
        unit_text = rest.strip(" ")
    else:
        raise Reject("UNPARSEABLE")

    if negative:
        value = -value
    if value < 0:
        raise Reject("OUT_OF_RANGE")

    return value * multiplier, _resolve_unit(unit_text)


# --------------------------------------------------------------------------- #
# 区间与入口
# --------------------------------------------------------------------------- #

def _find_connector(text):
    """第一个左右都不为空的 ~ / ～ / 到 / -；左边为空的 - 按负号留给数值层。"""
    for index, ch in enumerate(text):
        if ch in _CONNECTORS:
            if text[:index].strip(_WS) and text[index + 1:].strip(_WS):
                return index
    return None


def _ok_single(value, info):
    coefficient = info[2] if info is not None else Decimal(1)
    converted = value * coefficient
    if converted > _MAX_VALUE:
        raise Reject("OUT_OF_RANGE")
    unit = info[0] if info is not None else None
    normalized = format_decimal(converted) + (" " + unit if unit is not None else "")
    return {"status": "ok", "value": converted, "unit": unit, "normalized": normalized}


def parse_line(text):
    """解析一格文本，返回不含 ``line`` 的结果对象 dict。

    成功：``status/value/unit/normalized``（区间时 value 为两元素列表）；
    空值：``status/empty/code``；拒绝：``status/reject/code``，歧义另带
    ``candidates``。同一输入恒定返回同一结果（纯函数，确定性）。
    """
    stripped = text.strip(_WS)
    if not stripped:
        return {"status": "empty", "code": "EMPTY"}
    try:
        cut = _find_connector(stripped)
        if cut is None:
            return _ok_single(*_parse_segment(stripped))

        # 两段各自解析，先左后右报错。
        left_value, left_info = _parse_segment(stripped[:cut].strip(_WS))
        right_value, right_info = _parse_segment(stripped[cut + 1:].strip(_WS))

        # 一端缺单位时继承另一端。
        if left_info is None:
            left_info = right_info
        if right_info is None:
            right_info = left_info
        if left_info is not None and right_info is not None and left_info[1] != right_info[1]:
            raise Reject("UNIT_MISMATCH")

        left_coeff = left_info[2] if left_info is not None else Decimal(1)
        right_coeff = right_info[2] if right_info is not None else Decimal(1)
        lower = left_value * left_coeff
        upper = right_value * right_coeff
        if upper < lower:
            raise Reject("INVALID_RANGE")
        if lower > _MAX_VALUE or upper > _MAX_VALUE:
            raise Reject("OUT_OF_RANGE")

        unit = left_info[0] if left_info is not None else None
        normalized = format_decimal(lower) + "~" + format_decimal(upper)
        if unit is not None:
            normalized += " " + unit
        return {"status": "ok", "value": [lower, upper], "unit": unit, "normalized": normalized}
    except Reject as rejected:
        record = {"status": "reject", "code": rejected.code}
        if rejected.candidates is not None:
            record["candidates"] = rejected.candidates
        return record
