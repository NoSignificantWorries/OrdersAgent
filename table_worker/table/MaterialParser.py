import re
import csv
from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum, auto
from sys import prefix
from typing import Dict, List, Optional, Tuple


DELIMETERS = ["-", "–", "—", "+", "x", "х", "*"]


class DelimetersList:
    def __init__(self) -> None:
        self._cnt = 0
        self._index = []

    def __str__(self) -> str:
        return f"(cnt={self._cnt}, indxes={self._index})"

    def __repr__(self) -> str:
        return f"(cnt={self._cnt}, indxes={self._index})"

    @property
    def count(self) -> int:
        return self._cnt

    @property
    def index(self) -> List:
        return self._index

    def add(self, idx):
        self._cnt += 1
        self._index.append(idx)


def _check_breket(breket: str) -> Optional[str]:
    if breket in "()":
        return "round"
    if breket in "{}":
        return "figure"
    if breket in "[]":
        return "square"
    if breket in "$":
        return "empty"
    return None


class Block:
    def __init__(self, brek: str, level: int, start_i: int, end_i: Optional[int] = None):
        self._btype = _check_breket(brek)
        if self._btype is None:
            raise ValueError(f"Unsupported breket symbol '{brek}'")

        self._level = level
        self._start = start_i
        self._end = end_i

        self._delims = {}
        self._max_delimeter = None
        self._max_count = 0
        self._string = None

    def __str__(self) -> str:
        return f"Block(btype={self._btype}, string={self._string}, level={self._level}, ({self._start}, {self._end})) delims={self._delims} max_delim={self._max_delimeter} count={self._max_count}"

    def __repr__(self) -> str:
        return f"Block(btype={self._btype}, string={self._string}, level={self._level}, ({self._start}, {self._end})) delims={self._delims} max_delim={self._max_delimeter} count={self._max_count}"

    @property
    def level(self) -> int:
        return self._level

    @property
    def btype(self) -> Optional[str]:
        return self._btype

    @property
    def start(self) -> int:
        return self._start

    @property
    def end(self) -> Optional[int]:
        return self._end

    @property
    def delims(self) -> Dict:
        return self._delims

    @property
    def max_delimeter(self) -> Optional[str]:
        return self._max_delimeter

    @property
    def max_delimeter_count(self) -> int:
        return self._max_count

    @property
    def string(self) -> Optional[str]:
        return self._string

    def get_pair(self) -> Tuple[int, Optional[int]]:
        return self._start, self._end

    def set_end(self, idx) -> None:
        self._end = idx

    def set_string(self, text: str) -> None:
        self._string = text

    def add_delim(self, delimeter: str, idx: int) -> None:
        if delimeter not in self._delims:
            self._delims[delimeter] = DelimetersList()

        self._delims[delimeter].add(idx)

        delim_cnt = self._delims[delimeter].count
        if delim_cnt > self._max_count:
            self._max_count = delim_cnt
            self._max_delimeter = delimeter

    def split_by_delim(self, delim: str) -> None:
        if delim not in self._delims:
            raise ValueError(f"Undefined delimeter in the Block! Current delimeters: {list(self._delims.keys())}")


class BlockLevels:
    def __init__(self) -> None:
        self._levels = {}
        self._depth = 0

    def __str__(self) -> str:
        return f"Levels(levels={self._levels}, depth={self._depth})"

    def __repr__(self) -> str:
        return f"Levels(levels={self._levels}, depth={self._depth})"

    @property
    def depth(self) -> int:
        return self._depth

    def get_level(self, level: int):
        return self._levels.get(level)

    def add_block(self, block: Block) -> None:
        lvl = block.level

        if lvl not in self._levels:
            self._levels[lvl] = []
        self._levels[lvl].append(block)

        if lvl > self._depth:
            self._depth = lvl


def _symbols_tree(line: str, delims: List[str]) -> BlockLevels:
    open_breks = "([{"
    close_breks = "}])"

    line = line.strip()

    idx = 0
    levels = BlockLevels()
    stack = []
    general_block = Block("$", 0, -1, len(line))
    general_block.set_string(line)

    for i, symbol in enumerate(line):
        if symbol in open_breks:
            idx += 1
            stack.append(Block(symbol, idx, i))
        elif symbol in close_breks:
            if _check_breket(symbol) == stack[-1].btype:
                block = stack.pop(-1)
                block.set_end(i)
                block.set_string(line[block.start + 1:block.end])
                levels.add_block(block)
                idx -= 1
            else:
                raise ValueError(f"Wrong brekets format at {i}: '{symbol}'")
        elif symbol in delims:
            if stack:
                stack[-1].add_delim(symbol, i)
            else:
                general_block.add_delim(symbol, i)

    if stack:
        raise ValueError(f"Wrong brekets format at {i}: '{symbol}'")

    levels.add_block(general_block)
    return levels


class ParseAction(Enum):
    NO_ACTION = auto()


@dataclass
class ParseResult:
    action: ParseAction
    prefix: Optional[str] = None
    content: Optional[str] = None
    postfix: Optional[str] = None
    content: Optional[str] = None
    breket: Optional[Block] = None

    @classmethod
    def no_action(cls):
        return cls(action=ParseAction.NO_ACTION)


class ParseRule(ABC):
    @abstractmethod 
    def can_apply(self, levels: BlockLevels) -> bool:
        pass

    @abstractmethod 
    def apply(self, line: str, levels: BlockLevels) -> Optional[ParseResult]:
        pass


class ParsePipeline:
    def __init__(self, delimeters: List[str]) -> None:
        self._delims = delimeters
        self._rules: List[ParseRule] = []

    def parse(self, line: str) -> ParseResult:
        levels = _symbols_tree(line, self._delims)

        for rule in self._rules:
            if rule.can_apply(levels):
                result = rule.apply(line, levels)
                if result and result.action != ParseAction.NO_ACTION:
                    return result

        return ParseResult.no_action()

    def add_rule(self, rule: ParseRule) -> None:
        self._rules.append(rule)


class MaterialParser:
    def __init__(self) -> None:
        self._delims = DELIMETERS

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
        pattern = rf"^({mat}{sep}{size}{sep}){sep}{stuff}{sep}(.*)$"

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

    print(_brekets_and_delims_tree("aaa-aaa-(bb{c}d)-ee[f]", parser.delims))


def dev2() -> None:
    parser = MaterialParser()
    tree = _symbols_tree("aaa-aaa-(bb{c+b+e}d)-ee[f]", parser.delims)



if __name__ == "__main__":
    # development()
    dev2()

