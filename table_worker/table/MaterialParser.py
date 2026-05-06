import re
import csv
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .MaterialLibrary import MaterialMatcherORM, DatabaseManager, initialize_app


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

    def split_by_delim(self, delim: str) -> List[str]:
        if delim not in self._delims:
            raise ValueError(f"Undefined delimeter in the Block! Current delimeters: {list(self._delims.keys())}")
        parts = []
        last_idx = -1
        for idx in self._delims[delim].index:
            idx -= self._start + 1
            part = self._string[last_idx+1:idx]
            parts.append(part)
            last_idx = idx
        part = self._string[last_idx+1:]
        parts.append(part)

        return parts


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

    def get_level(self, level: int) -> Optional[List]:
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


@dataclass
class ParseResults:
    material: Optional[str] = None
    prefix: Optional[str] = None
    postfix: Optional[str] = None
    levels: Optional[BlockLevels] = None
    parts: List[str] = field(default_factory=list)
    matches: List[Tuple[ str, bool ]] = field(default_factory=list)
    parts_count: int = 0


class ParserV2:
    def __init__(self, delimeters: List[str]) -> None:
        self._delims = delimeters

    def _no_brekets_rule(self, levels: BlockLevels) -> ParseResults:
        general = levels.get_level(0)
        if not general:
            raise ValueError("Empty material string")
        general = general[0]

        cnt = general.max_delimeter_count
        if not general.max_delimeter or cnt < 1:
            return ParseResults(material=general.string, parts=[general.string], parts_count=1)

        parts = general.split_by_delim(general.max_delimeter)
        if cnt == 1:
            return ParseResults(material=general.string, parts=[parts[0]], postfix=parts[1], parts_count=1)
        elif cnt >= 2:
            return ParseResults(material=general.string, parts=parts, parts_count=len(parts))

        return ParseResults(material=general.string, parts=[general.string], parts_count=1)

    def _find_candidates(self, blocks: List[Block], general: Block) -> List[Block]:
        candidates = []
        cnt = general.max_delimeter_count
        for obj in blocks:
            obj_cnt = obj.max_delimeter_count
            if obj_cnt > cnt and obj_cnt > 1:
                candidates.append(obj)
        return candidates

    def _clean_p1_old(self, text_obj: str):
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

    def _clean_p1(self, text_obj: str):
        mat_no_space = r"СП[ДО]?\d+\s*(?:мм|:)?"
        mat_brackets = r"СП[ДО]?\s*\(\d+\)"
        mat_with_mm = r"СП[ДО]?\s+\d+\s*мм"

        mat1 = r"СП[ДО]?\s*\d+\s*^(мм)?:"

        pattern = rf"^({mat1})\s*(.*)$"

        prefix_pattern = re.compile(pattern, re.IGNORECASE)

        match = prefix_pattern.match(text_obj)

        prefix = ""
        p1 = text_obj
        if match:
            print(text_obj, match.groups())
            # prefix = match.group(1) or ""
            # p1 = match.group(3) or ""
        else:
            print(text_obj)

        return prefix, p1

    def _clean_last_p(self, text_obj: str):
        postfix = ""
        part = text_obj

        break_point = "(["
        green_point = ")"
        idx = -1
        for i, symbol in enumerate(text_obj):
            if symbol in break_point:
                return postfix, part
            if symbol in green_point:
                idx = i
                break

        if idx < 0:
            return postfix, part

        postfix = text_obj[idx + 1:].strip()
        part = text_obj[:idx].strip()

        return postfix, part

    def _parse(self, line: str) -> ParseResults:
        levels = _symbols_tree(line, self._delims)

        first_level = levels.get_level(1)
        if not first_level:
            res = self._no_brekets_rule(levels)
            # print(res)
            return res

        general = levels.get_level(0)
        if not general:
            raise ValueError("Empty material string")
        general = general[0]

        cnt = general.max_delimeter_count
        candidates = self._find_candidates(first_level, general)
        candidates_count = len(candidates)

        if cnt > 1:
            parts = general.split_by_delim(general.max_delimeter)
            res = ParseResults(material=general.string, parts=parts, parts_count=len(parts))
            return res

        if candidates_count == 1:
            candidate = candidates[0]
            start_i, end_i = candidate.start, candidate.end
            parts = candidate.split_by_delim(candidate.max_delimeter)
            prefix = general.string[:start_i]
            postfix = general.string[end_i + 1:]
            res = ParseResults(material=general.string, prefix=prefix, postfix=postfix, parts=parts, parts_count=len(parts))
            return res

        return ParseResults(material=line, parts=[line], parts_count=1)

    def _strip_all(self, results: ParseResults) -> ParseResults:
        if results.prefix:
            results.prefix = results.prefix.strip()
        if results.postfix:
            results.postfix = results.postfix.strip()
        new_parts = []
        for part in results.parts:
            new_parts.append(part.strip())
        results.parts = new_parts

        return results

    def parse(self, line: str) -> ParseResults:
        resuts = self._parse(line)
        if resuts.parts_count > 0:
            # processing p1
            # prefix, p1 = self._clean_p1(resuts.parts[0])
            # prefix = prefix.strip()
            # p1 = p1.strip()
            # if prefix:
            #     resuts.prefix = prefix
            # if p1:
            #     resuts.parts[0] = p1
            # else:
            #     del resuts.parts[0]

            # processing last p
            postfix, p = self._clean_last_p(resuts.parts[-1])
            postfix = postfix.strip()
            p = p.strip()
            if postfix:
                resuts.postfix = postfix
            if p:
                resuts.parts[-1] = p
            else:
                del resuts.parts[-1]

        resuts = self._strip_all(resuts)
        return resuts


class MaterialProcessor:
    def __init__(self, pipeline: ParserV2) -> None:
        self._pipeline = pipeline
        self._matcher = MaterialMatcherORM()

    async def process_line(self, line: str) -> Optional[ParseResults]:
        if not line:
            return None

        parsed = self._pipeline.parse(line)

        parts_from_lib = []
        for part in parsed.parts:
            target = await self._matcher.find_target(part)
            parts_from_lib.append(target)

        parsed.matches = parts_from_lib

        return parsed


async def development_async() -> None:
    await initialize_app()

    with open("res.txt", "r") as file:
        row_lines = file.readlines()
        lines = [line.rstrip("\n") for line in row_lines]

    pipeline = ParserV2(DELIMETERS)
    processor = MaterialProcessor(pipeline)

    results = []
    max_parts = 0
    for line in lines:
        if line:
            parsed = await processor.process_line(line)
            if parsed is None:
                print("[WARN]: Empty line")
                continue
            if parsed.levels is not None:
                print(parsed.levels)
            if parsed.parts_count > max_parts:
                max_parts = parsed.parts_count
            result = {
                    "material": parsed.material,
                    "prefix": parsed.prefix,
                    "postfix": parsed.postfix,
                }
            for i, (part, matched) in enumerate(zip(parsed.parts, parsed.matches)):
                result[f"p{i + 1}"] = part
                result[f"m{i + 1}"] = matched
            results.append(result)

    await DatabaseManager.close()

    ps = []
    for i in range(max_parts):
        ps.append(f"p{i + 1}")
        ps.append(f"m{i + 1}")

    fieldnames = ["material", "prefix"] + ps + ["postfix"]

    with open("res.csv", "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(results)


def development() -> None:
    asyncio.run(development_async())


if __name__ == "__main__":
    development()

