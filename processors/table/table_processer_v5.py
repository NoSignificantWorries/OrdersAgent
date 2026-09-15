from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

import openpyxl
import xlrd

from . import config as conf
from . import functional as func


@dataclass
class ProductPosition:
    material: str
    x: int
    y: int
    amount: int
    barcode: str | None = None
    marking: str | None = None


@dataclass
class ParseResults:
    unique_materials: dict[str, list[int]]
    data: list[ProductPosition]
    count: int


@dataclass
class CellValue:
    value: str | int | tuple[int, int]
    type: conf.CellType = conf.CellType.TEXT
    merged: bool = False
    parent: tuple[int, int] | None = None


def cell_value_classify(value: str) -> tuple[conf.CellType, list[str] | None]:
    if conf.TYPES_CONFIG.regex is not None:
        for cell_type, patterns in conf.TYPES_CONFIG.regex.items():
            for pattern, groups in patterns:
                matched, values = func.get_match_and_groups(pattern, value, groups)
                if matched:
                    return cell_type, values
    if conf.TYPES_CONFIG.fuzzy is not None:
        for cell_type, patterns in conf.TYPES_CONFIG.fuzzy.items():
            for pattern in patterns:
                if func.fuzzy_match(value.lower(), pattern, 70):
                    return cell_type, None
    return conf.CellType.TEXT, None


class TableLoader:
    class TableType(str, Enum):
        XLS = ".xls"
        XLSX = ".xlsx"

    @staticmethod
    def _detect_type(file_data: BytesIO | Path) -> TableType:
        if isinstance(file_data, BytesIO):
            file_data.seek(0)
            header = file_data.read(8)
            file_data.seek(0)
            if header.startswith(b"PK\x03\x04"):
                return TableLoader.TableType.
            if header.startswith(b"\xd0\xcf\x11\xe0"):
                return ".xls"
            raise ValueError("Unknown binary format: not .xls or .xlsx")
        elif isinstance(file_data, Path):
            filetype = filepath.suffix.lower()
            if filetype == ".xls":
                wb = xlrd.open_workbook(str(filepath), formatting_info=True)
            elif filetype == ".xlsx":
                wb = openpyxl.load_workbook(filepath, data_only=True)
            else:
                raise ValueError(f"Unsupported file type '*{filetype}'! Only *.xls and *.xlsx supported.")
        else:
            raise TypeError(f"Unsupported data type '{type(file_data).__name__}'! Use Path or BytesIO objects instead.")

    @staticmethod
    def load_bdata(bdata: BytesIO):
        bdata.seek(0)
        header = bdata.read(8)
        bdata.seek(0)

        if header.startswith(b"PK\x03\x04"):
            bdata.seek(0)
            wb = xlrd.open_workbook(file_contents=bdata.read(), formatting_info=True)
        else:
            bdata.seek(0)
            wb = openpyxl.load_workbook(bdata, data_only=False)

    @staticmethod
    def load_excel(filepath: Path):
        filetype = filepath.suffix.lower()
        if filetype == ".xls":
            wb = xlrd.open_workbook(str(filepath), formatting_info=True)
        elif filetype == ".xlsx":
            wb = openpyxl.load_workbook(filepath, data_only=False)
        else:
            raise ValueError(f"Unsupported file type '*{filetype}'! Only *.xls and *.xlsx supported.")

    @staticmethod
    def _get_merged_cells_from_xls_sheet(sheet) -> dict[tuple[int, int], tuple[int, int]]:
        merged_cells: dict[tuple[int, int], tuple[int, int]] = {}
        for merged_range in sheet.merged_cells:
            parent = (merged_range[0], merged_range[2])
            for row_idx in range(merged_range[0], merged_range[1]):
                for col_idx in range(merged_range[2], merged_range[3]):
                    merged_cells[(row_idx, col_idx)] = parent
            del merged_cells[parent]
        return merged_cells

    @staticmethod
    def _load_xls_data(
        bdata: BytesIO | None = None, filepath: Path | None = None
    ) -> Document | None:
        try:
            if filepath:
                wb = xlrd.open_workbook(str(filepath), formatting_info=True)
            elif bdata:
                bdata.seek(0)
                wb = xlrd.open_workbook(
                    file_contents=bdata.read(), formatting_info=True
                )
            else:
                raise ValueError("Unsupported file type")
            with_metadata = True
        except Exception as first_step_error:
            try:
                if filepath:
                    wb = xlrd.open_workbook(str(filepath), formatting_info=False)
                elif bdata:
                    bdata.seek(0)
                    wb = xlrd.open_workbook(
                        file_contents=bdata.read(), formatting_info=False
                    )
                else:
                    raise ValueError("Unsupported file type")
                with_metadata = False
            except Exception as err:
                print(f"File opening errors: {first_step_error} {err}")
                return

        # document = Document()
        sheets = wb.sheet_names()
        for sheetname in sheets:
            sheet = wb[sheetname]
            # document.add_sheet(sheet.nrows, sheet.ncols, sheetname)

            merged_cells = {}
            if hasattr(sheet, "merged_cells"):
                merged_cells = TableLoader._get_merged_cells_from_xls_sheet(sheet)

            for row in range(sheet.nrows):
                for col in range(sheet.ncols):
                    value = sheet.cell_value(row, col)
                    cell_data = TableLoader._parse_cell(value)

                    merge_parent = merged_cells.get((row, col))
                    if merge_parent and cell_data is None and merge_parent != (row, col):
                        parent_cell = document.get_cell_from_sheet(sheetname, *merge_parent)
                        cell_data = parent_cell
                        if cell_data is not None:
                            cell_data.parent = merge_parent
                            cell_data.merged = True

                    document.add_cell_on_sheet(sheetname, row, col, cell_data)
        document.clean_sheets()
        return document


    @staticmethod
    def _get_merged_cells_from_xlsx_sheet(sheet) -> dict[tuple[int, int], tuple[int, int]]:
        merged_cells: dict[tuple[int, int], tuple[int, int]] = {}
        for merged_range in sheet.merged_cells.ranges:
            parent = (merged_range.min_row - 1, merged_range.min_col - 1)
            for row_idx in range(merged_range.min_row - 1, merged_range.max_row):
                for col_idx in range(merged_range.min_col - 1, merged_range.max_col):
                    merged_cells[(row_idx, col_idx)] = parent
            del merged_cells[parent]
        return merged_cells

    @staticmethod
    def _load_xlsx_data(
        bdata: BytesIO | None = None, filepath: Path | None = None
    ) -> Document | None:
        try:
            if filepath:
                wb = openpyxl.load_workbook(filepath, data_only=False)
            elif bdata:
                bdata.seek(0)
                wb = openpyxl.load_workbook(bdata, data_only=False)
            else:
                raise ValueError("No data proveded")
            with_metadata = True
        except Exception as first_step_error:
            try:
                if filepath:
                    wb = openpyxl.load_workbook(filepath, data_only=True)
                elif bdata:
                    bdata.seek(0)
                    wb = openpyxl.load_workbook(bdata, data_only=True)
                else:
                    raise ValueError("No data proveded")
                with_metadata = False
            except Exception as err:
                print(f"File opening errors: {first_step_error} {err}")
                return

        document = Document()
        sheets = wb.sheetnames
        for sheetname in sheets:
            sheet = wb[sheetname]
            document.add_sheet(sheet.max_row - 1, sheet.max_column - 1, sheetname)

            merged_cells = {}
            if with_metadata:
                merged_cells = TableLoader._get_merged_cells_from_xlsx_sheet(sheet)

            for row in sheet.iter_rows():
                for cell in row:
                    value = cell.value
                    cell_data = TableLoader._parse_cell(value)

                    merge_parent = merged_cells.get((cell.row - 1, cell.column - 1))
                    if merge_parent and cell_data is None and merge_parent != (cell.row - 1, cell.column - 1):
                        parent_cell = document.get_cell_from_sheet(sheetname, *merge_parent)
                        cell_data = parent_cell
                        if cell_data is not None:
                            cell_data.parent = merge_parent
                            cell_data.merged = True
                    document.add_cell_on_sheet(sheetname, cell.row - 1, cell.col - 1, cell_data)
        document.clean_sheets()
        return document
