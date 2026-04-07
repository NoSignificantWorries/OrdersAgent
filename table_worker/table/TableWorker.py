from operator import is_
import re
import json
from functools import partial
from html import escape
from pathlib import Path
from typing import Optional, Tuple

# data working
import numpy as np
import pandas as pd
# tables processing
import openpyxl
import xlrd

from rapidfuzz import fuzz

import tqdm


_basic_table = """
<!DOCTYPE html>
<html lang="ru">
  <head>
    <meta charset="UTF-8">
    <title>File: {filename}</title>
    <style>
    table {{ border-collapse: collapse; font-family: sans-serif; font-size: 12px; }}
    td, th {{ border: 1px solid #000; padding: 2px 4px; max-width: 200px; overflow: hidden; white-space: nowrap; }}
    .cell-number    {{ background-color: #e0ffe0; }}
    .cell-text {{ background-color: #e0f0ff; }}
    .cell-barcode {{ background-color: #f5c2e7; }}
    .cell-maybe-material {{ background-color: #74c7ec; }}
    .cell-empty    {{ background-color: #666; color: #222; }}
    .cell-size {{ background-color: #00ff00; }}
    .cell-amount {{ background-color: #ffff00; }}
    .cell-material {{ background-color: #00ffff; }}
    </style>
  </head>
  <body>
    <table>{table}</table>
  </body>
</html>
"""


def _get_filename(path: Path):
    filename = "".join(path.name.split('.')[:-1])
    return filename

def _make_table(df: pd.DataFrame, classes_df: pd.DataFrame) -> str:
    html_rows = []
    for (_, row), (_, class_row) in zip(df.iterrows(), classes_df.iterrows()):
        tds = []
        for cell, cell_class in zip(row, class_row):
            if pd.isna(cell):
                val = "NULL"
            else:
                val = str(cell)
            tds.append(f"<td class='cell-{cell_class}'>{escape(val)}</td>")
        html_rows.append("<tr>" + "".join(tds) + "</tr>")
    table_html = "\n".join(html_rows)
    return table_html

def _create_table(df: pd.DataFrame, classes_df: pd.DataFrame, filepath: Path) -> None:
    table_html = _make_table(df, classes_df)

    filename = _get_filename(filepath)
    content = _basic_table.format(table=table_html, filename=filename)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as file:
        file.write(content)


def _get_values_by_class(df: pd.DataFrame, classes_df: pd.DataFrame, key_classes: Tuple[str, ...]):
    origin_flat = df.stack()
    classes_flat = classes_df.stack()
    mask = None
    for key_class in key_classes:
        local_mask = classes_flat == key_class
        if mask is None:
            mask = local_mask
        else:
            mask = local_mask | mask
    data = origin_flat[mask]
    result = pd.DataFrame({
        "data": data.values
    })
    result["class"] = 0
    return result


class ColumnsConfig:
    def __init__(self, config_path):
        self.path = config_path

        with open(self.path, "r") as file:
            data = json.load(file)

        self.col_asc = data["column-associations"]
        self.cell_regex = data["regex-classes"]


def fuzzy_match(text, pattern, threshold=50) -> bool:
    val = fuzz.ratio(text, pattern)
    return val >= threshold

def match_class(cell, config: ColumnsConfig) -> str:
    if pd.isna(cell):
        return "empty"
    cell = str(cell)
    cell = re.sub(r"\s*", "", cell)

    for (cls, pattern) in config.cell_regex.items():
        if re.fullmatch(pattern, cell):
            return cls

    for (cls, associations) in config.col_asc.items():
        for asc in associations:
            if fuzzy_match(cell.lower(), asc, 65):
                return cls

    return "text"


def match_classes_to_df(data: pd.DataFrame, config: ColumnsConfig) -> pd.DataFrame:
    classes = pd.DataFrame(index=data.index, columns=data.columns)
    match_class_with_config = partial(match_class, config=config)
    for col_idx in data.columns:
        col = data[col_idx].astype(str)
        classes[col_idx] = col.apply(match_class_with_config)
    return classes


class TableWorker:
    def __init__(self, file: Path, config: ColumnsConfig) -> None:
        self.path = file
        self.format = file.suffix
        self.name = "".join(file.name.split(".")[:-1])
        self.sheets_dfs = []
        self.classes_dfs = []

        self.config = config

    def open_and_clean(self):
        if self.format == ".xls":
            self._open_and_clean_xls()
        elif self.format == ".xlsx":
            self._open_and_clean_xlsx()

    def _open_and_clean_xls(self):
        try:
            wb = xlrd.open_workbook(str(self.path), formatting_info=False)
        except Exception:
            return

        sheets = wb.sheet_names()
        for sheetname in sheets:
            sheet = wb[sheetname]

            data = [
                [sheet.cell_value(row, col) for col in range(sheet.ncols)]
                for row in range(sheet.nrows)
            ]

            df = pd.DataFrame(data)
            df = df.astype(str)
            df = df.astype(str).replace('nan', np.nan)
            df = df.replace(r'^\s*$', np.nan, regex=True)

            df.dropna(axis=0, how='all', inplace=True)
            df.dropna(axis=1, how='all', inplace=True)
            df = df.reset_index(drop=True)

            self.sheets_dfs.append(df)


    def _open_and_clean_xlsx(self):
        wb = openpyxl.load_workbook(self.path)

        sheets = wb.sheetnames
        for sheetname in sheets:
            # loading sheet
            sheet = wb[sheetname]

            # merged = sheet.merged_cells.ranges

            data = sheet.values
            df = pd.DataFrame(data)
            df = df.astype(str)
            df = df.astype(str).replace('nan', np.nan)
            df = df.replace(r'^\s*$', np.nan, regex=True)

            df.dropna(axis=0, how='all', inplace=True)
            df.dropna(axis=1, how='all', inplace=True)
            df = df.reset_index(drop=True)

            self.sheets_dfs.append(df)

    def match_classes(self):
        tmp_dfs = []
        for df in self.sheets_dfs:
            tmp_dfs.append(match_classes_to_df(df, self.config))
        self.classes_dfs = tmp_dfs

    def crop_table(self):
        search_for = {"material": 1, "size": 2, "amount": 1}
        classes_mask = ["text", "number", "number", "number"]
        is_mask = False
        indexes = None
        for df, df_vals in zip(self.classes_dfs, self.sheets_dfs):
            for i, row in df.iterrows():
                # print(i, row.to_list())
                mask = [(row == key).sum() == cnt for key, cnt in search_for.items()]
                if all(mask):
                    # print("-->", i)
                    is_mask = True
                    col_idx = []
                    for key in search_for.keys():
                        col_idx += (row[row == key].index - 1).to_list()
                    indexes = col_idx
                elif is_mask:
                    # print("==>", i)
                    classes_in_row = row.iloc[indexes].to_list()
                    values = df_vals.iloc[i, indexes].to_list()
                    bins = [cls_r in classes_mask for cls_r in classes_in_row]
                    # print(bins, all(bins))
                    if all(bins):
                        values = df_vals.iloc[i, indexes].to_list()
                        # print(classes_in_row, values)
                    else:
                        is_mask = False
                        indexes = None




def development():
    private_dir = Path("~/Projects/OrdersAgent/private").expanduser()
    tables_path = private_dir / Path("tables")
    result_path = private_dir / Path("results/tables")

    config_path = Path("../config.json").resolve()
    conf = ColumnsConfig(config_path)

    # table_path = tables_path / Path("BTs_Kirova_steklopakety.xlsx")

    # for table_path in tables_path.iterdir():
    # table_path = tables_path / Path("BTs_Kirova_steklopakety.xlsx")
    table_path = tables_path / Path("1108A.xls")

    table = TableWorker(table_path, conf)

    table.open_and_clean()
    table.match_classes()
    table.crop_table()

    for i, (sheet, classes) in enumerate(zip(table.sheets_dfs, table.classes_dfs)):
        save_table_path = result_path / Path(f"{table.name}_sheet_{i}.html")
        _create_table(sheet, classes, result_path / save_table_path)


if __name__ == "__main__":
    development()

