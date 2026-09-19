import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from rapidfuzz import fuzz

from .table_loader import Workbook


@dataclass(slots=True)
class Cell:
    value: int | str | tuple[int, int]
    row: int
    col: int
    is_merge_child: bool = False


class SparseTable:
    def __init__(self, name: str | None, nrows: int, ncols: int) -> None:
        self.name = name
        self.nrows = nrows
        self.ncols = ncols

        self.cells: list[list[Cell | None]] = [[None] * self.ncols for _ in range(self.nrows)]

    @property
    def empty(self) -> bool:
        return self.nrows == 0 or self.ncols == 0

    def add_cell(self, value: int | str | None, row: int, col: int, merged: bool = False, parent: tuple[int, int] | None = None) -> None:
        if value is None:
            if parent is None:
                return
            prow, pcol = parent
            parent_cell = self.cells[prow][pcol]
            if parent_cell is None:
                return
            cell = Cell(value=parent_cell.value, row=row, col=col, is_merge_child=True)
        else:
            cell = Cell(value=value, row=row, col=col)
        self.cells[row][col] = cell

    def normalize(self) -> None:
        keep_rows = [r for r in range(self.nrows) if any(self.cells[r])]
        keep_cols = [c for c in range(self.ncols)
                     if any(self.cells[r][c] for r in keep_rows)]
        self.cells = [[self.cells[r][c] for c in keep_cols] for r in keep_rows]
        self.nrows = len(keep_rows)
        self.ncols = len(keep_cols)

        for i in range(self.nrows):
            for j in range(self.ncols):
                if self.cells[i][j] is not None:
                    self.cells[i][j].row = i
                    self.cells[i][j].col = j

    def get_cell(self, row: int, col: int) -> Cell | None:
        return self.cells[row][col]


class Direction(str, Enum):
    DOWN = "down"
    RIGHT = "right"


class ExtractorID(str, Enum):
    AsInt = "AsInt"
    AsStr = "AsStr"
    AsSizes = "AsSizes"


class Extractor(Protocol):
    extractor_id: ExtractorID
    def extract(self, cell: Cell) -> Any | None: ...


class AsInt(Extractor):
    extractor_id = ExtractorID.AsInt
    def extract(self, cell: Cell) -> int | None:
        if isinstance(cell.value, int):
            return cell.value
        s = str(cell.value).strip().replace("\xa0", "")
        s = s.replace(" ", "")
        s = s.replace(",", ".")
        try:
            float_value = float(s)
            if not float_value.is_integer():
                return None
            return int(float_value)
        except ValueError:
            return None


class AsStr(Extractor):
    extractor_id = ExtractorID.AsStr
    def extract(self, cell: Cell) -> str | None:
        if cell.value is None:
            return None
        s = str(cell.value).strip()
        return s or None


class AsSizes(Extractor):
    extractor_id = ExtractorID.AsSizes
    SIZES = re.compile(r"^\s*([\d\s]+(?:[.,]\d+)?)\s*[xXхХ*×]\s*([\d\s]+(?:[.,]\d+)?)\s*$")
    def extract(self, cell: Cell) -> tuple[int, int] | None:
        if not isinstance(cell.value, str):
            return None
        m = self.SIZES.match(cell.value)
        if not m:
            return None
        try:
            w = int(float(m.group(1).replace(" ", "").replace(",", ".")))
            h = int(float(m.group(2).replace(" ", "").replace(",", ".")))
            return w, h
        except ValueError:
            return None


@dataclass(slots=True)
class FieldSpec:
    name: str
    anchors: list[str]
    extractors: list[Extractor]
    aliases: list[str] = field(default_factory=list)
    direction: Direction = Direction.DOWN


@dataclass(frozen=True, slots=True)
class PushCallback:
    extracted: bool = False
    extractor_id: ExtractorID | None = None


@dataclass(slots=True)
class FieldState:
    spec: FieldSpec
    start: tuple[int, int]
    block_id: int
    cells: list[Cell] = field(default_factory=list)

    def push(self, cell: Cell) -> PushCallback:
        for extractor in self.spec.extractors:
            extracted = extractor.extract(cell)
            if extracted is not None:
                cell.value = extracted
                self.cells.append(cell)
                return PushCallback(extracted=True, extractor_id=extractor.extractor_id)
        return PushCallback()


class FieldMatcher:
    _WS = re.compile(r"\s+", re.UNICODE)
    _STRIP = re.compile(r"[\(\)\[\]\{\}\.,]")

    @staticmethod
    def normalize(text: str) -> str:
        s = str(text).lower()
        s = FieldMatcher._WS.sub("", s)
        s = FieldMatcher._STRIP.sub("", s)
        return s

    def __init__(self, fields: list[FieldSpec]) -> None:
        self.fields: list[FieldSpec] = fields
        self.name_to_field: dict[str, FieldSpec] = {field.name: field for field in self.fields}
        self.anchors_to_field: dict[str, FieldSpec] = {}
        self.max_length = 0

        self.normalize_all_anchors()

    def normalize_all_anchors(self) -> None:
        for field in self.fields:
            for anchor in field.anchors:
                norm_anchor = FieldMatcher.normalize(anchor)
                self.anchors_to_field[norm_anchor] = field
                self.max_length = max(self.max_length, len(norm_anchor))

    def classify_text(self, text: str, threshold: float = 90.0) -> FieldSpec | None:
        norm = self.normalize(text)
        exact = self.anchors_to_field.get(norm)
        if exact is not None:
            return exact

        if len(norm) < 5:
            return None

        best_ratio = 0.0
        best_field = None
        for anchor, field in self.anchors_to_field.items():
            if abs(len(norm) - len(anchor)) > 5:
                continue
            ratio = fuzz.ratio(norm, anchor)
            if ratio > best_ratio:
                best_ratio = ratio
                best_field = field
                if ratio == 100.0:
                    break
        if best_ratio >= threshold:
            return best_field
        return None

    def field_by_name(self, name: str) -> FieldSpec | None:
        return self.name_to_field.get(name, None)


@dataclass(slots=True)
class Block:
    id: int
    start_row: int
    end_row: int = -1
    vertical_fields: dict[int, FieldState] = field(default_factory=dict)
    horizontal_fields: dict[int, FieldState] = field(default_factory=dict)


MATCHER = FieldMatcher([
    FieldSpec("material", ["наименование", "обозначение", "номенклатура", "артикул", "формула", "формула заполнения", "формула сп"], [AsStr()]),
    FieldSpec("amount", ["кол-во", "количество", "кол-во(шт)", "количество(шт)", "n"], [AsInt()]),
    FieldSpec("barcode", ["штрихкод", "шк"], [AsStr()]),
    FieldSpec("marking", ["маркировка"], [AsStr()])
])


class TableParser:
    matcher: FieldMatcher = MATCHER

    @staticmethod
    def read(wb: Workbook) -> list[SparseTable]:
        tables = []
        for sheet in wb.sheets:
            subtable = SparseTable(name=sheet.name, nrows=sheet.nrows, ncols=sheet.ncols)
            for cell in sheet.cells:
                subtable.add_cell(cell.value, cell.row, cell.col, cell.merged, cell.parent)
            subtable.normalize()
            if not subtable.empty:
                tables.append(subtable)
            else:
                print(f"WARN: Empty sheet '{sheet.name}' in the workbook '{wb.name}'")
        return tables

    @staticmethod
    def parse(tables: list[SparseTable]) -> None: ...
