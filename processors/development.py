from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from materials import DELIMETERS, ParserV2
from table import TableWorker, make_callculation_xlsx, make_request_xlsx, tp2


def test_callculation_table():
    input = Path("../private/tables/1249A.xls")
    output = Path("../private/results/1249A_aricles.xlsx")

    worker = TableWorker(None, input)
    worker.open_and_clean()
    if worker.tables is None or not bool(worker.tables):
        print("Errors with table")

    res = worker.simple_parser()
    if all(map(lambda x: x.size > 0, res)):
        print(res)

    unique_materials = set()
    for table in res:
        if table.empty:
            continue
        unique_materials |= set(table.material)
    unique_materials = list(unique_materials)

    # parsing materials (finding unique parts)
    unique_materials_dict = dict()
    unique_parts = set()
    parser = ParserV2(DELIMETERS)
    for material in unique_materials:
        parse_results = parser.parse(material)
        unique_materials_dict[material] = parse_results
        unique_parts |= set(parse_results.parts)

    wb = make_callculation_xlsx(res, unique_materials_dict)
    if wb is not None:
        wb.save(output)


def test_text():
    input = Path("../private/tables/1249A.xls")
    output = Path("../private/results/1249A_aricles.xlsx")

    data = tp2.TableLoader.load(None, input)
    if data is None:
        print("Wrong table")
        return

    text = [f"Sheet_{i}\n" + "\n".join(sheet) + "\n" for i, sheet in enumerate(data)]

    for row in data[0]:
        pattern = tp2.find_pattern_in_one_row(row)
        if pattern:
            print(f"<{row}>")
            print(pattern)


def main():
    # testfile = Path("../../private/tables/1108A.xls")
    inputs = Path("../private/tables")
    output = Path("../private/results/tables")

    parsed_cnt = 0
    all_cnt = 0
    error_files = []
    for file in inputs.iterdir():
        print("\n\n", file)
        all_cnt += 1

        worker = TableWorker(None, file)
        worker.open_and_clean()
        if worker.tables is None or not bool(worker.tables):
            print("Errors with table")
            error_files.append(file)
            continue

        res = worker.simple_parser()
        if all(map(lambda x: x.size > 0, res)):
            # print(res)
            parsed_cnt += 1

        unique_materials = set()
        for table in res:
            if table.empty:
                continue
            unique_materials |= set(table.material)
        unique_materials = list(unique_materials)

        # parsing materials (finding unique parts)
        unique_materials_dict = dict()
        unique_parts = set()
        parser = ParserV2(DELIMETERS)
        for material in unique_materials:
            parse_results = parser.parse(material)
            unique_materials_dict[material] = parse_results
            unique_parts |= set(parse_results.parts)

        wb = make_request_xlsx(res, unique_materials_dict)
        if wb is not None:
            wb.save(output / Path(file.name))
        wb2 = make_callculation_xlsx(res, unique_materials_dict)
        if wb2 is not None:
            wb2.save(output / (Path(file.stem + "_article" + file.suffix)))

    if all_cnt == 0:
        print("No files in the dir")
    else:
        print(f"Parsed: {parsed_cnt}/{all_cnt} = {parsed_cnt / all_cnt * 100:.1f}%")
        print(error_files)


def mainv2():
    # testfile = Path("../../private/tables/1108A.xls")
    inputs = Path("../private/tables")
    output = Path("../private/results/texts")
    output.mkdir(parents=True, exist_ok=True)

    parsed_cnt = 0
    all_cnt = 0
    error_files = []
    for file in inputs.iterdir():
        print("\n\n", file)

        try:
            data = tp2.TableLoader.load(None, file)
        except BaseException:
            print("ERROR: Wrong file!")
            continue
        all_cnt += 1

        if data is None:
            continue
        parsed_cnt += 1

        text = [
            f"Sheet_{i}\n" + "\n".join(sheet.get_text()) + "\n"
            for i, sheet in enumerate(data)
        ]
        with open(output / Path(file.stem + ".txt"), "w") as txtfile:
            txtfile.write("\n".join(text))

        for i, sheet in enumerate(data):
            print("id:", i)
            tp2.parser(sheet.get_text(), sheet.cells)
        # worker.open_and_clean()
        # if worker.tables is None or not bool(worker.tables):
        #     print("Errors with table")
        #     error_files.append(file)
        #     continue

        # res = worker.simple_parser()
        # if all(map(lambda x: x.size > 0, res)):
        #     # print(res)
        #     parsed_cnt += 1

        # unique_materials = set()
        # for table in res:
        #     if table.empty:
        #         continue
        #     unique_materials |= set(table.material)
        # unique_materials = list(unique_materials)

        # # parsing materials (finding unique parts)
        # unique_materials_dict = dict()
        # unique_parts = set()
        # parser = ParserV2(DELIMETERS)
        # for material in unique_materials:
        #     parse_results = parser.parse(material)
        #     unique_materials_dict[material] = parse_results
        #     unique_parts |= set(parse_results.parts)

        # wb = make_request_xlsx(res, unique_materials_dict)
        # if wb is not None:
        #     wb.save(output / Path(file.name))
        # wb2 = make_callculation_xlsx(res, unique_materials_dict)
        # if wb2 is not None:
        #     wb2.save(output / (Path(file.stem + "_article" + file.suffix)))

    if all_cnt == 0:
        print("No files in the dir")
    else:
        print(f"Parsed: {parsed_cnt}/{all_cnt} = {parsed_cnt / all_cnt * 100:.1f}%")
        print(error_files)


if __name__ == "__main__":
    # test_callculation_table()
    # main()
    mainv2()
    # test_text()
