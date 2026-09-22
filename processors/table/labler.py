import re
from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class Trigger(Protocol):
    def match(self, value: Any) -> bool: ...


class Action(Protocol):
    def action(self, value: Any) -> Any: ...


class Direction(str, Enum):
    RIGHT = "one-value-right"
    DOWN = "many-values-down"


class FieldName(str, Enum):
    MATERIALS = "materials-header"
    TEXT = "simple-text"
    NUMBER = "number"
    SIZES = "two-sizes-in-one-column"


@dataclass(slots=True)
class FieldSpec:
    name: FieldName
    triggers: list[Trigger]
    action: Action
    content_types: list[FieldName]
    is_header: bool
    direction: Direction


class FieldCollection:
    def __init__(self) -> None:
        self.fields: dict[str, FieldSpec] = {}

    def add(self, name: str, spec: FieldSpec) -> None:
        self.fields[name] = spec


class TextMatcher:
    _WS = re.compile(r"\s+", re.UNICODE)
    _STRIP = re.compile(r"[\(\)\[\]\{\}\.,]")

    texts: list[str] = field(default_factory=list[str])

    @staticmethod
    def normalize(text: str) -> str:
        s = str(text).lower()
        s = TextMatcher._WS.sub("", s)
        s = TextMatcher._STRIP.sub("", s)
        return s

    def __init__(self, patterns: list[str]) -> None:
        self.texts += patterns

        self.fields: list[FieldSpec] = fields
        self.name_to_field: dict[str, FieldSpec] = {field.name: field for field in self.fields}
        self.anchors_to_field: dict[str, FieldSpec] = {}
        self.max_length = 0

        self.normalize_all_anchors()

    def normalize_all_anchors(self) -> None:
        for field in self.fields:
            for anchor in field.anchors:
                norm_anchor = FieldMatcher.normalize(anchor)
                self.anchors_to_field[norm_anchor] = field
                self.max_length = max(self.max_length, len(norm_anchor))

    def classify_text(self, text: str, threshold: float = 90.0) -> FieldSpec | None:
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

    def field_by_name(self, name: str) -> FieldSpec | None:
        return self.name_to_field.get(name, None)

    def match(self, value: int | str) -> FieldSpec | None:
        if isinstance(value, int):
            return None
        return self.classify_text(value)


def make_basics() -> FieldCollection:
    collection = FieldCollection()

    collection.add("materials", FieldSpec(FieldName.MATERIALS, [StrTrigger()], [], [FieldName.TEXT], True, Direction.DOWN))

    return collection
