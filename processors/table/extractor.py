from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum

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

    def iter_rows(self) -> Generator[tuple[int, Generator], None, None]:
        for ir in range(self.table.nrows):
            yield ir, self.iter_through_row(ir)

    def iter_through_row(self, row: int) -> Generator[tuple[int, ResCell | None], None, None]:
        for ic in range(self.table.ncols):
            yield ic, self.get_cell(row, ic)

    def header_in_row(self, row: int) -> bool:
        return self.stats.header_in_row(row)

    def find_headers_in_row(self, row: int) -> dict[int, ResCell]:
        result = {}
        for ic, cell in self.iter_through_row(row):
            if cell is not None and cell.role == CellRole.HEADER:
                result[ic] = cell
        return result


class Direct(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True)
class FieldSpec:
    kind: CellKind
    direction: Direct
    roles: frozenset[CellRole]
    empty_allowed: bool


class FieldsRegistry:
    def __init__(self, specs: list[FieldSpec]) -> None:
        self.specs = {spec.kind: spec for spec in specs}

    def by_kind(self, kind: CellKind) -> FieldSpec | None:
        return self.specs.get(kind)

    def direction_by_kind(self, kind: CellKind) -> Direct | None:
        spec = self.specs.get(kind)
        if spec is None:
            return spec
        return spec.direction


default_registry = FieldsRegistry([
    FieldSpec(CellKind.AUFBAU, Direct.HORIZONTAL, frozenset({CellRole.LABEL}), False),
    FieldSpec(CellKind.NAME, Direct.HORIZONTAL, frozenset({CellRole.LABEL}), False),
    FieldSpec(CellKind.THICKNESS, Direct.HORIZONTAL, frozenset({CellRole.LABEL}), False),
    FieldSpec(CellKind.MATERIAL, Direct.VERTICAL, frozenset({CellRole.LABEL}), False),
    FieldSpec(CellKind.AMOUNT, Direct.VERTICAL, frozenset({CellRole.NUMERIC}), False),
    FieldSpec(CellKind.SIZE, Direct.VERTICAL, frozenset({CellRole.NUMERIC}), False),
    FieldSpec(CellKind.BARCODE, Direct.VERTICAL, frozenset({CellRole.NUMERIC, CellRole.LABEL}), True),
    FieldSpec(CellKind.MARKING, Direct.VERTICAL, frozenset({CellRole.NUMERIC, CellRole.LABEL}), True),
])


@dataclass
class Field:
    spec: FieldSpec
    sources: list[tuple[int, int]]

    @property
    def kind(self) -> CellKind:
        return self.spec.kind


class FieldsPipeline:
    @classmethod
    def header_to_field(cls, cell: ResCell) -> Field | None:
        spec = default_registry.by_kind(cell.kind)
        if spec is None:
            return None
        return Field(spec, [(cell.row, cell.col)])


    @classmethod
    def headers_to_fields(cls, headers: dict[int, ResCell]) -> dict[int, Field]:
        result = {}
        for ir, cell in headers.items():
            field = cls.header_to_field(cell)
            if field is not None:
                result[ir] = field
        return result


    @classmethod
    def find_target_headers(cls, source: Source) -> dict[int, dict[int, Field]]:
        target_rows = {}
        for ir, _ in source.iter_rows():
            if source.header_in_row(ir):
                headers = source.find_headers_in_row(ir)
                target_rows[ir] = cls.headers_to_fields(headers)
        return target_rows


    @classmethod
    def merge_fields(cls, up_field: Field | None, low_field: Field | None) -> Field | None:
        if up_field is None and low_field is None:
            return None
        if up_field is not None and low_field is not None:
            if up_field.kind == low_field.kind:
                return Field(low_field.spec, up_field.sources + low_field.sources)
            return None

        if up_field:
            return up_field
        return low_field


    @classmethod
    def merge_rows(cls, upper_row: dict[int, Field], lower_row: dict[int, Field]) -> dict[int, Field] | None:
        keys = set(upper_row.keys()) | set(lower_row.keys())
        result = {}
        for key in keys:
            up = upper_row.get(key)
            low = lower_row.get(key)
            merged_cells = cls.merge_fields(up, low)
            if merged_cells is None:
                return None
            result[key] = merged_cells
        return result


    @classmethod
    def merge_target_headers(cls, target_headers: dict[int, dict[int, Field]]) -> dict[int, dict[int, Field]]:
        if len(target_headers) < 2:
            return target_headers

        res = {}
        rows = list(target_headers.items())
        last_row = rows[0]
        for ir, row_headers in rows[1:]:
            if ir - last_row[0] == 1:
                merged = cls.merge_rows(last_row[1], row_headers)
                if merged is None:
                    res[last_row[0]] = last_row[1]
                    last_row = (ir, row_headers)
                else:
                    last_row = (ir, merged)
            else:
                res[last_row[0]] = last_row[1]
                last_row = (ir, row_headers)
        res[last_row[0]] = last_row[1]
        return res

    @classmethod
    def run(cls, source: Source) -> dict[int, dict[int, Field]]:
        target_headers = cls.find_target_headers(source)
        merged_fields = cls.merge_target_headers(target_headers)
        return merged_fields
