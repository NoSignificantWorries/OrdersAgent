from dataclasses import dataclass, field

from table.annotate import Annotation, CellAnnotation, CellKind, CellRole
from table.loader import SparseTable


@dataclass(frozen=True, slots=True)
class ParsedCell:
    value: int | str | tuple[int, int]
    pos: tuple[int, int]
    kind: CellKind
    role: CellRole


@dataclass
class Cursor:
    position: tuple[int, int]
    table: SparseTable
    annotation: Annotation

    @property
    def row(self) -> int:
        return self.position[0]

    @property
    def col(self) -> int:
        return self.position[1]

    @property
    def at_end(self) -> bool:
        return self.position == self.table.size

    def _in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.table.nrows and 0 <= c < self.table.ncols

    def move(self, dr: int, dc: int) -> bool:
        r, c = self.row + dr, self.col + dc
        if not self._in_bounds(r, c):
            return False
        self.position = (r, c)
        return True

    def right(self) -> bool:  return self.move(0, +1)
    def left(self)  -> bool:  return self.move(0, -1)
    def down(self)  -> bool:  return self.move(+1, 0)
    def up(self)    -> bool:  return self.move(-1, 0)

    def next(self) -> bool:
        if self.at_end:
            return False
        r, c = self.position
        if c + 1 < self.table.ncols:
            self.position = (r, c + 1)
            return True
        if r + 1 < self.table.nrows:
            self.position = (r + 1, 0)
            return True
        self.position = self.table.size
        return False

    def seek(self, r: int, c: int) -> bool:
        if not self._in_bounds(r, c):
            return False
        self.position = (r, c)
        return True

    def get_cell(self) -> ParsedCell | None:
        cell = self.table.get_cell(*self.position)
        ann = self.annotation.get_cell(*self.position)
        if cell.value is None or ann is None:
            return None
        return ParsedCell(
            value=cell.value if ann.value is None else ann.value,
            pos=(cell.row, cell.col),
            kind=ann.kind,
            role=ann.role
        )


def find_targets(annotation: Annotation) -> dict[tuple[int, int], CellAnnotation]:
    return {pos: cell for pos, cell in annotation.cells.items() if cell.role == CellRole.HEADER}


def parse_column(table: SparseTable, annotation: Annotation, idx: int):
    targets = {pos: cell for pos, cell in annotation.cells.items() if pos[1] == idx and cell.role == CellRole.HEADER}
    print(targets)


def parse_columns(table: SparseTable, annotation:  Annotation):
    for c in range(table.ncols):
        parse_column(table, annotation, c)
