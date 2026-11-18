
from dataclasses import dataclass, field

from . import extractor, loader
from .annotate import AnnotationPipeline, CellKind, CellRole, TextMatcher, TextSpec


@dataclass
class ParsedFile:
    name: str | None
    data: dict[str, extractor.validator.DataChunk] = field(default_factory=dict)


class ParserPipeline:
    @classmethod
    def build_default_headers(cls) -> TextMatcher:
        return TextMatcher([
            TextSpec(CellKind.MATERIAL, CellRole.HEADER, ["наименование", "обозначение", "номенклатура", "артикул", "тип пакета", "формула", "формула заполнения", "формула сп"]),
            TextSpec(CellKind.AMOUNT, CellRole.HEADER, ["кол-во", "количество", "кол-во(шт)", "количество(шт)", "колич", "n", "количес", "шт"]),
            TextSpec(CellKind.SIZE, CellRole.HEADER, ["размер", "размеры", "размер мм", "размеры мм", "длина", "длина мм", "ширина мм", "ширина", "высота", "высота мм", "стекла", "габариты", "габариты мм", "мм"]),
            TextSpec(CellKind.BARCODE, CellRole.HEADER, ["штрихкод", "шк", "штрих"]),
            TextSpec(CellKind.MARKING, CellRole.HEADER, ["маркировка", "маркир"]),
            TextSpec(CellKind.NAME, CellRole.FIELD, ["имя:"]),
            TextSpec(CellKind.AUFBAU, CellRole.FIELD, ["aufbau:"]),
            TextSpec(CellKind.THICKNESS, CellRole.FIELD, ["толщина:"]),
            TextSpec(CellKind.ITOGO, CellRole.UNKNOWN, ["итого", "итого:"])
        ])

    @classmethod
    def read_workbook(cls, wb: loader.Workbook) -> list[loader.SparseTable]:
        # report = WorkbookReport(wb.name)
        tables: list[loader.SparseTable] = []
        for subtable in wb.sheets:
            # report.add_sheet(name=subtable.name, nrows=subtable.nrows, ncols=subtable.ncols)
            # report.add_cell_on_last_sheet(cell.row, cell.col, None if new_cell is None else new_cell.value)
            keeped_rows, keeped_cols = subtable.normalize()
            # report.last_table_normalized(subtable.nrows, subtable.ncols, keeped_rows, keeped_cols)
            if not subtable.empty:
                tables.append(subtable)
            else:
                print(f"WARN: Empty sheet '{subtable.name}' in the workbook '{wb.name}'")
        return tables

    @classmethod
    def run(cls, wb: loader.Workbook) -> ParsedFile:
        text_matcher = cls.build_default_headers()

        result = ParsedFile(wb.name)

        tables = cls.read_workbook(wb)
        annotated_tables_generator = (AnnotationPipeline(text_matcher, t).run() for t in tables)

        for annotated_table in annotated_tables_generator:
            extracted_blocks = extractor.pipeline.ExtractorPipeline(annotated_table).run()
            table_data_chunk = extractor.validator.ValidatorPipeline.run(extracted_blocks)
            if not table_data_chunk:
                print("Empty data on sheet!!!")
                continue
            result.data[annotated_table.name] = table_data_chunk

        return result
