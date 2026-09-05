import json
from pathlib import Path

import matplotlib.pyplot as plt

class_colors = {
    "EMPTY": "#E8E8E8",      # Светло-серый (почти незаметный)
    "TEXT": "#D0D0D0",       # Светло-серый
    "NUMBER": "#C8C8C8",     # Серый
    "SIZES": "#BEBEBE",      # Серый
    "SIZE_H": "#FF1744",     # Ярко-красный (заголовок)
    "LENGTH_H": "#D500F9",   # Ярко-фиолетовый (заголовок)
    "WIDTH_H": "#2979FF",    # Ярко-синий (заголовок)
    "HEIGHT_H": "#00E676",   # Ярко-зеленый (заголовок)
    "AMOUNT_H": "#00ff00",   # Ярко-оранжевый (заголовок)
    "MAT_H": "#FFD740",      # Ярко-желтый (заголовок)
    "BARCODE_H": "#00BCD4",  # Ярко-голубой (заголовок)
    "MARKING_H": "#ff0000",  # Ярко-пурпурный (заголовок)
    "GLASS": "#FF4081"       # Ярко-розовый (особо заметный)
}


def mainv4_1():
    input = Path("../private/headers.json")

    with open(input, "r") as file:
        data = json.load(file)

    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(10, 16))

    max_rows = 0
    max_cols = 0
    for pack in data:
        nrows = pack.get("nrows", 0)
        ncols = pack.get("ncols", 0)
        headers = pack.get("headers", None)
        if nrows == 0 or ncols == 0 or headers is None:
            continue

        max_rows = max(nrows, max_rows)
        max_cols = max(ncols, max_cols)
        for header in headers:
            row = header.get("row", 0)
            col = header.get("col", 0)
            color = class_colors[header["type-name"]]
            ax.scatter(
                col + 0.5,
                -(row + 0.5),
                c=color,
                s=10,
                edgecolors='black',
                linewidth=0.5,
                alpha=0.8,
                zorder=5,
            )

    step = 1  # Шаг сетки
    ax.set_xticks(range(0, int(max_cols) + 1, step))
    ax.set_yticks(range(-int(max_rows) - 1, 1, step))
    ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)

    plt.legend()
    plt.show()


if __name__ == "__main__":
    mainv4_1()
