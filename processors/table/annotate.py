import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rapidfuzz import fuzz

from .sparse_table import Cell, SparseTable


class CellKind(str, Enum):
    MATERIALS = "materials"
    AMOUNT = "amount"
    SIZE = "size"
    BARCODE = "barcode"
    MARKING = "marking"
    NAME = "name"
    AUFBAU = "aufbau"
    THIKNESS = "thikness"
    UNKNOWN = "unknown"


class CellRole(str, Enum):
    HEADER = "header"
    LABEL = "label"
    NUMERIC = "numeric"
    SIZES = "sizes"


@dataclass(frozen=True, slots=True)
class HeaderSpec:
    kind: CellKind
    anchors: list[str]


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    trigger: Callable[[Any], bool]
    annotate: Callable[[Any], tuple[CellRole, CellKind]]
    transform: Callable[[Any], Any | None] | None = None
    priority: int = 0


class HeaderMatcher:
    _WS = re.compile(r"\s+", re.UNICODE)
    _STRIP = re.compile(r"[\(\)\[\]\{\}\.,]")

    @staticmethod
    def normalize(text: str) -> str:
        s = str(text).lower()
        s = HeaderMatcher._WS.sub("", s)
        s = HeaderMatcher._STRIP.sub("", s)
        return s

    def __init__(self, patterns: list[HeaderSpec]) -> None:
        self.fields: list[HeaderSpec] = patterns
        self.name_to_field: dict[str, HeaderSpec] = {field.kind: field for field in self.fields}
        self.anchors_to_field: dict[str, HeaderSpec] = {}
        self.max_length = 0

        self.normalize_all_anchors()

    def normalize_all_anchors(self) -> None:
        for field in self.fields:
            for anchor in field.anchors:
                norm_anchor = HeaderMatcher.normalize(anchor)
                self.anchors_to_field[norm_anchor] = field
                self.max_length = max(self.max_length, len(norm_anchor))

    def classify_text(self, text: str, threshold: float = 90.0) -> HeaderSpec | None:
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

    def field_by_name(self, name: str) -> HeaderSpec | None:
        return self.name_to_field.get(name, None)

    def match(self, value: int | str) -> HeaderSpec | None:
        if isinstance(value, int):
            return None
        return self.classify_text(value)


def build_default_actions(matcher: HeaderMatcher) -> list[Action]:
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
        Action("header", lambda val: isinstance(val, str) and matcher.classify_text(val) is not None,
            lambda val: (CellRole.HEADER, matcher.classify_text(val).kind),
            priority=50),
        Action("str", lambda val: isinstance(val, str),
            lambda _: (CellRole.LABEL, CellKind.UNKNOWN), priority=30)
    ]


@dataclass(frozen=True, slots=True)
class CellAnnotation:
    role: CellRole
    kind: CellKind = CellKind.UNKNOWN
    value: Any | None = None


@dataclass
class Annotation:
    cells: dict[tuple[int, int], CellAnnotation] = field(default_factory=dict)


class AnnotateEngine:
    def __init__(self, actions: list[Action]) -> None:
        self.actions = sorted(actions, key=lambda act: act.priority, reverse=True)

    def process(self, table: SparseTable) -> Annotation:
        annotation = Annotation()
        for row, col, cell in table.iter_cells():
            for action in self.actions:
                if action.trigger(cell.value):
                    cell_role, cell_kind = action.annotate(cell.value)
                    if action.transform:
                        new_value = action.transform(cell.value)
                        annotation.cells[(row, col)] = CellAnnotation(cell_role, cell_kind, new_value)
                    else:
                        annotation.cells[(row, col)] = CellAnnotation(cell_role, cell_kind)
                    break
        return annotation
