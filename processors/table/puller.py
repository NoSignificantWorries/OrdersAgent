from dataclasses import dataclass, field
from enum import Enum

from table.annotate import Annotation, CellAnnotation, CellKind, CellRole
from table.loader import SparseTable


@dataclass(frozen=True, slots=True)
class ResCell:
    value: int | str | tuple[int, int]
    row: int
    col: int
    kind: CellKind
    role: CellRole


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
    start: int
    end: int
    direction: Direct
    fields: list[Field] = field(default_factory=list)

    def push_field(self, field: Field) -> None:
        if field.index < self.end:
            raise ValueError("Wrong index of Field in th echain")
        self.end = max(self.end, field.index)
        self.fields.append(field)


def data_role_for_kind(kind: CellKind) -> set[CellRole] | None:
    lib: dict[CellKind, set[CellRole]] = {
        CellKind.MATERIAL: {CellRole.LABEL},
        CellKind.AMOUNT: {CellRole.NUMERIC},
        CellKind.SIZE: {CellRole.NUMERIC, CellRole.SIZES},
    }
    return lib.get(kind)


def kind_to_direction(kind: CellKind) -> Direct: ...


def build_horizontal_chains(table: SparseTable, annotation: Annotation) -> dict[int, list[Chain]]:
    # sort annotations per row and filter not HEADERs
    ann_per_row: dict[int, dict[int, CellAnnotation]] = {}
    for pos, cell in annotation.cells.items():
        if cell.role != CellRole.HEADER:
            continue
        ann_per_row[pos[0]] = ann_per_row.get(pos[0], {})
        ann_per_row[pos[0]][pos[1]] = cell

    # build chains per row
    chains: dict[int, list[Chain]] = {}
    for ir in range(table.nrows):
        cells_in_row = ann_per_row.get(ir)
        if cells_in_row is None:
            continue

        # build chain
        row_chain = None
        for idx, ann in ann_per_row.get(ir, {}).items():
            if row_chain is None:
                row_chain = Chain(idx, idx + 1, Direct.HORIZONTAL)
            row_chain.push_field(Field(
                index=idx,
                kind=ann.kind,
                data_roles=data_role_for_kind(ann.kind),
                sources=[(ir, idx)]
            ))
        if row_chain is not None:
            chains[ir] = [row_chain]
    return chains


def get_data_from_horizontal_chains(table: SparseTable, chains: dict[int, list[Chain]]) -> None:
    for i, (ir, chains_lst) in enumerate(chains.items()):
        chain = chains_lst[0]
        parse_mask: dict[int, set[CellRole]] = {}
        for field in chain.fields:
            parse_mask[field.index] = field.data_roles
