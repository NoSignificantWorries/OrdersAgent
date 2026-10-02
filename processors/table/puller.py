from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

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

    def iter_through_row(self, row: int) -> Generator[ResCell | None, None, None]:
        for ic in range(self.table.ncols):
            yield self.get_cell(row, ic)

    def header_in_row(self, row: int) -> bool:
        return self.stats.header_in_row(row)



class Direct(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass
class Field:
    index: int
    kind: CellKind
    data_roles: set[CellRole]
    sources: list[tuple[int, int]]


@dataclass
class Chain:
    direction: Direct
    fields: list[Field] = field(default_factory=list)
    kind_counts: dict[CellKind, int] = field(default_factory=dict)

    # TODO: Recreate to the automatic ruleset matcher and validator
    _BASIC_RULESET: ClassVar[dict[CellKind, int]] = {
        CellKind.AMOUNT: 1,
        CellKind.MATERIAL: 1,
        CellKind.SIZE: 2
    }

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

    def push_field(self, field: Field) -> bool:
        if field.kind in Chain._BASIC_RULESET:
            kind_count = self.kind_counts.get(field.kind, 0)
            if kind_count >= Chain._BASIC_RULESET[field.kind]:
                return False

        self.fields.append(field)
        self.kind_counts[field.kind] = self.kind_counts.get(field.kind, 0) + 1
        return True

    def last(self) -> Field | None:
        if self.size > 0:
            return self.fields[-1]
        return None


@dataclass
class Table:
    header_chain: Chain
    data_rows: dict[int, list[ResCell | None]] = field(default_factory=dict)

    @property
    def nrows(self) -> int:
        return len(self.data_rows)

    def add_row(self, idx: int, row: list[ResCell | None]) -> None:
        self.data_rows[idx] = row


def kind_to_direction(kind: CellKind) -> Direct: ...


def make_chains_in_row(row: int, source: Source) -> list[Chain]:
    roles_by_kind: dict[CellKind, set[CellRole]] = {
            CellKind.MATERIAL: {CellRole.LABEL},
            CellKind.AMOUNT: {CellRole.NUMERIC},
            CellKind.SIZE: {CellRole.NUMERIC, CellRole.SIZES},
        }

    chains = []
    last_chain = None
    for cell in source.iter_through_row(row):
        # TODO: Create ruleset (mainly for the SIZE)

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
        if not last_chain.push_field(new_field):
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


def merge_chains(chn1: Chain, chn2: Chain) -> Chain | None:
    if chn1.direction != chn2.direction:
        return None
    if chn1.end < chn2.start or chn2.end < chn1.start:
        return None
    new_chain = Chain(chn1.direction)

    ch1_pointer = 0
    ch2_pointer = 0

    field1 = chn1.fields[ch1_pointer]
    field2 = chn2.fields[ch2_pointer]

    # TODO: Complete chains merger


def merge_chains_in_table(chains: dict[int, list[Chain]]) -> dict[int, list[Chain]]: ...


def get_data_by_horizontal_chain(chain_row_index: int, chain: Chain, source: Source) -> Table:
    subtable: Table = Table(chain)
    row_error: bool = False
    for row_index in range(chain_row_index + 1, source.table.nrows):
        if row_error:
            break
        data_row: list[ResCell | None] = []
        for field in chain.fields:
            cell = source.get_cell(row_index, field.index)

            if cell is None:
                data_row.append(None)
            elif cell.role not in field.data_roles:
                row_error = True
                break
            else:
                data_row.append(cell)
        if not row_error:
            subtable.add_row(row_index, data_row)
    return subtable


def get_data_by_horizontal_chains(chains: dict[int, list[Chain]], source: Source) -> list[Table]:
    subtables: list[Table] = []
    for chain_row_index, row_chains in chains.items():
        for chain in row_chains:
            subtable = get_data_by_horizontal_chain(chain_row_index, chain, source)
            subtables.append(subtable)

    return subtables
