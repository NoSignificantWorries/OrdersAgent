from dataclasses import dataclass
from enum import Enum

from table.annotate import AnnotatedTable, CellKind, CellRole, ResCell


class TableEngine:
    def __init__(self, annotated_table: AnnotatedTable) -> None:
        self.table = annotated_table

    def cell(self, row: int, col: int) -> ResCell | None:
        if 0 <= row < self.table.nrows and 0 <= col < self.table.ncols:
            return self.table.table[row][col]
        return None

    def range_rows(self) -> range:
        return range(self.table.nrows)

    def range_cols(self) -> range:
        return range(self.table.ncols)

    def row_roles(self, row: int) -> set[CellRole]:
        return self.table.stats.roles_in_row.get(row, set())

    def row_kinds(self, row: int) -> set[CellRole]:
        return self.table.stats.roles_in_row.get(row, set())

    def col_roles(self, col: int) -> set[CellRole]:
        return self.table.stats.roles_in_row.get(col, set())

    def col_kinds(self, col: int) -> set[CellKind]:
        return self.table.stats.kinds_in_col.get(col, set())

    def header_in_row(self, row: int) -> bool:
        return CellRole.HEADER in self.table.stats.roles_in_row.get(row, {})

    def header_in_col(self, col: int) -> bool:
        return CellRole.HEADER in self.table.stats.roles_in_col.get(col, {})


class Direction(Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True)
class FieldSpec:
    kind: CellKind
    roles: set[CellRole]
    direction: Direction
    none_allowed: bool


@dataclass
class Field:
    index: int
    sources: list[tuple[int, int]]
    spec: FieldSpec


class FieldsRegistry:
    def __init__(self, specs: list[FieldSpec]) -> None:
        self.specs = specs
        self.by_kind = {spec.kind: spec for spec in specs}

    def get_by_kind(self, kind: CellKind) -> FieldSpec | None:
        return self.by_kind.get(kind)


class ExtractorPipeline:
    @classmethod
    def build_default_fields_registry(cls) -> FieldsRegistry:
        return FieldsRegistry([
            FieldSpec(CellKind.MATERIAL, {CellRole.LABEL}, Direction.VERTICAL, False),
            FieldSpec(CellKind.SIZE, {CellRole.SIZES, CellRole.NUMERIC}, Direction.VERTICAL, False),
            FieldSpec(CellKind.AMOUNT, {CellRole.NUMERIC}, Direction.VERTICAL, False),
            FieldSpec(CellKind.BARCODE, {CellRole.LABEL, CellRole.NUMERIC}, Direction.VERTICAL, True),
            FieldSpec(CellKind.MARKING, {CellRole.LABEL, CellRole.NUMERIC}, Direction.VERTICAL, True),
        ])

    def __init__(self, annotated_table: AnnotatedTable) -> None:
        self.engine = TableEngine(annotated_table)
        self.fregistry = self.build_default_fields_registry()

    def mark_header_rows(self) -> list[int]:
        return [irow for irow in self.engine.range_rows() if self.engine.header_in_row(irow)]

    def mark_header_cols(self) -> list[int]:
        return [icol for icol in self.engine.range_cols() if self.engine.header_in_col(icol)]

    def make_fields_in_row(self, irow: int, hcols: list[int]) -> dict[int, Field]:
        fields = {}
        for icol in hcols:
            cell = self.engine.cell(irow, icol)
            if cell is None:
                break
            if cell.role is CellRole.HEADER:
                spec = self.fregistry.get_by_kind(cell.kind)

                if spec is None:
                    continue

                fields[icol] = Field(
                    icol,
                    [(irow, icol)],
                    spec
                )
        return fields

    def make_fields(self, hrows: list[int], hcols: list[int]) -> dict[int, dict[int, Field]]:
        fields = {}
        for irow in hrows:
            fields[irow] = self.make_fields_in_row(irow, hcols)

        return fields

    def size_pair(self, fields: dict[int, dict[int, Field]]):
        def check_brother(ir: int, ic: int) -> bool:
            right_cell = self.engine.cell(ir, ic + 1)
            if right_cell is None or right_cell.kind != CellKind.EMPTY:
                return False

            cell = self.engine.cell(ir + 1, ic + 1)
            while cell is not None:
                left_cell = self.engine.cell(cell.row, cell.col - 1)
                if left_cell is None:
                    break

                if cell.role == CellRole.NUMERIC and left_cell.role == CellRole.NUMERIC:
                    return True

                if cell.kind == CellKind.EMPTY:
                    cell = self.engine.cell(cell.row + 1, cell.col)
                    continue

                break
            return False

        new_fields = {r: dict(row) for r, row in fields.items()}
        for irow, row in fields.items():
            for icol, field in row.items():
                if field.spec.kind == CellKind.SIZE and check_brother(irow, icol):
                    spec = self.fregistry.get_by_kind(CellKind.SIZE)

                    if spec is None:
                        return fields

                    new_fields[irow][icol + 1] = Field(
                        icol + 1,
                        [(irow, icol)],
                        spec
                    )

        return {
            irow: {icol: row[icol] for icol in sorted(row)}
            for irow, row in new_fields.items()
        }

    def run(self) -> None:
        header_rows = self.mark_header_rows()
        header_cols = self.mark_header_cols()

        fields_matrix = self.make_fields(header_rows, header_cols)
        print(fields_matrix)
        size_paired_fields = self.size_pair(fields_matrix)
        print(size_paired_fields)
