from pathlib import Path
from typing import Optional, Dict, Type, List, Any
from io import BytesIO

import openpyxl
import xlrd

from . import functional as func
from . import config as conf


class BasicStartegy:
    def __init__(self) -> None:
        self.headers: Dict[conf.CellType, List[Dict]] = {}
        self.current_header_columns: Dict[int, conf.CellType] = {}
        self.per_header_data_blocks: Dict[conf.CellType, List[Any]] = {}

    def add_cell(self, cell: Dict):
        raise NotImplementedError("'add_cell' method not implemented")


class SimpleStrategy(BasicStartegy):
    def __init__(self) -> None:
        super().__init__()

    def add_cell(self, cell: Dict):
        if cell["class"] in conf.HEADER:
            self.current_header_columns[cell["col"]] = cell["class"]
            if cell["class"] not in self.headers:
                self.headers[cell["class"]] = []
            self.headers[cell["class"]].append(cell)
            return
        if cell["col"] not in self.current_header_columns:
            return
        col_cls = self.current_header_columns[cell["col"]]
        if col_cls not in self.per_header_data_blocks:
            self.per_header_data_blocks[col_cls] = []
        if cell["class"] in conf.COLUMN_RULES[col_cls]:
            self.per_header_data_blocks[col_cls].append(cell)


class StrategyManager:
    def __init__(self) -> None:
        self.strategies: List[Type[BasicStartegy]] = [SimpleStrategy]
        self._active_startegies = []

    def activate(self):
        self._active_startegies = [strategy() for strategy in self.strategies]

    def add_cell(self, cell: Dict):
        for strategy in self._active_startegies:
            strategy.add_cell(cell)


def cell_classify(value: str):
    if conf.TYPES_CONFIG.regex is not None:
        for cell_type, patterns in conf.TYPES_CONFIG.regex.items():
            for (pattern, groups) in patterns:
                if func.check_fullmatch(pattern, value):
                    return cell_type
    if conf.TYPES_CONFIG.fuzzy is not None:
        for cell_type, patterns in conf.TYPES_CONFIG.fuzzy.items():
            for pattern in patterns:
                if func.fuzzy_match(value.lower(), pattern, 90):
                    return cell_type
    return conf.CellType.TEXT

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

            if header.startswith(b'PK\x03\x04'):
                return TableLoader._load_xlsx_data(bdata=bdata)
            else:
                return TableLoader._load_xls_data(bdata=bdata)
        raise ValueError("No data provided")

    @staticmethod
    def _load_xls_data(bdata: Optional[BytesIO] = None, filepath: Optional[Path] = None):
        try:
            if filepath:
                wb = xlrd.open_workbook(str(filepath), formatting_info=True)
            elif bdata:
                bdata.seek(0)
                wb = xlrd.open_workbook(file_contents=bdata.read(), formatting_info=True)
            else:
                raise ValueError("Unsupported file type")
            with_metadata = True
        except Exception as first_step_error:
            try:
                if filepath:
                    wb = xlrd.open_workbook(str(filepath), formatting_info=False)
                elif bdata:
                    bdata.seek(0)
                    wb = xlrd.open_workbook(file_contents=bdata.read(), formatting_info=False)
                else:
                    raise ValueError("Unsupported file type")
                with_metadata = False
            except Exception as err:
                print(f"File opening errors: {first_step_error} {err}")
                return None

        sheets = wb.sheet_names()
        for sheetname in sheets:
            sheet = wb[sheetname]

            sm = StrategyManager()
            sm.activate()

            merged_ranges = []
            if hasattr(sheet, 'merged_cells'):
                for merged_cell in sheet.merged_cells:
                    merged_ranges.append({
                        'min_row': merged_cell[0],
                        'max_row': merged_cell[1] - 1,
                        'min_col': merged_cell[2],
                        'max_col': merged_cell[3] - 1,
                    })

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
                        "merged_info": None
                    }

                    for mr in merged_ranges:
                        if (mr["min_row"] <= metadata["row"] <= mr["max_row"]) and (mr["min_col"] <= metadata["col"] <= mr["max_col"]):
                            metadata["is_merged"] = True
                            metadata["merged_info"] = mr
                            break

                    cells.append(metadata)
                    sm.add_cell(metadata)
            # print(sm._active_startegies[0].per_header_data_blocks)
            print(sm._active_startegies[0].headers)

        return with_metadata

    @staticmethod
    def _load_xlsx_data(bdata: Optional[BytesIO] = None, filepath: Optional[Path] = None):
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

        sheets = wb.sheetnames
        for sheetname in sheets:
            sheet = wb[sheetname]

            sm = StrategyManager()
            sm.activate()

            merged_ranges = []
            if with_metadata:
                for merged_range in sheet.merged_cells.ranges:
                    merged_ranges.append({
                        "min_col": merged_range.min_col - 1,
                        "min_row": merged_range.min_row - 1,
                        "max_col": merged_range.max_col - 1,
                        "max_row": merged_range.max_row - 1
                    })

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
                        "merged_info": None
                    }

                    for mr in merged_ranges:
                        if mr["min_row"] <= metadata["row"] <= mr["max_row"] and mr["min_col"] <= metadata["col"] <= mr["max_col"]:
                            metadata["is_merged"] = True
                            metadata["merged_info"] = mr
                            break

                    cells.append(metadata)
                    sm.add_cell(metadata)
            # print(sm._active_startegies[0].per_header_data_blocks)
            print(sm._active_startegies[0].headers)


        return with_metadata
