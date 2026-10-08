from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum

from table.annotate import Annotation, CellAnnotation, CellKind, CellRole, Stats
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



class Direct(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"

    @classmethod
    def kind_to_direction(cls, kind: CellKind) -> "Direct":
        return cls.VERTICAL


class FieldReq(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class FieldSpec:
    kind: CellKind
    roles: frozenset[CellRole] = frozenset()
    min_count: int = 1
    max_count: int = 1
    allow_none: bool = False
    req: FieldReq = FieldReq.REQUIRED


class TableKind(str, Enum):
    STANDART = "standart"
    ONE_SIZE_COLUMN = "one_size_column"


@dataclass(frozen=True)
class TableScheme:
    kind: TableKind
    priority: int
    fields: tuple[FieldSpec, ...]

    def spec_by_kind(self, kind: CellKind) -> FieldSpec | None:
        for spec in self.fields:
            if kind == spec.kind:
                return spec
        return None


@dataclass
class Field:
    kind: CellKind
    index: int
    data_roles: set[CellRole]
    sources: list[tuple[int, int]]


@dataclass
class Chain:
    direction: Direct
    fields: list[Field] = field(default_factory=list)
    kind_counts: dict[CellKind, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.fields)

    @property
    def start(self) -> int:
        if self.size > 0:
            return self.fields[0].index
        return -1

    @property
    def end(self) -> int:
        if self.size > 0:
            return self.fields[-1].index
        return -1

    def push_field(self, field: Field) -> None:
        self.fields.append(field)
        self.kind_counts[field.kind] = self.kind_counts.get(field.kind, 0) + 1

    def last(self) -> Field | None:
        if self.size > 0:
            return self.fields[-1]
        return None


@dataclass
class SchemeRegistry:
    schemes: dict[TableKind, TableScheme] = field(default_factory=dict)

    def register(self, scheme: TableScheme) -> None:
        self.schemes[scheme.kind] = scheme

    def get(self, kind: TableKind) -> TableScheme | None:
        return self.schemes.get(kind)

    def match(self, chain: Chain) -> list[TableScheme]:
        return [spec for spec in self.schemes.values() if self._fits(chain, spec)]

    @staticmethod
    def _fits(chain: Chain, scheme: TableScheme) -> bool:
        for kind, cnt in chain.kind_counts.items():
            field_spec = scheme.spec_by_kind(kind)
            # kind not in the table scheme, doesn't fit
            if field_spec is None:
                return False

            # check field counts in the chain by the scheme
            if not (field_spec.min_count <= cnt <= field_spec.max_count):
                return False
        return True


def make_schemes_defaults() -> SchemeRegistry:
    registry = SchemeRegistry()

    registry.register(TableScheme(kind=TableKind.STANDART, priority=100, fields=(
        FieldSpec(CellKind.MARKING, frozenset({CellRole.LABEL}), allow_none=True),
        FieldSpec(CellKind.SIZE, frozenset({CellRole.NUMERIC}), min_count=2, max_count=2),
        FieldSpec(CellKind.AMOUNT, frozenset({CellRole.NUMERIC})),
        FieldSpec(CellKind.MARKING, frozenset({CellRole.NUMERIC, CellRole.LABEL}), allow_none=True, req=FieldReq.OPTIONAL),
        FieldSpec(CellKind.BARCODE, frozenset({CellRole.NUMERIC, CellRole.LABEL}), allow_none=True, req=FieldReq.OPTIONAL)
    )))

    registry.register(TableScheme(kind=TableKind.ONE_SIZE_COLUMN, priority=200, fields=(
        FieldSpec(CellKind.MARKING, frozenset({CellRole.LABEL}), allow_none=True),
        FieldSpec(CellKind.SIZE, frozenset({CellRole.NUMERIC})),
        FieldSpec(CellKind.AMOUNT, frozenset({CellRole.NUMERIC})),
        FieldSpec(CellKind.MARKING, frozenset({CellRole.NUMERIC, CellRole.LABEL}), allow_none=True, req=FieldReq.OPTIONAL),
        FieldSpec(CellKind.BARCODE, frozenset({CellRole.NUMERIC, CellRole.LABEL}), allow_none=True, req=FieldReq.OPTIONAL)
    )))

    return registry


def _break_chain_by_basic_rule(chain: Chain, field: Field) -> bool:
    _BASIC_RULESET: dict[CellKind, int] = {
        CellKind.AMOUNT: 1,
        CellKind.MATERIAL: 1,
        CellKind.SIZE: 2,
        CellKind.MARKING: 1,
        CellKind.BARCODE: 1
    }

    if field.kind in _BASIC_RULESET:
        kind_count = chain.kind_counts.get(field.kind, 0)
        if kind_count >= _BASIC_RULESET[field.kind]:
            return True
    return False


def _empty_cell_after_sizes(chain: Chain, idx: int, cell: ResCell | None) -> tuple[bool, CellKind | None]:
    if chain.last() is None:
        return False, None

    if chain.last().kind == CellKind.SIZE and \
       cell is None and \
       chain.kind_counts.get(CellKind.SIZE, 0) == 1 and \
       idx - chain.last().index == 1:
        return True, CellKind.SIZE

    return False, None



def make_chains_in_row(row: int, source: Source) -> list[Chain]:
    roles_by_kind: dict[CellKind, set[CellRole]] = {
            CellKind.MATERIAL: {CellRole.LABEL},
            CellKind.AMOUNT: {CellRole.NUMERIC},
            CellKind.SIZE: {CellRole.NUMERIC, CellRole.SIZES},
            CellKind.MARKING: {CellRole.NUMERIC, CellRole.LABEL},
            CellKind.BARCODE: {CellRole.NUMERIC, CellRole.LABEL}
        }

    chains = []
    last_chain = None
    for ic, cell in source.iter_through_row(row):
        if last_chain is not None:
            rule_valid, kind_for_cell = _empty_cell_after_sizes(last_chain, ic, cell)
            if rule_valid and kind_for_cell is not None:
                last_chain.push_field(Field(
                    index=ic,
                    kind=kind_for_cell,
                    data_roles=roles_by_kind.get(kind_for_cell, set()),
                    sources=[(row, ic)]
                ))
                continue

        if cell is None or cell.kind not in roles_by_kind:
            continue

        if last_chain is None:
            last_chain = Chain(Direct.HORIZONTAL)

        new_field = Field(
            index=cell.col,
            kind=cell.kind,
            data_roles=roles_by_kind.get(cell.kind, set()),
            sources=[(cell.row, cell.col)]
        )
        if _break_chain_by_basic_rule(last_chain, new_field):
            chains.append(last_chain)
            last_chain = Chain(Direct.HORIZONTAL)
        last_chain.push_field(new_field)

    if last_chain is not None:
        chains.append(last_chain)

    return chains


def make_horizontal_chains(source: Source) -> dict[int, list[Chain]]:
    chains_per_row: dict[int, list[Chain]] = {}
    for ir in range(source.table.nrows):
        if not source.header_in_row(ir):
            continue

        chains = make_chains_in_row(ir, source)
        if bool(chains):
            chains_per_row[ir] = chains

    return chains_per_row


def chains_overlapse(chain1: Chain, chain2: Chain) -> bool:
    return not (chain1.end < chain2.start or chain2.end < chain1.start)


def merge_chains(chain1: Chain, chain2: Chain) -> Chain | None:
    if chain1.direction != chain2.direction:
        return None
    if not chains_overlapse(chain1, chain2):
        return None

    new_chain = Chain(chain1.direction)
    i = j = 0
    f1, f2 = chain1.fields, chain2.fields

    while i < len(f1) and j < len(f2):
        a, b = f1[i], f2[j]
        if a.index < b.index:
            new_chain.push_field(a)
            i += 1
        elif a.index > b.index:
            new_chain.push_field(b)
            j += 1
        elif a.kind != b.kind:
            return None
        else:
            new_chain.push_field(Field(a.index, a.kind, a.data_roles, a.sources + b.sources))
            i += 1
            j += 1

    for a in f1[i:]:
        new_chain.push_field(a)
    for b in f2[j:]:
        new_chain.push_field(b)

    return new_chain

def merge_chain_rows(upper: list[Chain], lower: list[Chain]) -> tuple[list[Chain], list[Chain]]:
    upper = sorted(upper, key=lambda o: o.start)
    lower = sorted(lower, key=lambda o: o.start)

    new_upper: list[Chain] = []
    new_lower: list[Chain] = []
    i = j = 0

    while i < len(upper) and j < len(lower):
        u, l = upper[i], lower[j]

        if u.start <= l.end and l.start <= u.end:
            merged = merge_chains(u, l)
            if merged is not None:
                new_lower.append(merged)
                i += 1
                j += 1
                continue

            if u.end <= l.end:
                new_upper.append(u)
                i += 1
            else:
                new_lower.append(l)
                j += 1
        elif u.end < l.start:
            new_upper.append(u)
            i += 1
        else:
            new_lower.append(l)
            j += 1

    new_upper.extend(upper[i:])
    new_lower.extend(lower[j:])

    return new_upper, new_lower


def merge_chains_in_table(chains: dict[int, list[Chain]]) -> dict[int, list[Chain]]:
    if len(chains) < 2:
        return chains

    keys = sorted(chains)
    result = {keys[0]: chains[keys[0]]}
    for i in range(len(chains) - 1):
        current_row = result[keys[i]]
        next_row = chains[keys[i + 1]]
        if keys[i + 1] - keys[i] == 1:
            m1, m2 = merge_chain_rows(current_row, next_row)
            if m1:
                result[keys[i]] = m1
                result[keys[i + 1]] = m2
            else:
                del result[keys[i]]
                result[keys[i + 1]] = m2
        else:
            result[keys[i + 1]] = chains[keys[i + 1]]

    return result


def validate_table_by_header_scheme(chain: Chain, scheme: dict[CellKind, list[int]]) -> bool:
    for key, counts in scheme.items():
        table_count = chain.kind_counts.get(key, 0)
        if table_count not in counts:
            return False
    return True


class Scheme(str, Enum):
    STANDART = "standart"
    ONE_COLUMN_SIZE = "one_column_size"
    WITHOUT_MATERIAL = "without_material"
    UNKNOWN = "unknown"


@dataclass
class Table:
    header_chain: Chain
    data_rows: dict[int, list[ResCell | None]] = field(default_factory=dict)
    scheme: Scheme | None = None

    @property
    def nrows(self) -> int:
        return len(self.data_rows)

    @property
    def empty(self) -> bool:
        return self.nrows == 0

    def add_row(self, idx: int, row: list[ResCell | None]) -> None:
        self.data_rows[idx] = row

    def classify_table(self) -> Scheme:
        standart = {
            CellKind.MATERIAL: [1],
            CellKind.AMOUNT: [1],
            CellKind.SIZE: [2],
            CellKind.MARKING: [0, 1],
            CellKind.BARCODE: [0, 1]
        }
        one_column_size = {
            CellKind.MATERIAL: [1],
            CellKind.AMOUNT: [1],
            CellKind.SIZE: [1],
            CellKind.MARKING: [0, 1],
            CellKind.BARCODE: [0, 1]
        }
        if validate_table_by_header_scheme(self.header_chain, standart):
            return Scheme.STANDART
        if validate_table_by_header_scheme(self.header_chain, one_column_size):
            return Scheme.ONE_COLUMN_SIZE

        return Scheme.UNKNOWN


def get_data_by_horizontal_chain(chain_row: int, chain: Chain, source: Source) -> Table:
    subtable: Table = Table(chain)
    row_error: bool = False
    for row_index in range(chain_row + 1, source.table.nrows):
        if row_error:
            break
        data_row: list[ResCell | None] = []
        for field in chain.fields:
            cell = source.get_cell(row_index, field.index)

            if cell is None:
                data_row.append(None)
            elif source.stats.header_in_row(row_index):
                row_error = True
                break
            else:
                data_row.append(cell)
        if not row_error:
            subtable.add_row(row_index, data_row)
    return subtable


def get_data_by_horizontal_chains(chains: dict[int, list[Chain]], source: Source) -> list[Table]:
    subtables: list[Table] = []
    for chain_row, chains_in_row in chains.items():
        for chain in chains_in_row:
            subtable = get_data_by_horizontal_chain(chain_row, chain, source)
            subtables.append(subtable)

    return subtables


def clean_dirty_rows_in_table(subtable: Table) -> Table:
    new_table = Table(subtable.header_chain)
    for i, row in enumerate(subtable.data_rows.values()):
        if all(obj is None for obj in row):
            continue

        new_row: list[ResCell | None] = []
        error_row = False
        for elem, field in zip(row, subtable.header_chain.fields):
            if elem is not None and elem.role not in field.data_roles:
                error_row = True
                break
            new_row.append(elem)

        if not error_row:
            new_table.add_row(i, new_row)

    return new_table


def clean_dirty_tables(subtables: list[Table]) -> list[Table]:
    result: list[Table] = []
    for subtable in subtables:
        clean_table = clean_dirty_rows_in_table(subtable)
        result.append(clean_table)
    return result


def clean_empty_tables(subtables: list[Table]) -> list[Table]:
    result: list[Table] = []
    for subtable in subtables:
        if not subtable.empty:
            result.append(subtable)
    return result
