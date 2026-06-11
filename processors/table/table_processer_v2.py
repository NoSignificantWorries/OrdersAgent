import re
from typing import Callable, Dict, List, Optional, Self, Tuple

from rapidfuzz import fuzz

from .config import TYPES_CONFIG, CellCode, CellType, CellTypes


def fuzzy_match(text: str, pattern: str, threshold: int = 50) -> bool:
    val = fuzz.ratio(text, pattern)
    return val >= threshold


class Cell:
    def __new__(cls, row: int, col: int, value: Optional[str]) -> Optional[Self]:
        if value is None or not bool(value.strip()):
            return None
        instance = super().__new__(cls)
        return instance

    def __init__(self, row: int, col: int, value: str) -> None:
        self.row = row
        self.col = col
        self.value = value.strip()
        self._type = CellType.TEXT
        self._code = CellCode[CellType.TEXT]
        self._classify(TYPES_CONFIG)

    def __repr__(self) -> str:
        return f"Cell('{self.value}' {self.row}:{self.col} {self._type} '{self._code}')"

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def type(self) -> CellType:
        return self._type

    @property
    def code(self) -> str:
        return self._code

    def _classify(self, config: CellTypes) -> CellType:
        value = re.sub(r"\s*", "", self.value)
        if config.regex is not None:
            for cell_type, patterns in config.regex.items():
                for pattern in patterns:
                    if re.fullmatch(pattern, value):
                        self._type = cell_type
                        self._code = CellCode[self._type]
                        return cell_type
        if config.fuzzy is not None:
            for cell_type, patterns in config.fuzzy.items():
                for pattern in patterns:
                    if fuzzy_match(value.lower(), pattern, 90):
                        self._type = cell_type
                        self._code = CellCode[self._type]
                        return cell_type
        return self._type


class Table:
    def __init__(self) -> None:
        self.cells: Dict[Tuple[int, int], Cell] = {}
        self.max_row = -1
        self.max_col = -1

        self.columns = {
            CellType.AMOUNT_H: CellType.NUMBER,
            CellType.BARCODE_H: CellType.TEXT | CellType.NUMBER,
            CellType.HEIGHT_H: CellType.NUMBER,
            CellType.LENGTH_H: CellType.NUMBER,
            CellType.WIDTH_H: CellType.NUMBER,
            CellType.MARKING_H: CellType.TEXT | CellType.NUMBER,
            CellType.MAT_H: CellType.TEXT,
            CellType.SIZE_H: CellType.TEXT | CellType.NUMBER,
        }

    def set_cell(self, cell: Cell) -> None:
        row, col = cell.row, cell.col
        if row > self.max_row:
            self.max_row = row
        if col > self.max_col:
            self.max_col = col
        self.cells[(row, col)] = cell

    def get_cell(self, row: int, col: int) -> Optional[Cell]:
        return self.cells.get((row, col))
