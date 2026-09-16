from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

import openpyxl
import xlrd

from . import table_loader as tl


class TableParser:
    def __init__(self, workbook: tl.Workbook) -> None:
        self.wb = workbook

    def parse(self) -> None:
        for sheet in self.wb.sheets:
            for cell in sheet.cells:
                print(cell)
