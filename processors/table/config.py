from dataclasses import dataclass
from enum import Enum, Flag, auto
from typing import Dict, List, Optional, Tuple


class CellType(Flag):
    TEXT = auto()
    NUMBER = auto()
    SIZES = auto()
    SIZE_H = auto()
    LENGTH_H = auto()
    WIDTH_H = auto()
    HEIGHT_H = auto()
    AMOUNT_H = auto()
    MAT_H = auto()
    BARCODE_H = auto()
    MARKING_H = auto()


HEADER = (
    CellType.MAT_H
    | CellType.AMOUNT_H
    | CellType.WIDTH_H
    | CellType.LENGTH_H
    | CellType.HEIGHT_H
    | CellType.SIZE_H
    | CellType.BARCODE_H
    | CellType.MARKING_H
)


@dataclass
class CellTypes:
    regex: Optional[Dict[CellType, List[Tuple[str, List[int]]]]] = None
    fuzzy: Optional[Dict[CellType, List[str]]] = None


TYPES_CONFIG = CellTypes(
    regex={
        CellType.NUMBER: [(r"^[+-]?\d+(?:[.,]\d+)?$", [])],
        CellType.SIZES: [(r"^\s*(\d+([.,]\d+)?)\s*[xXхХ]\s*(\d+([.,]\d+)?)\s*$", [1, 3])]
    },
    fuzzy={
        CellType.SIZE_H: [
            "размер",
            "размеры",
            "размеры,мм",
            "размеры[мм]",
            "размеры(мм)",
        ],
        CellType.LENGTH_H: ["длина", "длина,мм", "длина[мм]", "длина(мм)"],
        CellType.WIDTH_H: ["ширина", "ширина,мм", "ширина[мм]", "ширина(мм)"],
        CellType.HEIGHT_H: ["высота", "высота,мм", "высота[мм]", "высота(мм)"],
        CellType.AMOUNT_H: ["кол-во", "количество", "кол-во(шт)", "количество(шт)"],
        CellType.MAT_H: [
            "наименование",
            "обозначение",
            "имя",
            "номенклатура",
            "артикул",
            "типпакета",
            "формула",
            "формулазаполнения",
            "формуласп",
        ],
        CellType.BARCODE_H: ["штрихкод", "шк"],
        CellType.MARKING_H: ["маркировка"],
    },
)

COLUMN_RULES = {
    CellType.MAT_H: CellType.TEXT,
    CellType.WIDTH_H: CellType.NUMBER,
    CellType.HEIGHT_H: CellType.NUMBER,
    CellType.LENGTH_H: CellType.NUMBER,
    CellType.AMOUNT_H: CellType.NUMBER,
    CellType.BARCODE_H: CellType.TEXT | CellType.NUMBER,
    CellType.MARKING_H: CellType.TEXT | CellType.NUMBER,
    CellType.SIZE_H: CellType.NUMBER | CellType.SIZES
}

MERGES_CALLCULATION = [
    (43, 1, 46, 1),
    (48, 1, 68, 1),
    (12, 1, 16, 1),
    (3, 1, 7, 1),
    (10, 1, 11, 1),
    (31, 1, 32, 1),
    (33, 1, 42, 1),
]
HEADERS_CALLCULATION = {
    (0, 0): "ID",
    (0, 1): "Кол-во",
    (0, 2): "материалы",
    (0, 7): "Рамка от края",
    (0, 8): "Ед. Изм.",
    (0, 9): "размеры",
    (0, 11): "Припуск на обработку",
    (0, 16): "Вращ.",
    (0, 17): "Приор.",
    (0, 18): "Предп.",
    (0, 19): "Пирам.",
    (0, 20): "Пир1Р",
    (0, 21): "Пир2М",
    (0, 22): "Пир2Р",
    (0, 23): "Пир2М",
    (0, 24): "Этикетки",
    (0, 25): "Заказ",
    (0, 26): "Заказчик",
    (0, 27): "Дата раскроя",
    (0, 28): "Текст рамки",
    (0, 29): "Отв. В рамке",
    (0, 30): "Имя фигуры",
    (0, 32): "Shape Parameters",
    (0, 42): "Shape Trims",
    (0, 46): "Shape\nElaboration",
    (0, 47): "Piece Notes",
    (1, 2): "1материал",
    (1, 3): "1рамка",
    (1, 4): "2материал",
    (1, 5): "2рамка",
    (1, 6): "3материал",
    (1, 9): "X",
    (1, 10): "Y",
    (1, 11): "Общий",
    (1, 12): "X1",
    (1, 13): "Y1",
    (1, 14): "X2",
    (1, 15): "Y2",
    (1, 30): "Импорт",
    (1, 31): "Сохран.",
    (1, 32): "Par1",
    (1, 33): "Par2",
    (1, 34): "Par3",
    (1, 35): "Par4",
    (1, 36): "Par5",
    (1, 37): "Par6",
    (1, 38): "Par 7",
    (1, 39): "Par 8",
    (1, 40): "Par 9",
    (1, 41): "Par 10",
    (1, 42): "Rif X1",
    (1, 43): "Rif Y1",
    (1, 44): "Rif X2",
    (1, 45): "Rif Y2",
    (1, 47): "Note",
    (1, 48): "Note 1",
    (1, 49): "Note 2",
    (1, 50): "Note 3",
    (1, 51): "Note 4",
    (1, 52): "Note 5",
    (1, 53): "Note 6",
    (1, 54): "Note 7",
    (1, 55): "Note 8",
    (1, 56): "Note 9",
    (1, 57): "Note 10",
    (1, 58): "Note 11",
    (1, 59): "Note 12",
    (1, 60): "Note 13",
    (1, 61): "Note 14",
    (1, 62): "Note 15",
    (1, 63): "Note 16",
    (1, 64): "Note 17",
    (1, 65): "Note 18",
    (1, 66): "Note 19",
    (1, 67): "Note 20",
}
