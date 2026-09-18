from io import BytesIO
from pathlib import Path

from . import table_loader as tl
from . import table_parser as tp


def run_file(file: Path | BytesIO) -> None:
    workbook = tl.TableLoader.load(file)
    for sheet in workbook.sheets:
        table = tp.SparseTable(name=sheet.name, nrows=sheet.nrows, ncols=sheet.ncols)
        print(table._empty_rows)
        print(table._empty_columns)
        print(table.nrows, table.ncols)
        table.normilize_cells()
        print(table.nrows, table.ncols)
