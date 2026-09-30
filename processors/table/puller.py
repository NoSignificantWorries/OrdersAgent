from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Protocol, Self

from table.annotate import Annotation, CellAnnotation, CellKind, CellRole
from table.loader import Cell, SparseTable


@dataclass(frozen=True, slots=True)
class ResCell:
    value: int | str | tuple[int, int]
    row: int
    col: int
    kind: CellKind
    role: CellRole


@dataclass(frozen=True, slots=True)
class AnnCell:
    cell: Cell
    ann: CellAnnotation | None

    @property
    def annotated(self) -> bool:
        return self.ann is not None

    def build(self) -> ResCell | None:
        if not self.annotated or self.cell.value is None:
            return None

        if self.ann.value is not None:
            val = self.ann.value
        else:
            val = self.cell.value
        return ResCell(
            value=val,
            row=self.cell.row,
            col=self.cell.col,
            kind=self.ann.kind,
            role=self.ann.role)


@dataclass
class Cursor:
    position: tuple[int, int]
    table: SparseTable
    annotation: Annotation

    @property
    def row(self) -> int:
        return self.position[0]

    @property
    def col(self) -> int:
        return self.position[1]

    @property
    def at_end(self) -> bool:
        return self.position == self.table.size

    def _in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.table.nrows and 0 <= c < self.table.ncols

    def move(self, dr: int, dc: int) -> bool:
        r, c = self.row + dr, self.col + dc
        if not self._in_bounds(r, c):
            return False
        self.position = (r, c)
        return True

    def right(self) -> bool:  return self.move(0, +1)
    def left(self)  -> bool:  return self.move(0, -1)
    def down(self)  -> bool:  return self.move(+1, 0)
    def up(self)    -> bool:  return self.move(-1, 0)

    def next(self) -> bool:
        if self.at_end:
            return False
        r, c = self.position
        if c + 1 < self.table.ncols:
            self.position = (r, c + 1)
            return True
        if r + 1 < self.table.nrows:
            self.position = (r + 1, 0)
            return True
        self.position = self.table.size
        return False

    def seek(self, r: int, c: int) -> bool:
        if not self._in_bounds(r, c):
            return False
        self.position = (r, c)
        return True

    def get_cell(self) -> AnnCell:
        return AnnCell(self.table.get_cell(*self.position), self.annotation.get_cell(*self.position))


@dataclass(frozen=True)
class Anchor:
    pos: tuple[int, int]
    kind: CellKind


@dataclass
class Star:
    anchor: Anchor
    data: ResCell | list[ResCell] | list[list[ResCell]]
    multistar: bool = False
    one_value: bool = False


class StarParser(Protocol):
    kind: CellKind
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None: ...


class CommonParsers:
    @staticmethod
    def get_data_below(cur: Cursor, roles: set[CellRole]) -> list[ResCell]:
        results: list[ResCell] = []
        while cur.down():
            cell = cur.get_cell()
            if not cell.annotated or cell.cell.empty:
                continue
            if cell.ann.role in roles:
                results.append(cell.build())
            else:
                break
        return results

    @staticmethod
    def get_data_right(cur: Cursor, roles: set[CellRole]) -> ResCell | None:
        while cur.right():
            cell = cur.get_cell()
            if not cell.annotated or cell.cell.empty:
                continue
            if cell.ann.role in roles:
                return cell.build()
            else:
                return None
        return None


class AufbauParser(StarParser):
    kind = CellKind.AUFBAU
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        cursor = Cursor(anchor.pos, table, annotation)
        value = CommonParsers.get_data_right(cursor, {CellRole.LABEL})
        if value is None:
            return None
        return Star(anchor, value, one_value=True)


class NameParser(StarParser):
    kind = CellKind.NAME
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        cursor = Cursor(anchor.pos, table, annotation)
        value = CommonParsers.get_data_right(cursor, {CellRole.LABEL})
        if value is None:
            return None
        return Star(anchor, value, one_value=True)


class ThicknessParser(StarParser):
    kind = CellKind.THICKNESS
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        cursor = Cursor(anchor.pos, table, annotation)
        value = CommonParsers.get_data_right(cursor, {CellRole.LABEL})
        if value is None:
            return None
        return Star(anchor, value, one_value=True)


class MaterialParser(StarParser):
    kind = CellKind.MATERIAL
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        cursor = Cursor(anchor.pos, table, annotation)
        values = CommonParsers.get_data_below(cursor, {CellRole.LABEL})
        return Star(anchor, values)


class SizeOneColumnParser(StarParser):
    kind = CellKind.SIZE
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        ...


class AmountParser(StarParser):
    kind = CellKind.AMOUNT
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        cursor = Cursor(anchor.pos, table, annotation)
        values = CommonParsers.get_data_below(cursor, {CellRole.NUMERIC})
        return Star(anchor, values)


class MarkingParser(StarParser):
    kind = CellKind.MARKING
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        cursor = Cursor(anchor.pos, table, annotation)
        values = CommonParsers.get_data_below(cursor, {CellRole.LABEL, CellRole.NUMERIC})
        return Star(anchor, values)


class BarcodeParser(StarParser):
    kind = CellKind.BARCODE
    def parse(self, anchor: Anchor, table: SparseTable, annotation: Annotation) -> Star | None:
        cursor = Cursor(anchor.pos, table, annotation)
        values = CommonParsers.get_data_below(cursor, {CellRole.LABEL, CellRole.NUMERIC})
        return Star(anchor, values)


def find_anchors(annotation: Annotation) -> list[Anchor]:
    finded_anchors: list[Anchor] = []
    for pos, cell in annotation.cells.items():
        if cell.role == CellRole.HEADER:
            finded_anchors.append(Anchor(pos, cell.kind))
    return finded_anchors


def parse(anchors: list[Anchor], table: SparseTable, annotation: Annotation) -> None:
    star_parser_by_type: dict[CellKind, list[StarParser]] = {
        CellKind.AUFBAU: [AufbauParser()],
        CellKind.NAME: [NameParser()],
        CellKind.THICKNESS: [ThicknessParser()],
        CellKind.MATERIAL: [MaterialParser()],
        CellKind.AMOUNT: [AmountParser()],
        CellKind.MARKING: [AmountParser()],
        CellKind.BARCODE: [AmountParser()]
    }

    for anchor in anchors:
        parsers = star_parser_by_type.get(anchor.kind, [])
        for parser in parsers:
            star = parser.parse(anchor, table, annotation)
            print(star)
