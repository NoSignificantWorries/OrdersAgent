import re
from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from rapidfuzz import fuzz

from .loader import Workbook
from .report import WorkbookReport


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

    def add_cell(self, value: int | str | None, row: int, col: int, merged: bool = False, parent: tuple[int, int] | None = None) -> Cell | None:
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
        return cell

    def normalize(self) -> tuple[list[int], list[int]]:
        keep_rows: set[int] | list[int] = set()
        keep_cols: set[int] | list[int] = set()
        for r in range(self.nrows):
            for c in range(self.ncols):
                if self.cells[r][c] is not None and not self.cells[r][c].is_merge_child:
                    keep_cols.add(c)
                    keep_rows.add(r)
        keep_rows = sorted(keep_rows)
        keep_cols = sorted(keep_cols)
        self.cells = [[self.cells[r][c] for c in keep_cols] for r in keep_rows]
        self.nrows = len(keep_rows)
        self.ncols = len(keep_cols)

        for i in range(self.nrows):
            for j in range(self.ncols):
                if self.cells[i][j] is not None:
                    self.cells[i][j].row = i
                    self.cells[i][j].col = j

        return keep_rows, keep_cols

    def get_cell(self, row: int, col: int) -> Cell | None:
        return self.cells[row][col]

    def iter_cells(self) -> Generator[tuple[int, int, Cell], None, None]:
        for i in range(self.nrows):
            for j in range(self.ncols):
                cell = self.get_cell(i, j)
                if cell is not None:
                    yield i, j, cell


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
    header: str
    start: tuple[int, int]
    block_id: int
    cells: list[Cell] = field(default_factory=list)
    closed: bool = False

    @property
    def size(self) -> int:
        return len(self.cells)

    @property
    def empty(self) -> bool:
        return len(self.cells) == 0

    def push(self, cell: Cell) -> PushCallback:
        if self.closed:
            return PushCallback()
        callback = PushCallback()
        for extractor in self.spec.extractors:
            extracted = extractor.extract(cell)
            if extracted is not None:
                new_cell = Cell(extracted, cell.row, cell.col, is_merge_child=cell.is_merge_child)
                self.cells.append(new_cell)
                callback = PushCallback(extracted=True, extractor_id=extractor.extractor_id)
                break

        if self.spec.direction == Direction.RIGHT and self.size >= 1:
            self.closed = True
        return callback


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

    def match(self, value: int | str) -> FieldSpec | None:
        if isinstance(value, int):
            return None
        return self.classify_text(value)


@dataclass(slots=True)
class Block:
    id: int
    start_row: int
    end_row: int = -1
    vertical_fields: dict[int, FieldState] = field(default_factory=dict)
    horizontal_fields: dict[int, FieldState] = field(default_factory=dict)


MATCHER = FieldMatcher([
    FieldSpec("material", ["наименование", "обозначение", "номенклатура", "артикул", "тип пакета", "формула", "формула заполнения", "формула сп"], [AsStr()]),
    FieldSpec("amount", ["кол-во", "количество", "кол-во(шт)", "количество(шт)", "колич", "n"], [AsInt()]),
    FieldSpec("size", ["размер", "размеры", "размер мм", "размеры мм", "длина", "длина мм", "ширина мм", "ширина", "высота", "высота мм", "стекла"], [AsSizes(), AsInt()]),
    FieldSpec("barcode", ["штрихкод", "шк"], [AsStr()]),
    FieldSpec("marking", ["маркировка"], [AsStr()]),
    FieldSpec("name", ["имя:"], [AsStr()], direction=Direction.RIGHT),
    FieldSpec("aufbau", ["aufbau:"], [AsStr()], direction=Direction.RIGHT),
    FieldSpec("thickness", ["толщина:"], [AsStr()], direction=Direction.RIGHT),
])


class TableParser:
    def __init__(self, table: SparseTable, matcher: FieldMatcher) -> None:
        self.matcher: FieldMatcher = matcher
        self.table: SparseTable = table
        self.blocks: list[Block] = []
        self._new_block_id: int = 0

    def last_block(self) -> Block | None:
        if self._new_block_id == 0:
            return None
        return self.blocks[-1]

    def create_block(self, row: int) -> Block:
        self.blocks.append(Block(id=self._new_block_id, start_row=row))
        self._new_block_id += 1
        return self.blocks[-1]

    def get_block_or_create(self, row: int) -> Block:
        last_block = self.last_block()
        if last_block:
            return last_block
        return self.create_block(row)

    def close_block_and_create_new(self, row: int) -> Block:
        last_block = self.last_block()
        if last_block is not None:
            last_block.end_row = row
        return self.create_block(row)

    def push_value_in_block(self, block: Block, row: int, col: int, cell: Cell) -> PushCallback:
        vfield = block.vertical_fields.get(col)
        if vfield is not None and not vfield.closed:
            return vfield.push(cell)

        hfield = block.horizontal_fields.get(row)
        if hfield is not None and not hfield.closed:
            return hfield.push(cell)

        return PushCallback()

    def add_field_in_block(self, block: Block, row: int, col: int, header: str, spec: FieldSpec) -> bool:
        field = FieldState(spec, header, (row, col), block.id)
        match spec.direction:
            case Direction.DOWN:
                block_field = block.vertical_fields.get(col)
                if block_field is None:
                    block.vertical_fields[col] = field
                    return True
            case Direction.RIGHT:
                block_field = block.horizontal_fields.get(row)
                if block_field is None:
                    block.horizontal_fields[row] = field
                    return True
        return False

    def parse(self) -> list[Block]:
        for row, col, cell in self.table.iter_cells():
            if isinstance(cell.value, int):
                block = self.last_block()
                if block is None:
                    continue
                response = self.push_value_in_block(block, row, col, cell)
            elif isinstance(cell.value, str):
                spec = self.matcher.match(cell.value)
                if spec is None:
                    block = self.last_block()
                    if block is None:
                        continue
                    response = self.push_value_in_block(block, row, col, cell)
                else:
                    block = self.last_block()
                    if block is None:
                        block = self.create_block(row)
                    field_added = self.add_field_in_block(block, row, col, spec)
                    if not field_added:
                        block = self.close_block_and_create_new(row)
                        field_added = self.add_field_in_block(block, row, col, spec)
        return self.blocks


def read(wb: Workbook) -> tuple[WorkbookReport, list[SparseTable]]:
    report = WorkbookReport(wb.name, with_metadata=wb.with_metadata)
    tables: list[SparseTable] = []
    for sheet in wb.sheets:
        subtable = SparseTable(name=sheet.name, nrows=sheet.nrows, ncols=sheet.ncols)
        report.add_sheet(name=sheet.name, nrows=sheet.nrows, ncols=sheet.ncols)
        for cell in sheet.cells:
            new_cell = subtable.add_cell(cell.value, cell.row, cell.col, cell.merged, cell.parent)
            report.add_cell_on_last_sheet(cell.row, cell.col, None if new_cell is None else new_cell.value, cell.merged)
            if cell.parent is not None:
                report.add_parent_on_last_sheet(*cell.parent)
        keeped_rows, keeped_cols = subtable.normalize()
        report.last_table_normalized(subtable.nrows, subtable.ncols, keeped_rows, keeped_cols)
        if not subtable.empty:
            tables.append(subtable)
        else:
            print(f"WARN: Empty sheet '{sheet.name}' in the workbook '{wb.name}'")
    return report, tables
