import re
from typing import List, Optional, Tuple

from rapidfuzz import fuzz


NUMBER = re.compile(r"^\s*((\d+)([.,]\d+)?)\s*$")
WHITESPACE = re.compile(r"\s*")


def number_to_int(number: str) -> Optional[int]:
    match = NUMBER.match(number)
    if match:
        number = match.group(2)
        return int(number)
    return None


def clean(text: str) -> str:
    value = re.sub(r"\s*", "", text)
    return value


def fuzzy_match(text: str, pattern: str, threshold: int = 50) -> bool:
    val = fuzz.ratio(text, pattern)
    return val >= threshold


def get_match_and_groups(pattern: str, text: str, groups: List[int] = []) -> Tuple[bool, List[str]]:
    pattern = re.compile(pattern)
    match = pattern.match(text)
    if match:
        return True, [match.group(i) for i in groups]
    return False, []


def check_fullmatch(pattern: str, text: str) -> bool:
    pattern = re.compile(pattern)
    match = pattern.fullmatch(text)
    if match:
        return True
    return False
