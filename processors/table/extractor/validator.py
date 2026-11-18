from collections import Counter
from dataclasses import dataclass

from table.annotate import CellKind

from .pipeline import Block
from .specs import HeaderSpec, HeaderType


@dataclass(frozen=True)
class DataChunk:
    nrows: int
    material: list[str]
    X: list[int]
    Y: list[int]
    amount: list[int]
    marking: list[int | str | None]
    barcode: list[int | str | None]

    @property
    def unique_materials(self) -> dict[str, int]:
        return Counter(self.material)


def merge_chunks(chunks: list[DataChunk]) -> DataChunk | None:
    if not chunks:
        return None
    if len(chunks) < 2:
        return chunks[0]
    nrows = 0
    material = []
    X = []
    Y = []
    amount = []
    marking = []
    barcode = []
    for chunk in chunks:
        material += chunk.material
        nrows += chunk.nrows
        X += chunk.X
        Y += chunk.Y
        amount += chunk.amount
        marking += chunk.marking
        barcode += chunk.barcode
    return DataChunk(nrows, material, X, Y, amount, marking, barcode)


class ValidatorPipeline:
    @classmethod
    def fill_forward_materials(cls, blocks: list[Block]) -> list[Block]:
        processed_blocks: list[Block] = []
        for block in blocks:
            if block.fill_forward_material():
                processed_blocks.append(block)
        return processed_blocks

    @classmethod
    def valildate_blocks(cls, blocks: list[Block]) -> list[Block]:
        result_blocks: list[Block] = []
        for block in blocks:
            validated_block = cls._valildate_schemes_in_block(block)
            if validated_block:
                result_blocks.append(block)
        return result_blocks

    @classmethod
    def _valildate_schemes_in_block(cls, block: Block) -> Block | None:
        new_specs: list[HeaderSpec] = []
        for spec, valid in zip(block.header.specs, block.valid_specs):
            if valid and cls._check_spec_data(spec, block):
                new_specs.append(spec)
        if not new_specs:
            return None
        block.header.specs = new_specs
        return block

    @classmethod
    def _check_spec_data(cls, spec: HeaderSpec, block: Block) -> bool:
        for kind in spec.scheme:
            for field, valid in zip(block.header.fields, block.validate_fields()):
                if field.spec.kind != kind:
                    continue
                if not valid:
                    return False
        return True

    @classmethod
    def blocks_to_chunks(cls, blocks: list[Block]) -> list[DataChunk]:
        chunks: list[DataChunk] = []
        for block in blocks:
            spec = block.header.specs[0]
            match spec.type:
                case HeaderType.STANDART:
                    chunks.append(cls._standart_header(block))
                case HeaderType.ONE_SIZE_COLUMN:
                    chunks.append(cls._one_culumn_size_header(block))
                case _:
                    print("Not supported block type")
        return chunks

    @classmethod
    def _standart_header(cls, block: Block) -> DataChunk:
        mat_index = block.header.find_kind_indexes(CellKind.MATERIAL)[0]
        x_index, y_index = block.header.find_kind_indexes(CellKind.SIZE)[:2]
        amount_index = block.header.find_kind_indexes(CellKind.AMOUNT)[0]
        marking_index = block.header.find_kind_indexes(CellKind.MARKING)
        is_marking = len(marking_index) == 1
        if is_marking:
            marking_index = marking_index[0]
        barcode_index = block.header.find_kind_indexes(CellKind.BARCODE)
        is_barcode = len(barcode_index) == 1
        if is_barcode:
            barcode_index = barcode_index[0]

        material: list[str] = []
        X: list[int] = []
        Y: list[int] = []
        amount: list[int] = []
        marking: list[int | str | None] = []
        barcode: list[int | str | None] = []
        for row in block.data.values():
            material.append(row[mat_index].value)
            X.append(row[x_index].value)
            Y.append(row[y_index].value)
            amount.append(row[amount_index].value)
            marking.append(row[marking_index].value if is_marking else None)
            barcode.append(row[barcode_index].value if is_barcode else None)

        return DataChunk(block.data_size, material, X, Y, amount, marking, barcode)

    @classmethod
    def _one_culumn_size_header(cls, block: Block) -> DataChunk:
        mat_index = block.header.find_kind_indexes(CellKind.MATERIAL)[0]
        sizes_index = block.header.find_kind_indexes(CellKind.SIZE)[0]
        amount_index = block.header.find_kind_indexes(CellKind.AMOUNT)[0]
        marking_index = block.header.find_kind_indexes(CellKind.MARKING)
        is_marking = len(marking_index) == 1
        if is_marking:
            marking_index = marking_index[0]
        barcode_index = block.header.find_kind_indexes(CellKind.BARCODE)
        is_barcode = len(barcode_index) == 1
        if is_barcode:
            barcode_index = barcode_index[0]

        material: list[str] = []
        X: list[int] = []
        Y: list[int] = []
        amount: list[int] = []
        marking: list[int | str | None] = []
        barcode: list[int | str | None] = []
        for row in block.data.values():
            material.append(row[mat_index].value)
            x, y = row[sizes_index].value
            X.append(x)
            Y.append(y)
            amount.append(row[amount_index].value)
            marking.append(row[marking_index].value if is_marking else None)
            barcode.append(row[barcode_index].value if is_barcode else None)

        return DataChunk(block.data_size, material, X, Y, amount, marking, barcode)

    @classmethod
    def run(cls, blocks: list[Block]) -> DataChunk | None:
        print("=============================")
        filled_blocks = cls.fill_forward_materials(blocks)
        if not filled_blocks:
            return None
        # print("Fill forward material")
        # for block in filled_blocks:
        #     print(block.header.index)
        #     for irow, data_row in block.data.items():
        #         print(f"{irow}:", [(data.role.name, data.value) for data in data_row])

        valid_blocks = cls.valildate_blocks(filled_blocks)
        if not valid_blocks:
            return None
        # print("\n")
        # print("Valid blocks")
        # for block in valid_blocks:
        #     print(block.header.index, [spec.type.name for spec in block.header.specs])
        #     for irow, data_row in block.data.items():
        #         print(f"{irow}:", [(data.role.name, data.value) for data in data_row])

        chunks = cls.blocks_to_chunks(valid_blocks)
        if not chunks:
            return None
        print("\n")
        print("Chunks")
        for chunk in chunks:
            print("size:", chunk.nrows)
            print("material:", chunk.material)
            print("X:", chunk.X)
            print("Y:", chunk.Y)
            print("amount:", chunk.amount)
            print("marking:", chunk.marking)
            print("barcode:", chunk.barcode)
            print("---")
            print(chunk.unique_materials)
            print("===")

        main_chunk = merge_chunks(chunks)
        if main_chunk is None:
            return None
        print("\n")
        print("Main chunk")
        print("size:", main_chunk.nrows)
        print("material:", main_chunk.material)
        print("X:", main_chunk.X)
        print("Y:", main_chunk.Y)
        print("amount:", main_chunk.amount)
        print("marking:", main_chunk.marking)
        print("barcode:", main_chunk.barcode)
        print("---")
        print(main_chunk.unique_materials)
        print("===")

        return main_chunk
