import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rapidfuzz import fuzz

from .loader import SparseTable


class CellKind(str, Enum):
    EMPTY = "empty"
    MATERIAL = "materials"
    AMOUNT = "amount"
    SIZE = "size"
    BARCODE = "barcode"
    MARKING = "marking"
    NAME = "name"
    AUFBAU = "aufbau"
    THICKNESS = "thikness"
    UNKNOWN = "unknown"
    ITOGO = "itogo"


class CellRole(str, Enum):
    HEADER = "header"
    LABEL = "label"
    NUMERIC = "numeric"
    SIZES = "sizes"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TextSpec:
    kind: CellKind
    role: CellRole
    anchors: list[str]


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    trigger: Callable[[Any], bool]
    annotate: Callable[[Any], tuple[CellRole, CellKind]]
    transform: Callable[[Any], Any | None] | None = None
    priority: int = 0


class TextMatcher:
    _WS = re.compile(r"\s+", re.UNICODE)
    _STRIP = re.compile(r"[\(\)\[\]\{\}\.,]")

    @staticmethod
    def normalize(text: str) -> str:
        s = str(text).lower()
        s = TextMatcher._WS.sub("", s)
        s = TextMatcher._STRIP.sub("", s)
        return s

    def __init__(self, patterns: list[TextSpec]) -> None:
        self.fields: list[TextSpec] = patterns
        self.name_to_field: dict[CellKind, TextSpec] = {field.kind: field for field in self.fields}
        self.anchors_to_field: dict[str, TextSpec] = {}
        self.max_length = 0

        self.normalize_all_anchors()

    def normalize_all_anchors(self) -> None:
        for field in self.fields:
            for anchor in field.anchors:
                norm_anchor = TextMatcher.normalize(anchor)
                self.anchors_to_field[norm_anchor] = field
                self.max_length = max(self.max_length, len(norm_anchor))

    def classify_text(self, text: str, threshold: float = 90.0) -> TextSpec | None:
        norm = self.normalize(text)
        exact = self.anchors_to_field.get(norm)
        if exact is not None:
            return exact

        if len(norm) < 5:
            return None

        best_ratio = 0.0
        best_field = None
        for anchor, field in self.anchors_to_field.items():
            if abs(len(norm) - len(anchor)) > 5:
                continue
            ratio = fuzz.ratio(norm, anchor)
            if ratio > best_ratio:
                best_ratio = ratio
                best_field = field
                if ratio == 100.0:
                    break
        if best_ratio >= threshold:
            return best_field
        return None

    def field_by_kind(self, name: CellKind) -> TextSpec | None:
        return self.name_to_field.get(name, None)

    def match(self, value: int | str) -> TextSpec | None:
        if isinstance(value, int):
            return None
        return self.classify_text(value)


def build_default_actions(matcher: TextMatcher) -> list[Action]:
    pattern = re.compile(r"^\s*([\d\s]+(?:[.,]\d+)?)\s*[xXхХ*×]\s*([\d\s]+(?:[.,]\d+)?)\s*$")

    def is_sizes(value: Any) -> bool:
        return bool(isinstance(value, str) and pattern.fullmatch(value))

    def transform_sizes(value: Any) -> tuple[int, int] | None:
        match = pattern.match(value)
        if not match:
            return None
        try:
            w = int(float(match.group(1).replace(" ", "").replace(",", ".")))
            h = int(float(match.group(2).replace(" ", "").replace(",", ".")))
            return w, h
        except ValueError:
            return None

    return [
        Action("int", lambda val: isinstance(val, int),
            lambda _: (CellRole.NUMERIC, CellKind.UNKNOWN), priority=200),
        Action("sizes", is_sizes,
            lambda _: (CellRole.SIZES, CellKind.UNKNOWN),
            transform_sizes, priority=100),
        Action("text", lambda val: isinstance(val, str) and matcher.classify_text(val) is not None,
            lambda val: (lambda cls: (cls.role, cls.kind))(matcher.classify_text(val)),
            priority=50),
        Action("str", lambda val: isinstance(val, str),
            lambda _: (CellRole.LABEL, CellKind.UNKNOWN), priority=30)
    ]


@dataclass(frozen=True, slots=True)
class ResCell:
    value: int | str | tuple[int, int] | None
    row: int
    col: int
    kind: CellKind = CellKind.EMPTY
    role: CellRole = CellRole.UNKNOWN


@dataclass(frozen=True)
class Stats:
    roles_in_row: dict[int, frozenset[CellRole]]
    roles_in_col: dict[int, frozenset[CellRole]]
    kinds_in_row: dict[int, frozenset[CellRole]]
    kinds_in_col: dict[int, frozenset[CellRole]]


@dataclass(frozen=True)
class AnnotatedTable:
    name: str
    nrows: int
    ncols: int
    table: list[list[ResCell]]
    stats: Stats


class AnnotationPipeline:
    @classmethod
    def make_annotations(cls, actions: list[Action], table: SparseTable) -> list[list[ResCell]]:
        res_table = [[ResCell(None, irow, icol) for icol in range(table.ncols)] for irow in range(table.nrows)]
        for row, col, cell in table.iter_cells():
            for action in actions:

                if not action.trigger(cell.value):
                    continue

                cell_role, cell_kind = action.annotate(cell.value)
                new_value = action.transform(cell.value) if action.transform else None

                res_table[row][col] = ResCell(
                    cell.value if new_value is None else new_value,
                    row,
                    col,
                    cell_kind,
                    cell_role
                )

                break

        return res_table

    @classmethod
    def make_stats(cls, table: list[list[ResCell]]) -> Stats:
        per_row_roles = {}
        per_col_roles = {}
        per_row_kinds = {}
        per_col_kinds = {}
        for irow, row in enumerate(table):
            for icol, cell in enumerate(row):

                per_col_roles[icol] = per_col_roles.get(icol, set())
                per_col_kinds[icol] = per_col_kinds.get(icol, set())
                per_row_roles[irow] = per_row_roles.get(irow, set())
                per_row_kinds[irow] = per_row_kinds.get(irow, set())

                per_col_roles[icol].add(cell.role)
                per_col_kinds[icol].add(cell.kind)
                per_row_roles[irow].add(cell.role)
                per_row_kinds[irow].add(cell.kind)

        return Stats(
            per_row_roles,
            per_col_roles,
            per_row_kinds,
            per_col_kinds
        )

    @classmethod
    def run(cls, actions: list[Action], table: SparseTable) -> AnnotatedTable:
        sorted_actions = sorted(actions, key=lambda act: act.priority, reverse=True)
        annotated_cells = cls.make_annotations(sorted_actions, table)
        stats = cls.make_stats(annotated_cells)

        return AnnotatedTable(
            table.name,
            table.nrows,
            table.ncols,
            annotated_cells,
            stats
        )
