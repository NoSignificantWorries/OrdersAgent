
from dataclasses import dataclass
from enum import Enum


class CellType(str, Enum):
    TEXT = "text"
    NUMBER = "number"


@dataclass(slots=True)
class Field:
    anchor_patterns: list[str]
    possible_value_types: list[CellType]
    vertical: bool = True
    needed: bool = True



TypePatterns = {
    CellType.NUMBER: ["pattern1", "pattern2"]
}
