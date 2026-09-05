import json
from pathlib import Path

from materials import DELIMETERS, ParserV2
from table import TableWorker, make_callculation_xlsx, make_request_xlsx
from table import config as conf
from table import table_processer_v4 as tp4
from table import table_processer_v4_1 as tp4_1


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



def mainv4():
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
            data = tp4.TableLoader.load(None, file)
        except BaseException as err:
            print("ERROR: Wrong file!", err)
            continue
        all_cnt += 1

        if data is None:
            continue
        parsed_cnt += 1

        for sheet in data.sheets.values():
            print(sheet.name, sheet.nrows, sheet.ncols)
            print(sheet.type_cells)


    if all_cnt == 0:
        print("No files in the dir")
    else:
        print(f"Parsed: {parsed_cnt}/{all_cnt} = {parsed_cnt / all_cnt * 100:.1f}%")
        print(error_files)


def mainv4_1():
    # testfile = Path("../../private/tables/1108A.xls")
    inputs = Path("../private/tables")
    output = Path("../private/results/texts")
    output.mkdir(parents=True, exist_ok=True)

    parsed_cnt = 0
    all_cnt = 0
    error_files = []
    header_packs = []
    for file in inputs.iterdir():
        print("\n\n", file)

        try:
            data = tp4_1.TableLoader.load(None, file)
        except BaseException as err:
            print("ERROR: Wrong file!", err)
            continue
        all_cnt += 1

        if data is None:
            continue
        parsed_cnt += 1

        for sheet in data.sheets.values():
            print(sheet.name, sheet.nrows, sheet.ncols)
            if sheet.empty:
                continue
            headers_on_sheet = {"nrows": sheet.nrows, "ncols": sheet.ncols, "headers": []}
            headers = sheet.find_headers()
            for header in headers:
                headers_on_sheet["headers"].append(header.to_json())
            header_packs.append(headers_on_sheet)
    with open("../private/headers.json", "w") as file:
        json.dump(header_packs, file, indent=4)


    if all_cnt == 0:
        print("No files in the dir")
    else:
        print(f"Parsed: {parsed_cnt}/{all_cnt} = {parsed_cnt / all_cnt * 100:.1f}%")
        print(error_files)


if __name__ == "__main__":
    # test_callculation_table()
    # main()
    # test_text()
    # mainv2()
    # test_ascii_table()
    # mainv3()
    # mainv4()
    mainv4_1()
