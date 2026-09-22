from collections.abc import Generator
from dataclasses import dataclass


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
