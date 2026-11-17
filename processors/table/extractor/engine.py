from table.annotate import AnnotatedTable, CellRole, ResCell


class TableEngine:
    def __init__(self, table: AnnotatedTable) -> None:
        self.table = table

    def get_cell(self, row: int, col: int) -> ResCell | None:
        if 0 <= row < self.table.nrows and 0 <= col < self.table.ncols:
            return self.table.table[row][col]
        return None

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.table.nrows and 0 <= col < self.table.ncols

    def range_rows(self, start: int = 0) -> range:
        return range(start, self.table.nrows)

    def range_cols(self, start: int = 0) -> range:
        return range(start, self.table.ncols)

    def has_header_in_row(self, row: int) -> bool:
        return CellRole.HEADER in self.table.stats.roles_in_row.get(row, set())

    def has_header_in_col(self, col: int) -> bool:
        return CellRole.HEADER in self.table.stats.roles_in_col.get(col, set())


Pos = tuple[int, int]

def cell(engine: TableEngine, pos: Pos) -> ResCell | None:
    return engine.get_cell(*pos)

def shifted(engine: TableEngine, pos: Pos, dr: int, dc: int) -> Pos | None:
    r, c = pos[0] + dr, pos[1] + dc
    return (r, c) if engine.in_bounds(r, c) else None
