import re

from rapidfuzz import fuzz

NUMBER = re.compile(r"^\s*((\d+)([.,]\d+)?)\s*$")
WHITESPACE = re.compile(r"\s*")


def number_to_int(number: str) -> int | None:
    match = NUMBER.match(number)
    if match:
        number = match.group(2)
        return int(number)
    return None


def clean(text: str | None) -> str | None:
    if text is None:
        return None
    value = re.sub(WHITESPACE, "", text)
    if not bool(value):
        return None
    return value


def to_text(data: str | float | None) -> str | None:
    if data is None:
        return None
    text = str(data)
    return clean(text)


def fuzzy_match(text: str, pattern: str, threshold: int = 50) -> bool:
    val = fuzz.ratio(text, pattern)
    return val >= threshold


def get_match_and_groups(
    pattern: re.Pattern[str], text: str, groups: list[int] = []
) -> tuple[bool, list[str]]:
    pattern = re.compile(pattern)
    match = pattern.match(text)
    if match:
        return True, [match.group(i) for i in groups]
    return False, []


def check_fullmatch(pattern: re.Pattern[str], text: str) -> bool:
    pattern = re.compile(pattern)
    match = pattern.fullmatch(text)
    return bool(match)
