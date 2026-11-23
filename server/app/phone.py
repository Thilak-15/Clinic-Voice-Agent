"""Turn a spoken phone number into digits.

Speech-to-text usually returns digits, but sometimes it returns words
("nine eight four double five ..."), so we handle both.
"""

import re

_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "nil": "0",
    "one": "1", "two": "2", "to": "2", "too": "2", "three": "3", "four": "4", "for": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}  # fmt: skip
_REPEAT = {"double": 2, "triple": 3}


def normalize_phone(raw: str) -> str:
    """Return only the digits of a spoken or typed phone number."""
    tokens = re.findall(r"[a-zA-Z]+|\d", (raw or "").lower())
    digits: list[str] = []
    repeat = 1
    for tok in tokens:
        if tok in _REPEAT:
            repeat = _REPEAT[tok]
            continue
        d = tok if tok.isdigit() else _WORDS.get(tok)
        if d is None:
            repeat = 1
            continue
        digits.append(d * repeat)
        repeat = 1
    return "".join(digits)


def canonical_phone(raw: str) -> str | None:
    """Canonical 10-digit Indian mobile number, or None if it doesn't look valid.

    Accepts an optional +91 / 91 / 0 prefix in front of 10 digits.
    """
    d = normalize_phone(raw)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) != 10:
        return None
    return d


def spoken(phone: str) -> str:
    """'9876543210' -> '98765 43210', the way people read numbers back."""
    return f"{phone[:5]} {phone[5:]}" if len(phone) == 10 else phone
