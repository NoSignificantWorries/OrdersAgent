from collections.abc import Generator
from dataclasses import dataclass, field

from table.annotate import Annotation, CellKind, CellRole, Stats
from table.loader import SparseTable


@dataclass(frozen=True, slots=True)
class ResCell:
    value: int | str | tuple[int, int]
    row: int
    col: int
    kind: CellKind
    role: CellRole


@dataclass(frozen=True)
class Source:
    table: SparseTable
    annotation: Annotation
    stats: Stats

    def get_cell(self, row: int, col: int) -> ResCell | None:
        origin_cell = self.table.get_cell(row, col)
        ann_cell = self.annotation.get_cell(row, col)

        if origin_cell.value is None:
            return None

        if ann_cell is None:
            return ResCell(
                value=origin_cell.value,
                row=origin_cell.row,
                col=origin_cell.col,
                kind=CellKind.UNKNOWN,
                role=CellRole.UNKNOWN
            )

        return ResCell(
            value=origin_cell.value if ann_cell.value is None else ann_cell.value,
            row=origin_cell.row,
            col=origin_cell.col,
            kind=ann_cell.kind,
            role=ann_cell.role
        )

    def iter_through_row(self, row: int) -> Generator[tuple[int, ResCell | None], None, None]:
        for ic in range(self.table.ncols):
            yield ic, self.get_cell(row, ic)

    def header_in_row(self, row: int) -> bool:
        return self.stats.header_in_row(row)
