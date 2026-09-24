from collections.abc import Generator
from dataclasses import dataclass


@dataclass(slots=True)
class Cell:
    row: int
    col: int
    value: int | str | tuple[int, int] | None = None


class SparseTable:
    def __init__(self, nrows: int, ncols: int) -> None:
        self.nrows = nrows
        self.ncols = ncols

        self.cells: list[list[Cell]] = [[Cell(r, c) for c in range(self.ncols)] for r in range(self.nrows)]

    @property
    def empty(self) -> bool:
        return self.nrows == 0 or self.ncols == 0

    def add_cell(self, value: int | str | None, row: int, col: int) -> Cell | None:
        cell = Cell(row, col, value)
        self.cells[row][col] = cell
        return cell

    def normalize(self) -> tuple[list[int], list[int]]:
        keep_rows: set[int] | list[int] = set()
        keep_cols: set[int] | list[int] = set()
        for r in range(self.nrows):
            for c in range(self.ncols):
                if self.cells[r][c].value is not None:
                    keep_cols.add(c)
                    keep_rows.add(r)
        keep_rows = sorted(keep_rows)
        keep_cols = sorted(keep_cols)
        self.cells = [[self.cells[r][c] for c in keep_cols] for r in keep_rows]
        self.nrows = len(keep_rows)
        self.ncols = len(keep_cols)

        for i in range(self.nrows):
            for j in range(self.ncols):
                self.cells[i][j].row = i
                self.cells[i][j].col = j

        return keep_rows, keep_cols

    def get_cell(self, row: int, col: int) -> Cell:
        return self.cells[row][col]

    def iter_cells(self) -> Generator[tuple[int, int, Cell], None, None]:
        for i in range(self.nrows):
            for j in range(self.ncols):
                cell = self.get_cell(i, j)
                yield i, j, cell
