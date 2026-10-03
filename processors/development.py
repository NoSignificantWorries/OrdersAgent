from itertools import pairwise
from pathlib import Path

from materials import DELIMETERS, ParserV2
from table import (
    TableWorker,
    make_callculation_xlsx,
    make_request_xlsx,
)
from table import loader as tl
from table import parser_v7 as tp
from table.puller import Source, get_data_by_horizontal_chains, make_horizontal_chains, merge_chains_in_table


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


def mainv5():
    # testfile = Path("../../private/tables/1108A.xls")
    inputs = Path("../private/tables")
    output = Path("../private/results/texts")
    output.mkdir(parents=True, exist_ok=True)

    parsed_cnt = 0
    all_cnt = 0
    error_files = []
    for file in inputs.iterdir():
        all_cnt += 1
        try:
            data = tl.TableLoader.load(file)
        except BaseException as err:
            print(f"ERROR: Wrong file '{file.name}'!", err)
            print("\n")
            error_files.append(file)
            continue

        print(data.name, data.fmt)
        print("\n")

        report, tables = tp.read(data)

        # for sheet in report.sheets:
        #     print(sheet.rows_match)
        #     print(sheet.cols_match)
        #     print("\n")

        print(len(tables))
        for table in tables:
            ann = tp.annotate_table(table)
            stats = tp.make_stats(ann)
            source = Source(table, ann, stats)
            chains = make_horizontal_chains(source)
            merged_chains = merge_chains_in_table(chains)
            # print(chains)
            subtables = get_data_by_horizontal_chains(merged_chains, source)
            for subtable in subtables:
                for row in subtable.data_rows.values():
                    print(row)
                print("\n")
            print("\n")

        parsed_cnt += 1

    if all_cnt == 0:
        print("No files in the dir")
    else:
        print(f"Parsed: {parsed_cnt}/{all_cnt} = {parsed_cnt / all_cnt * 100:.1f}%")
        print(error_files)


def mainv5_one_file():
    # input = Path("../private/tables/Бланк заявки Иван Баня 26.02.2026.xls")
    # input = Path("Заявка на стеклопакеты часть 4.xlsx")
    # input = Path("Заявка 17 М1.xlsx")  # for merged materials
    # input = Path("Заявка М1 на СП от 26.02.26.xlsx")  # two tables on nearest rows
    input = Path("Заявка на СП захватка №2.xlsx")
    # input = Path("Заявка на СП захватка №3.xlsx")
    # input = Path("ЗАЯВКА СП раскладка №1 вар №2 (MF Silver 70 + бр200).xlsx")
    # input = Path("../private/tables/BTs_Kirova_steklopakety.xlsx")

    input = Path("../private/tables") / input
    output = Path("../private/")
    output.mkdir(parents=True, exist_ok=True)

    # schm_maker = schemes.SchemeMaker(schemes.Schemes.REQUEST)
    # schm_maker.make_scheme()
    # schm_maker.wb.save(output / Path("test_request.xlsx"))

    # schm_maker = schemes.SchemeMaker(schemes.Schemes.CALC)
    # schm_maker.make_scheme()
    # schm_maker.wb.save(output / Path("test_calc.xlsx"))

    try:
        data = tl.TableLoader.load(input)
    except BaseException as err:
        print(f"ERROR: Wrong file '{input.name}'!", err)
        return

    print(data.name, data.fmt)

    report, tables = tp.read(data)

    # for sheet in report.sheets:
    #     print(sheet.rows_match)
    #     print(sheet.cols_match)
    #     print("\n")

    print(len(tables))
    for table in tables:
        ann = tp.annotate_table(table)
        stats = tp.make_stats(ann)
        source = Source(table, ann, stats)
        chains = make_horizontal_chains(source)
        merged_chains = merge_chains_in_table(chains)
        for ir, chn in chains.items():
            print(f"{ir}:", chn)
        print("\n")
        for ir, chn in merged_chains.items():
            print(f"{ir}:", chn)
        subtables = get_data_by_horizontal_chains(merged_chains, source)
        for subtable in subtables:
            for row in subtable.data_rows.values():
                print(row)
            print("\n")
        print("\n")

    # with open(output / Path(f"{report.name}.html"), "w") as file:
    #     file.write(report.to_html())


if __name__ == "__main__":
    # test_callculation_table()
    # main()

    # mainv5()
    mainv5_one_file()
