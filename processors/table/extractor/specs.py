from collections import Counter
from dataclasses import dataclass
from enum import Enum

from table.annotate import CellKind, CellRole


class Direction(Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


@dataclass(frozen=True)
class FieldSpec:
    kind: CellKind
    roles: set[CellRole]
    direction: Direction
    none_allowed: bool
    multirole_allowed: bool


@dataclass(slots=True)
class Field:
    index: int
    sources: list[int]
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
    OKNA_TOP = "okna-top"
    OKNA_DATA = "okna-data"


@dataclass(frozen=True)
class HeaderSpec:
    type: HeaderType
    direction: Direction
    scheme: dict[CellKind, tuple[int, int]]
    priority: int = 0

    def kind_in(self, kind: CellKind) -> bool:
        return kind in self.scheme

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
        if not counts.keys() <= self.scheme.keys():
            return False
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

    def find_kind_indexes(self, kind: CellKind) -> list[int]:
        return [i for i, field in enumerate(self.fields) if field.spec.kind == kind]
