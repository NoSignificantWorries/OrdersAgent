from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

import openpyxl
import xlrd

from . import config as conf
from . import functional as func
from .config import CellType


def cell_classify(value: str):
    if conf.TYPES_CONFIG.regex is not None:
        for cell_type, patterns in conf.TYPES_CONFIG.regex.items():
            for pattern, groups in patterns:
                if func.check_fullmatch(pattern, value):
                    return cell_type
    if conf.TYPES_CONFIG.fuzzy is not None:
        for cell_type, patterns in conf.TYPES_CONFIG.fuzzy.items():
            for pattern in patterns:
                if func.fuzzy_match(value.lower(), pattern, 90):
                    return cell_type
    return conf.CellType.TEXT


class SparseTable:
    def __init__(self) -> None:
        self.cells: Dict[Tuple[int, int], Dict[str, conf.CellType | str | int]] = {}
        self.rows = set()
        self.cols = set()

    @property
    def ncols(self):
        return max(self.cols) + 1 if self.cols else 0

    @property
    def nrows(self):
        return max(self.rows) + 1 if self.rows else 0

    def __repr__(self) -> str:
        cells_info = [f"({r} {c}) -> {cell}" for (r, c), cell in self.cells.items()]
        return f"SparseTable:\n{'\n'.join(cells_info)}"

    def __str__(self) -> str:
        return self.__repr__()

    def add(self, row, col, value):
        value = func.clean(str(value))
        cell_type = cell_classify(value)
        self.rows.add(row)
        self.cols.add(col)
        self.cells[(row, col)] = {
            "type": cell_type,
            "value": value,
            "row": row,
            "col": col,
        }

    def get(self, row, col):
        return self.cells.get((row, col), None)

    def get_text(self):
        rows = []
        for ri in range(self.nrows):
            row = ""
            for ci in range(self.ncols):
                cell = self.get(ri, ci)
                if cell:
                    row += conf.CellTypeLabel[cell["type"]]
                else:
                    row += "."
            rows.append(row)
        return rows


def find_pattern_in_one_row(row: str):
    basic_headers = [
        CellType.AMOUNT_H,
        CellType.BARCODE_H,
        CellType.HEIGHT_H,
        CellType.WIDTH_H,
        CellType.LENGTH_H,
        CellType.MARKING_H,
        CellType.MAT_H,
        CellType.SIZE_H,
    ]

    def get_labels(types_list):
        res = {}
        for tp in types_list:
            label = conf.CellTypeLabel[tp]
            res[label] = res.get(label, 0) + 1
        return res

    basic_labels = get_labels(basic_headers)
    counts = {}
    for label in basic_labels:
        counts[label] = row.count(label)

    required_patterns = {
        "simple1": {"A": 1, "R": 1, "S": 0, "W": 1, "H": 1, "L": 0},
        "simple2": {"A": 1, "R": 1, "S": 0, "W": 1, "H": 0, "L": 1},
        "simple3": {"A": 1, "R": 1, "S": 0, "W": 0, "H": 1, "L": 1},
        "sized": {"A": 1, "R": 1, "S": 2, "W": 0, "H": 0, "L": 0},
        "sized_uno_duo": {"A": 1, "R": 1, "S": 1, "W": 0, "H": 0, "L": 0},
    }

    correct_pattern = None
    for name, rp in required_patterns.items():
        all_correct = True
        for label, cnt in rp.items():
            if counts[label] != cnt:
                all_correct = False
                break
        if all_correct:
            correct_pattern = name
            break

    if correct_pattern is None:
        return None

    target_columns = []
    target_indexes = []
    for i, elem in enumerate(row):
        if elem in basic_labels:
            target_columns.append(elem)
            target_indexes.append(i)
            if correct_pattern == "sized_uno_duo" and elem == ".":
                if i > 0 and row[i - 1] == "S":
                    target_columns.append("S")
                    target_indexes.append(i)

    return (target_columns, target_indexes)


class TableLoader:
    @staticmethod
    def load(bdata: Optional[BytesIO] = None, filepath: Optional[Path] = None):
        if filepath:
            format = filepath.suffix.lower()
            if format == ".xls":
                return TableLoader._load_xls_data(filepath=filepath)
            elif format == ".xlsx":
                return TableLoader._load_xlsx_data(filepath=filepath)
            else:
                raise ValueError("Unsupported file type")
        elif bdata:
            bdata.seek(0)
            header = bdata.read(8)
            bdata.seek(0)

            if header.startswith(b"PK\x03\x04"):
                return TableLoader._load_xlsx_data(bdata=bdata)
            else:
                return TableLoader._load_xls_data(bdata=bdata)
        raise ValueError("No data provided")

    @staticmethod
    def _load_xls_data(
        bdata: Optional[BytesIO] = None, filepath: Optional[Path] = None
    ):
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
                return None

        sheet_texts = []
        sheets = wb.sheet_names()
        for sheetname in sheets:
            sheet = wb[sheetname]

            merged_ranges = []
            if hasattr(sheet, "merged_cells"):
                for merged_cell in sheet.merged_cells:
                    merged_ranges.append(
                        {
                            "min_row": merged_cell[0],
                            "max_row": merged_cell[1] - 1,
                            "min_col": merged_cell[2],
                            "max_col": merged_cell[3] - 1,
                        }
                    )

            st = SparseTable()
            cells = []
            for row in range(sheet.nrows):
                for col in range(sheet.ncols):
                    value = sheet.cell_value(row, col)
                    if value is None:
                        continue
                    clean_value = func.clean(str(value))
                    if clean_value == "":
                        continue

                    metadata = {
                        "value": clean_value,
                        "row": row,
                        "col": col,
                        "class": cell_classify(clean_value),
                        "is_merged": False,
                        "merged_info": None,
                    }

                    for mr in merged_ranges:
                        if (mr["min_row"] <= metadata["row"] <= mr["max_row"]) and (
                            mr["min_col"] <= metadata["col"] <= mr["max_col"]
                        ):
                            metadata["is_merged"] = True
                            metadata["merged_info"] = mr
                            break

                    st.add(row, col, clean_value)
                    cells.append(metadata)
            sheet_texts.append(st.get_text())
        return sheet_texts

    @staticmethod
    def _load_xlsx_data(
        bdata: Optional[BytesIO] = None, filepath: Optional[Path] = None
    ):
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
                return None

        sheet_texts = []
        sheets = wb.sheetnames
        for sheetname in sheets:
            sheet = wb[sheetname]

            merged_ranges = []
            if with_metadata:
                for merged_range in sheet.merged_cells.ranges:
                    merged_ranges.append(
                        {
                            "min_col": merged_range.min_col - 1,
                            "min_row": merged_range.min_row - 1,
                            "max_col": merged_range.max_col - 1,
                            "max_row": merged_range.max_row - 1,
                        }
                    )

            st = SparseTable()
            cells = []
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    clean_value = func.clean(str(cell.value))
                    if clean_value == "":
                        continue

                    metadata = {
                        "value": clean_value,
                        "row": cell.row - 1,
                        "col": cell.column - 1,
                        "class": cell_classify(clean_value),
                        "is_merged": False,
                        "merged_info": None,
                    }

                    for mr in merged_ranges:
                        if (
                            mr["min_row"] <= metadata["row"] <= mr["max_row"]
                            and mr["min_col"] <= metadata["col"] <= mr["max_col"]
                        ):
                            metadata["is_merged"] = True
                            metadata["merged_info"] = mr
                            break

                    st.add(cell.row - 1, cell.column - 1, clean_value)
                    cells.append(metadata)
            # print(st)
            sheet_texts.append(st.get_text())

        return sheet_texts
