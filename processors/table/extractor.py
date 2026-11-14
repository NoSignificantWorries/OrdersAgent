from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Self

from table.annotate import AnnotatedTable, CellKind, CellRole, ResCell


class TableEngine:
    def __init__(self, annotated_table: AnnotatedTable) -> None:
        self.table = annotated_table

    def _check_col(self, col: int) -> bool:
        return 0 <= col < self.table.ncols

    def _check_row(self, row: int) -> bool:
        return 0 <= row < self.table.nrows

    def get_cell(self, row: int, col: int) -> ResCell | None:
        if self._check_col(col) and self._check_row(row):
            return self.table.table[row][col]
        return None

    def range_rows(self) -> range:
        return range(self.table.nrows)

    def range_cols(self) -> range:
        return range(self.table.ncols)

    def row_roles(self, row: int) -> set[CellRole]:
        if self._check_col(row + 1):
            return self.table.stats.roles_in_row.get(row, set())
        return set()

    def row_kinds(self, row: int) -> set[CellRole]:
        if self._check_col(row + 1):
            return self.table.stats.roles_in_row.get(row, set())
        return set()

    def col_roles(self, col: int) -> set[CellRole]:
        if self._check_col(col + 1):
            return self.table.stats.roles_in_row.get(col, set())
        return set()

    def col_kinds(self, col: int) -> set[CellKind]:
        if self._check_col(col + 1):
            return self.table.stats.kinds_in_col.get(col, set())
        return set()

    def header_in_row(self, row: int) -> bool:
        return CellRole.HEADER in self.table.stats.roles_in_row.get(row, {})

    def header_in_col(self, col: int) -> bool:
        return CellRole.HEADER in self.table.stats.roles_in_col.get(col, {})


class Watch:
    def __init__(self, engine: TableEngine, row: int = 0, col: int = 0) -> None:
        self.engine = engine
        if self._check_row(row) and self._check_col(col):
            self.row: int = row
            self.col: int = col
        else:
            raise IndexError("Position in table isn't valid")

    @property
    def pos(self) -> tuple[int, int]:
        return self.row, self.col

    def _check_col(self, col: int) -> bool:
        return 0 <= col < self.engine.table.ncols

    def _check_row(self, row: int) -> bool:
        return 0 <= row < self.engine.table.nrows

    def zero(self) -> Self:
        self.row = 0
        self.col = 0
        return self

    def set_pos(self, row: int, col: int) -> Self | None:
        if self._check_col(col) and self._check_row(row):
            self.row = row
            self.col = col
            return self
        return None

    def shift(self, row_shift: int = 0, col_shift: int = 0) -> Self | None:
        if self._check_col(self.col + col_shift) and self._check_row(self.row + row_shift):
            self.row += row_shift
            self.col += col_shift
            return self
        return None

    def watch(self) -> ResCell | None:
        return self.engine.get_cell(*self.pos)

    def next(self) -> Self | None:
        if self._check_col(self.col + 1):
            self.col += 1
            return self
        else:
            if self._check_row(self.row + 1):
                self.row += 1
                self.col = 0
                return self
        return None

    def left(self, step: int = 1, watch: bool = False) -> Self | None | ResCell:
        if self._check_col(self.col - step) and step > 0:
            self.col -= step
            if watch:
                return self.watch()
            return self
        return None

    def right(self, step: int = 1, watch: bool = False) -> Self | None | ResCell:
        if self._check_col(self.col + step) and step > 0:
            self.col += step
            if watch:
                return self.watch()
            return self
        return None

    def down(self, step: int = 1) -> Self | None:
        if self._check_row(self.row + step) and step >= 0:
            self.row += step
            return self
        return None


class Direction(Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True)
class FieldSpec:
    kind: CellKind
    roles: set[CellRole]
    direction: Direction
    none_allowed: bool


@dataclass(slots=True)
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


class HeaderType(Enum):
    STANDART = "standart"
    ONE_SIZE_COLUMN = "one-size-column"
    OKNA_DATA = "okna-data"


@dataclass(frozen=True)
class HeaderSpec:
    type: HeaderType
    scheme: dict[CellKind, tuple[int, int]]
    priority: int = 0

    def valid(self, lst: list[CellKind]) -> bool:
        counts = Counter(lst)
        if not counts.keys() <= self.scheme.keys():
            return False
        for kind, (lo, hi) in self.scheme.items():
            n = counts.get(kind, 0)
            if n < lo or n > hi:
                return False
        return True

    def submatch(self, lst: list[CellKind]) -> bool:
        counts = Counter(lst)
        for kind, (_, hi) in self.scheme.items():
            n = counts.get(kind, 0)
            if n > hi:
                return False
        return True

    def full(self, lst: list[CellKind]) -> bool:
        counts = Counter(lst)
        for key, (_, hi) in self.scheme.items():
            n = counts.get(key, 0)
            if n != hi:
                return False
        return True


class HeadersRegistry:
    def __init__(self, specs: list[HeaderSpec]) -> None:
        self.specs = sorted(specs, key=lambda s: s.priority, reverse=True)
        self.kinds = set()
        for spec in specs:
            for kind in spec.scheme:
                self.kinds.add(kind)

    def kind_in(self, kind: CellKind) -> bool:
        return kind in self.kinds

    def sort_matched(self, lst: list[CellKind], matched: list[HeaderSpec]) -> list[HeaderSpec]:
        return sorted(
            matched,
            key=lambda s: (s.valid(lst), s.priority),
            reverse=True,
        )

    def subschemes(self, lst: list[CellKind]) -> list[HeaderSpec]:
        res = []
        for spec in self.specs:
            if spec.submatch(lst):
                res.append(spec)
        return self.sort_matched(lst, res)

    def full_matched(self, lst: list[CellKind]) -> HeaderSpec | None:
        for spec in self.specs:
            if spec.full(lst):
                return spec
        return None


@dataclass
class Header:
    index: int
    fields: list[Field]
    specs: list[HeaderSpec]


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

    @classmethod
    def build_default_headers_registry(cls) -> HeadersRegistry:
        return HeadersRegistry([
            HeaderSpec(HeaderType.ONE_SIZE_COLUMN, {
                CellKind.MATERIAL: (1, 1),
                CellKind.SIZE: (1, 1),
                CellKind.AMOUNT: (1, 1),
                CellKind.BARCODE: (0, 1),
                CellKind.MARKING: (0, 1)
            }, priority=200),
            HeaderSpec(HeaderType.STANDART, {
                CellKind.MATERIAL: (1, 1),
                CellKind.SIZE: (2, 2),
                CellKind.AMOUNT: (1, 1),
                CellKind.BARCODE: (0, 1),
                CellKind.MARKING: (0, 1)
            }, priority=100),
            HeaderSpec(HeaderType.OKNA_DATA, {
                CellKind.SIZE: (2, 2),
                CellKind.AMOUNT: (1, 1),
                CellKind.BARCODE: (0, 1),
                CellKind.MARKING: (0, 1)
            }, priority=50),
        ])

    def __init__(self, annotated_table: AnnotatedTable) -> None:
        self.engine = TableEngine(annotated_table)
        self.fregistry = self.build_default_fields_registry()
        self.hregistry = self.build_default_headers_registry()

    def mark_header_rows(self) -> list[int]:
        return [irow for irow in self.engine.range_rows() if self.engine.header_in_row(irow)]

    def mark_header_cols(self) -> list[int]:
        return [icol for icol in self.engine.range_cols() if self.engine.header_in_col(icol)]

    def make_field(self, cell: ResCell) -> Field | None:
        spec = self.fregistry.get_by_kind(cell.kind)
        if spec is None:
            return None
        return  Field(
            cell.col,
            [(cell.row, cell.col)],
            spec
        )

    def make_fields_in_row(self, irow: int, hcols: list[int]) -> dict[int, Field]:
        fields = {}
        for icol in hcols:
            cell = self.engine.get_cell(irow, icol)
            if cell is None:
                break
            if cell.role is CellRole.HEADER:
                field = self.make_field(cell)

                if field is None:
                    continue

                fields[icol] = field
        return fields

    def make_fields(self, hrows: list[int], hcols: list[int]) -> dict[int, dict[int, Field]]:
        fields = {}
        for irow in hrows:
            fields[irow] = self.make_fields_in_row(irow, hcols)

        return fields

    def size_pair(self, fields: dict[int, dict[int, Field]]):
        def check_brother(ir: int, ic: int) -> bool:
            watch = Watch(self.engine, ir, ic)
            right = watch.right(watch=True)
            if right is None or right.kind != CellKind.EMPTY:
                return False

            datacol = watch.shift(+1, +1)
            while datacol is not None:
                left = datacol.left(watch=True)
                if left is None:
                    break

                if datacol.watch().role == CellRole.NUMERIC and left.role == CellRole.NUMERIC:
                    return True

                if datacol.watch().kind == CellKind.EMPTY:
                    datacol.down()
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
                        [(irow, icol + 1)],
                        spec
                    )

        return {
            irow: {icol: row[icol] for icol in sorted(row)}
            for irow, row in new_fields.items()
        }

    def merge_fields(self, field1: Field | None, field2: Field | None) -> Field | None:
        if field1 and field2 and field1.spec.kind == field2.spec.kind:
            if field1.index != field2.index:
                return None
            return Field(
                field2.index,
                field1.sources + field2.sources,
                field2.spec
            )
        if field1 and not field2:
            return field1
        if field2 and not field1:
            return field2
        return None

    def merge_two_rows(self, row1: dict[int, Field], row2: dict[int, Field]) -> dict[int, Field] | None:
        keys = set(row1.keys()) | set(row2.keys())
        res: dict[int, Field] = {}
        for key in keys:
            f1 = row1.get(key)
            f2 = row2.get(key)
            merged = self.merge_fields(f1, f2)
            if merged is None:
                return None
            res[key] = merged

        return res

    def merge_lines(self, fields_rows: dict[int, dict[int, Field]]) -> dict[int, dict[int, Field]]:
        if len(fields_rows) < 2:
            return fields_rows

        objects = list(fields_rows.items())
        last = objects[0]

        res: dict[int, dict[int, Field]] = {}
        for irow, row in objects[1:]:
            if irow - last[0] == 1:
                merged = self.merge_two_rows(last[1], row)
                if merged is not None:
                    last = irow, merged
                    continue
            res[last[0]] = last[1]
            last = irow, row
        res[last[0]] = last[1]
        return res

    def build_headers_in_row(self, irow: int, row: dict[int, Field]) -> list[Header]:
        row_headers: list[Header] = []

        last_schemes: list[HeaderSpec] = []
        fields: list[Field] = []
        kinds: list[CellKind] = []
        for field in row.values():
            fkind = field.spec.kind
            if not self.hregistry.kind_in(fkind):
                continue
            matched = self.hregistry.subschemes(kinds + [fkind])
            if matched:
                last_schemes = matched
                kinds.append(fkind)
                fields.append(field)
            elif last_schemes:
                row_headers.append(Header(
                    irow,
                    fields,
                    last_schemes
                ))
                kinds = [fkind]
                fields = [field]
                last_schemes = self.hregistry.subschemes(kinds)

        if last_schemes and fields:
            row_headers.append(Header(
                irow,
                fields,
                last_schemes
            ))

        return row_headers

    def build_header_objects(self, header_rows: dict[int, dict[int, Field]]) -> dict[int, list[Header]]:
        headers: dict[int, list[Header]] = {}
        for irow, row in header_rows.items():
            headers[irow] = self.build_headers_in_row(irow, row)

        return headers


    def run(self) -> None:
        header_rows = self.mark_header_rows()
        header_cols = self.mark_header_cols()

        fields_matrix = self.make_fields(header_rows, header_cols)
        size_paired_fields = self.size_pair(fields_matrix)
        for i, row in size_paired_fields.items():
            for j, field in row.items():
                print(f"({i}, {j}): {field.index}: {field.sources}: {field.spec.kind.name}")
            print("---")
        merged_rows = self.merge_lines(size_paired_fields)
        print("\n")
        for i, row in merged_rows.items():
            for j, field in row.items():
                print(f"({i}, {j}): {field.index}: {field.sources}: {field.spec.kind.name}")
            print("---")
        headers = self.build_header_objects(merged_rows)
        for i, header in headers.items():
            for h in header:
                for spec in h.specs:
                    print(f"{i} ({spec.type.name}):", [f.spec.kind.name for f in h.fields], spec.valid([f.spec.kind for f in h.fields]))
