
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


def normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[\(\[,\.\s]+', '', s)
    return s


PATTERNS = [
    'длина', 'длинамм',
    'ширина', 'ширинамм',
    'высота', 'высотамм',
    'размер', 'размеры', 'размерымм',
    'количество', 'количествошт', 'колво', 'колвошт',
    'наименование', 'номенклатура', 'артикул', 'маркировка',
    'формула', 'формуласп', 'формулазаполнения',
    'штрихкод', 'обозначение', 'типпакета', 'стекла',
]

K = 1
buckets = defaultdict(list)
for p in sorted(PATTERNS, key=len):
    buckets[len(p)].append(p)


def candidates(text: str):
    t = normalize(text)
    n = len(t)
    for L in range(n - K, n + K + 1):
        for p in buckets.get(L, ()):
            yield p, t
