from .annotate import (
    AnnotateEngine,
    Annotation,
    CellKind,
    HeaderMatcher,
    HeaderSpec,
    Stats,
    build_default_actions,
)
from .loader import SparseTable, Workbook
from .report import WorkbookReport


def build_default_headers() -> HeaderMatcher:
    return HeaderMatcher([
        HeaderSpec(CellKind.MATERIAL, ["наименование", "обозначение", "номенклатура", "артикул", "тип пакета", "формула", "формула заполнения", "формула сп"]),
        HeaderSpec(CellKind.AMOUNT, ["кол-во", "количество", "кол-во(шт)", "количество(шт)", "колич", "n", "количес", "шт"]),
        HeaderSpec(CellKind.SIZE, ["размер", "размеры", "размер мм", "размеры мм", "длина", "длина мм", "ширина мм", "ширина", "высота", "высота мм", "стекла", "габариты", "габариты мм", "мм"]),
        HeaderSpec(CellKind.BARCODE, ["штрихкод", "шк", "штрих"]),
        HeaderSpec(CellKind.MARKING, ["маркировка", "маркир"]),
        HeaderSpec(CellKind.NAME, ["имя:"]),
        HeaderSpec(CellKind.AUFBAU, ["aufbau:"]),
        HeaderSpec(CellKind.THICKNESS, ["толщина:"])
    ])


engine = AnnotateEngine(build_default_actions(build_default_headers()))


def annotate_table(table: SparseTable) -> Annotation:
    return engine.make_annotations(table)


def make_stats(annotations: Annotation) -> Stats:
    return engine.build_stats(annotations)


def read(wb: Workbook) -> tuple[WorkbookReport, list[SparseTable]]:
    report = WorkbookReport(wb.name)
    tables: list[SparseTable] = []
    for subtable in wb.sheets:
        report.add_sheet(name=subtable.name, nrows=subtable.nrows, ncols=subtable.ncols)
        # report.add_cell_on_last_sheet(cell.row, cell.col, None if new_cell is None else new_cell.value)
        keeped_rows, keeped_cols = subtable.normalize()
        report.last_table_normalized(subtable.nrows, subtable.ncols, keeped_rows, keeped_cols)
        if not subtable.empty:
            tables.append(subtable)
        else:
            print(f"WARN: Empty sheet '{subtable.name}' in the workbook '{wb.name}'")
    return report, tables
