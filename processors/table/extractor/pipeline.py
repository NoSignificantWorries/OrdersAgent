from collections.abc import Generator
from dataclasses import dataclass

from table.annotate import AnnotatedTable, CellKind, CellRole, ResCell
from table.extractor import engine, specs
from table.extractor.specs import (
    Direction,
    Field,
    Header,
    HeaderSpec,
)

from .defaults import build_default_fields_registry, build_default_headers_registry


@dataclass
class Block:
    header: Header
    pos: tuple[int, int]
    data: dict[int, list[ResCell]]

    @staticmethod
    def make_position(header: Header) -> tuple[int, int]:
        if header.specs[0].direction == Direction.VERTICAL:
            return header.index, min(f.index for f in header.fields)
        return min(f.index for f in header.fields), header.index

    @property
    def data_size(self) -> int:
        return len(self.data)

    @property
    def empty(self) -> bool:
        return self.data_size == 0

    @property
    def valid_specs(self) -> list[bool]:
        return [spec.valid([field.spec.kind for field in self.header.fields]) for spec in self.header.specs]

    def validate_fields(self) -> list[bool]:
        return [self._validate_column(icol, field) for icol, field in enumerate(self.header.fields)]

    def _validate_column(self, icol: int, field: Field) -> bool:
        first_role = None
        for row in self.data.values():
            elem = row[icol]
            if elem.is_empty and not field.spec.none_allowed:
                return False
            if not elem.is_empty and elem.role not in field.spec.roles:
                return False
            first_role = first_role or elem.role
            if not elem.is_empty and not field.spec.multirole_allowed and elem.role != first_role:
                return False
        return True

    def drop_invalid_rows(self) -> list[int]:
        droped_rows: list[int] = []
        new_data: dict[int, list[ResCell]] = {}
        for irow, row in self.data.items():
            if self._drop_row(row):
                droped_rows.append(irow)
                continue
            new_data[irow] = row
        self.data = new_data
        return droped_rows

    def _drop_row(self, row: list[ResCell]) -> bool:
        for elem, field in zip(row, self.header.fields):
            if elem.is_empty and not field.spec.none_allowed:
                return True
            if not elem.is_empty and elem.role not in field.spec.roles:
                return True
        return False

    def fill_forward_material(self) -> bool:
        for icol, field in enumerate(self.header.fields):
            if field.spec.kind != CellKind.MATERIAL:
                continue

            last_cell = None
            for row in self.data.values():
                elem = row[icol]
                if elem.is_empty:
                    if last_cell:
                        row[icol] = ResCell(last_cell.value, last_cell.row, last_cell.col, last_cell.kind, last_cell.role)
                    else:
                        return False
                else:
                    last_cell = elem
        return True


class ExtractorPipeline:
    def __init__(self,
                 annotated_table: AnnotatedTable,
                 fields_registry: specs.FieldsRegistry | None = None,
                 headers_registry: specs.HeadersRegistry | None = None) -> None:

        self.engine = engine.TableEngine(annotated_table)
        self.fregistry = fields_registry or build_default_fields_registry()
        self.hregistry = headers_registry or build_default_headers_registry()

    ##########################
    ##    FIELDS BUILDER    ##
    ##########################

    def mark_header_rows(self) -> list[int]:
        return [irow for irow in self.engine.range_rows() if self.engine.has_header_in_row(irow)]

    def mark_header_cols(self) -> list[int]:
        return [icol for icol in self.engine.range_cols() if self.engine.has_header_in_col(icol)]

    def mark_field_rows(self) -> list[int]:
        return [irow for irow in self.engine.range_rows() if self.engine.has_field_in_row(irow)]

    def mark_field_cols(self) -> list[int]:
        return [icol for icol in self.engine.range_cols() if self.engine.has_field_in_col(icol)]

    def make_fields_in_row(self, irow: int, hcols: list[int]) -> dict[int, Field]:
        fields = {}
        for icol in hcols:
            cell = self.engine.get_cell(irow, icol)
            if cell is None:
                break
            if cell.role is CellRole.HEADER:
                spec = self.fregistry.get_by_kind(cell.kind)
                if spec is None:
                    continue

                field = Field(icol, [irow], spec)
                fields[icol] = field

        return fields

    def make_fields_in_col(self, icol: int, frows: list[int]) -> dict[int, Field]:
        fields = {}
        for irow in frows:
            cell = self.engine.get_cell(irow, icol)
            if cell is None:
                break
            if cell.role == CellRole.FIELD:
                spec = self.fregistry.get_by_kind(cell.kind)
                if spec is None:
                    continue

                field = Field(irow, [icol], spec)
                fields[irow] = field

        return fields

    def make_h_fields(self, hrows: list[int], hcols: list[int]) -> dict[int, dict[int, Field]]:
        fields = {}
        for irow in hrows:
            fields[irow] = self.make_fields_in_row(irow, hcols)

        return fields

    def make_v_fields(self, fcols: list[int], frows: list[int]) -> dict[int, dict[int, Field]]:
        fields = {}
        for icol in fcols:
            fields[icol] = self.make_fields_in_col(icol, frows)

        return fields

    def _has_numeric_brother(self, row: int, col: int) -> bool:
        if not self.engine.in_bounds(row, col + 1):
            return False
        right = self.engine.get_cell(row, col + 1)
        if right is None or right.kind != CellKind.EMPTY:
            return False

        r, c = row + 1, col + 1
        while self.engine.in_bounds(r, c):
            cur = self.engine.get_cell(r, c)
            left = self.engine.get_cell(r, c - 1)
            if cur is None or left is None:
                break
            if cur.role == CellRole.NUMERIC and left.role == CellRole.NUMERIC:
                return True
            if cur.kind == CellKind.EMPTY:
                r += 1
                continue
            break
        return False

    def _paired_size_positions(self, fields: dict[int, dict[int, Field]]) -> Generator[tuple[int, int]]:
        for irow, row in fields.items():
            for icol, field in row.items():
                if field.spec.kind != CellKind.SIZE:
                    continue
                if icol + 1 in row:
                    continue
                if self._has_numeric_brother(irow, icol):
                    yield irow, icol + 1

    def expand_paired_sizes(self, fields: dict[int, dict[int, Field]]) -> dict[int, dict[int, Field]]:
        size_spec = self.fregistry.get_by_kind(CellKind.SIZE)
        assert size_spec is not None, "SIZE spec must be registered"

        new_fields = {r: dict(row) for r, row in fields.items()}
        for irow, new_col in self._paired_size_positions(fields):
                new_fields[irow][new_col] = Field(new_col, [irow], size_spec)

        return {
            irow: {icol: row[icol] for icol in sorted(row)}
            for irow, row in new_fields.items()
        }

    ##########################
    ##    FIELDS MERGING    ##
    ##########################

    def merge_fields(self, field1: Field, field2: Field) -> Field | None:
        if field1.spec.kind != field2.spec.kind or field1.index != field2.index:
            return None
        return Field(
            field2.index,
            field1.sources + field2.sources,
            field2.spec
        )

    def merge_two_rows(self, row1: dict[int, Field], row2: dict[int, Field]) -> dict[int, Field] | None:
        keys = set(row1.keys()) | set(row2.keys())
        res: dict[int, Field] = {}
        for key in keys:
            f1 = row1.get(key)
            f2 = row2.get(key)
            if f1 and f2:
                merged = self.merge_fields(f1, f2)
                if merged is None:
                    return None
                res[key] = merged
            elif f1 and not f2:
                res[key] = f1
            elif not f1 and f2:
                res[key] = f2

        return res

    def merge_multiline_headers(self, fields_rows: dict[int, dict[int, Field]]) -> dict[int, dict[int, Field]]:
        if len(fields_rows) < 2:
            return fields_rows

        rows = sorted(fields_rows.items())
        res: dict[int, dict[int, Field]] = {}
        anchor, acc = rows[0]

        for irow, row in rows[1:]:
            merged = self.merge_two_rows(acc, row) if irow - anchor == 1 else None
            if merged is not None:
                anchor, acc = irow, merged
                continue
            res[anchor] = acc
            anchor, acc = irow, row

        res[anchor] = acc
        return res

    #######################################
    ##    HEADERS TO BLOCK TRANSITION    ##
    #######################################

    def build_headers_in_row(self, irow: int, row: dict[int, Field]) -> list[Header]:
        headers: list[Header] = []
        kinds: list[CellKind] = []
        fields: list[Field] = []

        last_schemes: list[HeaderSpec] = []
        for field in row.values():
            kind = field.spec.kind
            if not self.hregistry.kind_in(kind):
                continue

            schemes = self.hregistry.subschemes(kinds + [kind])
            if not schemes and last_schemes:
                headers.append(Header(irow, fields, last_schemes))
                kinds = [kind]
                last_schemes = self.hregistry.subschemes(kinds)
                fields = [field]
                continue

            last_schemes = schemes
            kinds.append(kind)
            fields.append(field)

        if fields:
            headers.append(Header(irow, fields, last_schemes))
        return headers

    def build_headers_in_col(self, icol: int, col: dict[int, Field]) -> list[Header]:
        headers: list[Header] = []
        kinds: list[CellKind] = []
        fields: list[Field] = []

        last_schemes: list[HeaderSpec] = []
        for field in col.values():
            kind = field.spec.kind
            if not self.hregistry.kind_in(kind):
                continue

            schemes = self.hregistry.subschemes(kinds + [kind])
            if not schemes and last_schemes:
                headers.append(Header(icol, fields, last_schemes))
                kinds = [kind]
                last_schemes = self.hregistry.subschemes(kinds)
                fields = [field]
                continue

            last_schemes = schemes
            kinds.append(kind)
            fields.append(field)

        if fields:
            headers.append(Header(icol, fields, last_schemes))
        return headers

    def build_h_header_objects(self, header_rows: dict[int, dict[int, Field]]) -> dict[int, list[Header]]:
        headers: dict[int, list[Header]] = {}
        for irow, row in header_rows.items():
            headers[irow] = self.build_headers_in_row(irow, row)

        return headers

    def build_v_header_objects(self, header_cols: dict[int, dict[int, Field]]) -> dict[int, list[Header]]:
        headers: dict[int, list[Header]] = {}
        for icol, col in header_cols.items():
            headers[icol] = self.build_headers_in_col(icol, col)

        return headers

    def _read_row_data(self, irow: int, header: Header) -> list[ResCell] | None:
        if self.engine.has_header_in_row(irow):
            return None

        cells = [self.engine.get_cell(irow, f.index) for f in header.fields]
        if any(c is None for c in cells):
            return None
        return cells

    def _read_col_data(self, icol: int, header: Header) -> list[ResCell] | None:
        if self.engine.has_field_in_col(icol):
            return None

        cells = [self.engine.get_cell(f.index, icol) for f in header.fields]
        if any(c is None for c in cells):
            return None
        return cells

    def build_h_block(self, header: Header) -> Block:
        data: dict[int, list[ResCell]] = {}
        for irow in self.engine.range_rows(header.index + 1):
            data_row = self._read_row_data(irow, header)
            if data_row is None:
                break
            data[irow] = data_row
        return Block(header, Block.make_position(header), data)

    def build_h_blocks(self, headers: dict[int, list[Header]]) -> list[Block]:
        blocks: list[Block] = []
        for row in headers.values():
            for header in row:
                block = self.build_h_block(header)
                blocks.append(block)
        return blocks

    def build_v_block(self, header: Header) -> Block:
        data: dict[int, list[ResCell]] = {}
        for icol in self.engine.range_cols(header.index + 1):
            data_col = self._read_col_data(icol, header)
            if data_col is None:
                break
            if all(data.kind == CellKind.EMPTY for data in data_col):
                continue
            data[icol] = data_col
            break
        return Block(header, Block.make_position(header), data)

    def build_v_blocks(self, headers: dict[int, list[Header]]) -> list[Block]:
        blocks: list[Block] = []
        for col in headers.values():
            for header in col:
                block = self.build_v_block(header)
                blocks.append(block)
        return blocks

    ###########################
    ##    BLOCKS CLEANING    ##
    ###########################

    def clean_blocks(self, blocks: list[Block]) -> list[Block]:
        not_empty_blocks: list[Block] = []
        for block in blocks:
            block.drop_invalid_rows()
            if not block.empty:
                not_empty_blocks.append(block)
        return not_empty_blocks

    ########################
    ##    RUN PIPELINE    ##
    ########################

    def run(self) -> list[Block]:
        header_rows = self.mark_header_rows()
        header_cols = self.mark_header_cols()

        h_fields_matrix = self.make_h_fields(header_rows, header_cols)
        size_paired_fields = self.expand_paired_sizes(h_fields_matrix)
        # print("Fields")
        # for i, row in size_paired_fields.items():
        #     for j, field in row.items():
        #         print(f"({i}, {j}): {field.index}: {field.sources}: {field.spec.kind.name}")
        #     print("---")

        field_cols = self.mark_field_cols()
        field_rows = self.mark_field_rows()

        v_fields_matrix = self.make_v_fields(field_cols, field_rows)
        # print("Vertical Fields")
        # for i, col in v_fields_matrix.items():
        #     for j, field in col.items():
        #         print(f"({j}, {i}): {field.index}: {field.sources}: {field.spec.kind.name}")
        #     print("---")

        merged_rows = self.merge_multiline_headers(size_paired_fields)
        # print("\n")
        # print("Merged")
        # for i, row in merged_rows.items():
        #     for j, field in row.items():
        #         print(f"({i}, {j}): {field.index}: {field.sources}: {field.spec.kind.name}")
        #     print("---")

        h_headers = self.build_h_header_objects(merged_rows)
        # print("\n")
        # print("Headers")
        # for i, header in h_headers.items():
        #     for h in header:
        #         for spec in h.specs:
        #             print(f"{i} ({spec.type.name}):", [f.spec.kind.name for f in h.fields], spec.valid([f.spec.kind for f in h.fields]))
        #     print("---")
        v_headers = self.build_v_header_objects(v_fields_matrix)
        # print("\n")
        # print("Vert Headers")
        # for i, header in v_headers.items():
        #     for h in header:
        #         for spec in h.specs:
        #             print(f"{i} ({spec.type.name}):", [f.spec.kind.name for f in h.fields], spec.valid([f.spec.kind for f in h.fields]))
        #     print("---")

        h_blocks = self.build_h_blocks(h_headers)
        # print("\n")
        # print("Blocks")
        # for block in blocks:
        #     print(block.header.index)
        #     for irow, data_row in block.data.items():
        #         print(f"{irow}:", [(data.role.name, data.value) for data in data_row])
        v_blocks = self.build_v_blocks(v_headers)
        # print("\n")
        # print("Blocks")
        # for block in v_blocks:
        #     print(block.header.index)
        #     for irow, data_row in block.data.items():
        #         print(f"{irow}:", [(data.role.name, data.value) for data in data_row])

        cleaned_h_blocks = self.clean_blocks(h_blocks)
        # print("\n")
        # print("Cleaned blocks")
        # for block in cleaned_blocks:
        #     print(block.header.index)
        #     for irow, data_row in block.data.items():
        #         print(f"{irow}:", [(data.role.name, data.value) for data in data_row])
        # print("\n")
        # print("Valid columns")
        # for block in cleaned_blocks:
        #     print(block.header.index)
        #     print([field.spec.kind.name for field in block.header.fields])
        #     print(block.validate_fields())
        cleaned_v_blocks = self.clean_blocks(v_blocks)
        # print("\n")
        # print("Cleaned blocks")
        # for block in cleaned_v_blocks:
        #     print(block.pos)
        #     for irow, data_row in block.data.items():
        #         print(f"{irow}:", [(data.role.name, data.value) for data in data_row])
        blocks = cleaned_h_blocks + cleaned_v_blocks
        blocks = sorted(blocks, key=lambda b: b.pos)
        print("\n")
        print("Cleaned blocks")
        for block in blocks:
            print(block.pos)
            print([field.spec.kind.name for field in block.header.fields])
            for irow, data_row in block.data.items():
                print(f"{irow}:", [(data.role.name, data.value) for data in data_row])

        return blocks
