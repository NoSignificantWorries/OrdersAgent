from .annotate import (
    AnnotateEngine,
    Annotation,
    CellKind,
    HeaderMatcher,
    HeaderSpec,
    TableShape,
    build_default_actions,
)
from .loader import SparseTable, Workbook
from .report import WorkbookReport


def build_default_headers() -> HeaderMatcher:
    return HeaderMatcher([
        HeaderSpec(CellKind.MATERIALS, ["наименование", "обозначение", "номенклатура", "артикул", "тип пакета", "формула", "формула заполнения", "формула сп"]),
        HeaderSpec(CellKind.AMOUNT, ["кол-во", "количество", "кол-во(шт)", "количество(шт)", "колич", "n", "количес"]),
        HeaderSpec(CellKind.SIZE, ["размер", "размеры", "размер мм", "размеры мм", "длина", "длина мм", "ширина мм", "ширина", "высота", "высота мм", "стекла", "габариты", "габариты мм"]),
        HeaderSpec(CellKind.BARCODE, ["штрихкод", "шк", "штрих"]),
        HeaderSpec(CellKind.MARKING, ["маркировка", "маркир"]),
        HeaderSpec(CellKind.NAME, ["имя:"]),
        HeaderSpec(CellKind.AUFBAU, ["aufbau:"]),
        HeaderSpec(CellKind.THIKNESS, ["толщина:"])
    ])


engine = AnnotateEngine(build_default_actions(build_default_headers()))


def annotate_table(table: SparseTable) -> Annotation:
    return engine.process(table)


def make_shape(annotation: Annotation) -> TableShape:
    return engine.shape(annotation)


# def read(wb: Workbook) -> tuple[WorkbookReport, list[SparseTable]]:
#     report = WorkbookReport(wb.name)
#     tables: list[SparseTable] = []
#     for sheet in wb.sheets:
#         subtable = SparseTable(nrows=sheet.nrows, ncols=sheet.ncols)
#         report.add_sheet(name=sheet.name, nrows=sheet.nrows, ncols=sheet.ncols)
#         for cell in sheet.table:
#             new_cell = subtable.add_cell(cell.value, cell.row, cell.col)
#             report.add_cell_on_last_sheet(cell.row, cell.col, None if new_cell is None else new_cell.value)
#         keeped_rows, keeped_cols = subtable.normalize()
#         report.last_table_normalized(subtable.nrows, subtable.ncols, keeped_rows, keeped_cols)
#         if not subtable.empty:
#             tables.append(subtable)
#         else:
#             print(f"WARN: Empty sheet '{sheet.name}' in the workbook '{wb.name}'")
#     return report, tables
