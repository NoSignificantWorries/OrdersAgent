from typing import Dict, Optional, Self

table = [
    ["material", "___", None, "width", "height", "amount", "-0-", "barcode"],
    ["123", None, "12", "13", "1", None, "S1234"],
]


class Cell:
    values: Dict = {}

    def __new__(cls, row: int, col: int, value: Optional[str]) -> Optional[Self]:
        if value is None or not bool(value.strip()):
            return None
        instance = super().__new__(cls)
        return instance

    def __init__(self, row: int, col: int, value: str) -> None:
        self.row = row
        self.col = row
        value = value.strip()
        if not Cell.values.get(value):
            Cell.values[value] = []
        else:
            Cell.values


for i, row in enumerate(table):
    for j, col in enumerate(row):
        print(i, j, col)
