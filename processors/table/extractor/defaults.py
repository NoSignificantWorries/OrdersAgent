from table.annotate import CellKind, CellRole
from table.extractor.specs import (
    Direction,
    FieldSpec,
    FieldsRegistry,
    HeaderSpec,
    HeadersRegistry,
    HeaderType,
)


def build_default_fields_registry() -> FieldsRegistry:
    return FieldsRegistry([
        FieldSpec(CellKind.MATERIAL, {CellRole.LABEL}, Direction.VERTICAL, True, False),
        FieldSpec(CellKind.SIZE, {CellRole.SIZES, CellRole.NUMERIC}, Direction.VERTICAL, False, False),
        FieldSpec(CellKind.AMOUNT, {CellRole.NUMERIC}, Direction.VERTICAL, False, False),
        FieldSpec(CellKind.BARCODE, {CellRole.LABEL, CellRole.NUMERIC}, Direction.VERTICAL, True, True),
        FieldSpec(CellKind.MARKING, {CellRole.LABEL, CellRole.NUMERIC}, Direction.VERTICAL, True, True),
    ])

def build_default_headers_registry() -> HeadersRegistry:
    return HeadersRegistry([
        HeaderSpec(HeaderType.ONE_SIZE_COLUMN, Direction.VERTICAL, {
            CellKind.MATERIAL: (1, 1),
            CellKind.SIZE: (1, 1),
            CellKind.AMOUNT: (1, 1),
            CellKind.BARCODE: (0, 1),
            CellKind.MARKING: (0, 1)
        }, priority=200),
        HeaderSpec(HeaderType.STANDART, Direction.VERTICAL, {
            CellKind.MATERIAL: (1, 1),
            CellKind.SIZE: (2, 2),
            CellKind.AMOUNT: (1, 1),
            CellKind.BARCODE: (0, 1),
            CellKind.MARKING: (0, 1)
        }, priority=100),
        HeaderSpec(HeaderType.OKNA_DATA, Direction.VERTICAL, {
            CellKind.SIZE: (2, 2),
            CellKind.AMOUNT: (1, 1),
            CellKind.BARCODE: (0, 1),
            CellKind.MARKING: (0, 1)
        }, priority=50),
    ])
