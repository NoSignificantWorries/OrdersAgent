import re
import csv
from sys import maxsize


def get_indexes(text: str, symbol: str):
    return [i for i, c in enumerate(text) if c == symbol]


class MaterialParser:
    def __init__(self) -> None:
        self._delims = ["-", "–", "—", "+", "x", "х", "*"]

    @property
    def delims(self):
        return self._delims

    def _clean_p1(self, text_obj: str):
        sep = "\s*"
        mat = "(СП[ДО]?)"
        size = f"\(?(\d*)\)?{sep}(мм)?"
        stuff = "[\(:]?"
        pattern = rf"^{mat}{sep}{size}{sep}{stuff}{sep}(.*)$"

        prefix_pattern = re.compile(pattern, re.IGNORECASE)

        match = prefix_pattern.match(text_obj)

        res = {
            "prefix": "",
            "thikness": "",
            "p1": text_obj
            }
        if match:
            res["prefix"] = match.group(1) or ""
            # print(match.group(2))
            res["thikness"] = match.group(2) or ""
            res["p1"] = match.group(4) or ""

        return res

    def _extended_clean_p1(self, text_obj: str):
        sep = "\s*"
        mat = "СП[ДО]?"
        size = f"\(?\d*\)?{sep}(мм)?"
        stuff = "[\(:]?"
        pattern = rf"^({mat}{sep}{size}{sep}{stuff}){sep}(.*)$"

        prefix_pattern = re.compile(pattern, re.IGNORECASE)

        match = prefix_pattern.match(text_obj)

        prefix = ""
        p1 = text_obj
        if match:
            prefix = match.group(1) or ""
            p1 = match.group(3) or ""

        return prefix, p1

    def _clean_last_p(self, part: str, text_obj: str):
        res = {
            "postfix": "",
            part: text_obj
            }
        break_point = "(["
        green_point = ")"
        idx = -1
        for i, symbol in enumerate(text_obj):
            if symbol in break_point:
                return res
            if symbol in green_point:
                idx = i
                break

        if idx < 0:
            return res
        res["postfix"] = text_obj[idx + 1:].strip()
        res[part] = text_obj[:idx].strip()

        return res

    def delimeters_parser(self, text: str):
        text = text.strip()
        res = {"material": text}
        max_del = None
        max_cnt = 0
        for delim in self._delims:
            cnt = text.count(delim)
            res[delim] = cnt
            if cnt > max_cnt:
                max_del = delim
                max_cnt = cnt

        if max_del is None:
            pass
        else:
            last_p = "p1"
            for i, cc in enumerate(text.split(max_del)):
                key = f"p{i + 1}"
                res[key] = cc
                last_p = key

        if max_cnt > 0:
            parsed_p1 = self._clean_p1(res["p1"])
            res.update(parsed_p1)
            parsed_last_p = self._clean_last_p(last_p, res[last_p])
            res.update(parsed_last_p)

        return res, max_cnt + 1

    def extended_delimeters_parser(self, text: str):
        text = text.strip()
        res_delims = [(delim, text.count(delim)) for delim in self.delims]
        max_delim, max_cnt = max(res_delims, key=lambda x: x[1])
        delims_dict = dict(res_delims)

        if max_cnt == 0:
            res = {
                    "material": text,
                    "prefix": "",
                    "p1": text,
                    "postfix": ""
                    }
            res.update(delims_dict)
            return res, 1
        if max_cnt == 1:
            p1, postfix = text.split(max_delim)
            res = {
                    "material": text,
                    "prefix": "",
                    "p1": p1,
                    "postfix": postfix
                    }
            res.update(delims_dict)
            return res, 1
        
        delim_indexes = get_indexes(text, max_delim)
        open_brek = get_indexes(text, "(")
        close_brek = get_indexes(text, ")")
        # print(text, delim_indexes, open_brek, close_brek)
        prefix = ""
        postfix = ""
        # outer brekets
        if open_brek:
            if open_brek[0] < delim_indexes[0] and close_brek[-1] > delim_indexes[-1]:
                content = text[open_brek[0] + 1:close_brek[-1]]
                prefix = text[:open_brek[0]]
                postfix = text[close_brek[-1] + 1:]
            else:
                content = text
        else:
            content = text

        res = {
                "material": text,
                "prefix": prefix,
                "postfix": postfix
                }
        idx = 0
        blocks = {}
        substring = ""
        in_block = False
        for symbol in content:
            if symbol == max_delim and not in_block:
                blocks[f"p{idx + 1}"] = substring
                substring = ""
                idx += 1
                continue
            if symbol in "([{":
                in_block = True
            if symbol in ")}]":
                in_block = False
            substring += symbol
        if substring:
            blocks[f"p{idx + 1}"] = substring

        res.update(blocks)

        if not prefix:
            prefix, p1 = self._extended_clean_p1(res["p1"])
            print(text, res["p1"], prefix, p1)
            res["prefix"] = prefix
            res["p1"] = p1

        for key in res.keys():
            res[key] = res[key].strip()

        res.update(delims_dict)

        return res, max_cnt + 1
            

def development() -> None:
    with open("res.txt", "r") as file:
        row_lines = file.readlines()
        lines = [line.rstrip("\n") for line in row_lines]

    parser = MaterialParser()

    results = []

    max_count = 0
    for line in lines:
        if line:
            result, max_cnt = parser.extended_delimeters_parser(line)
            # result, max_cnt = parser.delimeters_parser(line)
            if max_cnt > max_count:
                max_count = max_cnt
            results.append(result)

    if results:
        for res in results:
            for i in range(max_count):
                key = f"p{i+1}"
                if key not in res:
                    res[key] = ""

        ps = [f"p{i + 1}" for i in range(max_count)]

        # fieldnames = list(results[0].keys())
        fieldnames = ["material", "prefix"] + ps + ["postfix"] + parser.delims
        with open("res.csv", "w", newline="", encoding="utf-8") as csvfile:
            # fieldnames = ["material"] + [f"p{i+1}" for i in range(max_count)] + parser.delims
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=";")

            writer.writeheader()

            writer.writerows(results)
    else:
        print("N/A")


if __name__ == "__main__":
    development()

