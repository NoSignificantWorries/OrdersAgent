from dataclasses import dataclass

from . import table_loader as tl


@dataclass(slots=True)
class Cell:
    value: int | str
    is_merge_child: bool = False


class SparseTable:
    def __init__(self, name: str | None, nrows: int, ncols: int) -> None:
        self.name = name
        self.nrows = nrows
        self.ncols = ncols

        self.cells: list[list[Cell | None]] = [[None] * self.ncols for _ in range(self.nrows)]

        self._empty_columns: list[int] = list(range(self.ncols))
        self._empty_rows: list[int] = list(range(self.nrows))

    @property
    def empty(self) -> bool:
        return self.nrows == 0 or self.ncols == 0

    def add_cell(self, value: int | str | None, row: int, col: int, merged: bool = False, parent: tuple[int, int] | None = None) -> None:
        if value is None:
            prow, pcol = parent
            parent_cell = self.cells[prow][pcol]
            if parent_cell is None:
                return
            cell = Cell(value=parent_cell.value, is_merge_child=True)
        else:
            cell = Cell(value=value)
        self.cells[row][col] = cell

        if value is not None:
            if col in self._empty_columns:
                idx = self._empty_columns.index(col)
                self._empty_columns.pop(idx)
            if row in self._empty_rows:
                idx = self._empty_rows.index(row)
                self._empty_rows.pop(idx)

    def normilize_cells(self) -> None:
        for r2d in self._empty_rows[::-1]:
            del self.cells[r2d]
        self.nrows -= len(self._empty_rows)

        for ri in range(self.nrows):
            for c2d in self._empty_columns[::-1]:
                del self.cells[ri][c2d]
        self.ncols -= len(self._empty_columns)

        self._empty_columns = []
        self._empty_rows = []
