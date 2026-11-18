from collections import Counter
from dataclasses import dataclass, field

from table.annotate import CellKind

from .pipeline import Block
from .specs import HeaderSpec, HeaderType


@dataclass
class DataChunk:
    nrows: int = 0
    material: list[str] = field(default_factory=list[str])
    X: list[int] = field(default_factory=list[int])
    Y: list[int] = field(default_factory=list[int])
    amount: list[int] = field(default_factory=list[int])
    marking: list[int | str | None] = field(default_factory=list[int | str | None])
    barcode: list[int | str | None] = field(default_factory=list[int | str | None])

    @property
    def unique_materials(self) -> dict[str, int]:
        return Counter(self.material)

    def add_row(self, material: str, x: int, y: int, amount: int, marking: int | str | None = None, barcode: int | str | None = None) -> None:
        self.nrows += 1
        self.material.append(material)
        self.X.append(x)
        self.Y.append(y)
        self.amount.append(amount)
        self.marking.append(marking)
        self.barcode.append(barcode)


def merge_chunks(chunks: list[DataChunk]) -> DataChunk | None:
    if not chunks:
        return None
    if len(chunks) < 2:
        return chunks[0]
    new_chunk = DataChunk()
    for chunk in chunks:
        new_chunk.nrows += chunk.nrows
        new_chunk.material += chunk.material
        new_chunk.X += chunk.X
        new_chunk.Y += chunk.Y
        new_chunk.amount += chunk.amount
        new_chunk.marking += chunk.marking
        new_chunk.barcode += chunk.barcode
    return new_chunk


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

        chunk = DataChunk()
        for row in block.data.values():
            chunk.add_row(
                material=row[mat_index].value,
                x=row[x_index].value,
                y=row[y_index].value,
                amount=row[amount_index].value,
                marking=row[marking_index].value if is_marking else None,
                barcode=row[barcode_index].value if is_barcode else None
            )

        return chunk

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

        chunk = DataChunk()
        for row in block.data.values():
            x, y = row[sizes_index].value
            chunk.add_row(
                material=row[mat_index].value,
                x=x,
                y=y,
                amount=row[amount_index].value,
                marking=row[marking_index].value if is_marking else None,
                barcode=row[barcode_index].value if is_barcode else None,
            )

        return chunk

    @classmethod
    def _okna_format(cls, block: Block, material: str) -> DataChunk:
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

        chunk = DataChunk()
        for row in block.data.values():
            chunk.add_row(
                material=material,
                x=row[x_index].value,
                y=row[y_index].value,
                amount=row[amount_index].value,
                marking=row[marking_index].value if is_marking else None,
                barcode=row[barcode_index].value if is_barcode else None
            )
        return chunk

    @classmethod
    def build_okna_chunks(cls, blocks: list[Block]) -> DataChunk | None:
        total_chunks: list[DataChunk] = []
        last_material = None
        subchunks: list[DataChunk] = []
        for block in blocks:
            match block.header.specs[0].type:
                case HeaderType.OKNA_TOP:
                    if subchunks:
                        merged = merge_chunks(subchunks)
                        if not merged:
                            return None
                        total_chunks.append(merged)
                    mat_index = 0
                    for i, f in enumerate(block.header.fields):
                        if f.spec.kind == CellKind.NAME:
                            mat_index = i
                            break
                    last_material = block.data[next(iter(block.data.keys()))][mat_index].value
                    subchunks = []
                case HeaderType.OKNA_DATA:
                    if last_material:
                        subchunks.append(cls._okna_format(block, last_material))
                    else:
                        return None
                case _:
                    return None
        if subchunks:
            merged = merge_chunks(subchunks)
            if not merged:
                return None
            total_chunks.append(merged)
        return merge_chunks(total_chunks)

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
                    continue
        return chunks

    @classmethod
    def run(cls, blocks: list[Block]) -> DataChunk | None:
        # print("=============================")
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

        okna_chunk = cls.build_okna_chunks(valid_blocks)
        if okna_chunk:
            # print("\n")
            # print("Okna chunks")
            # print("size:", okna_chunk.nrows)
            # print("material:", okna_chunk.material)
            # print("X:", okna_chunk.X)
            # print("Y:", okna_chunk.Y)
            # print("amount:", okna_chunk.amount)
            # print("marking:", okna_chunk.marking)
            # print("barcode:", okna_chunk.barcode)
            # print("---")
            # print(okna_chunk.unique_materials)
            # print("===")
            return okna_chunk

        chunks = cls.blocks_to_chunks(valid_blocks)
        if not chunks:
            return None
        # print("\n")
        # print("Chunks")
        # for chunk in chunks:
        #     print("size:", chunk.nrows)
        #     print("material:", chunk.material)
        #     print("X:", chunk.X)
        #     print("Y:", chunk.Y)
        #     print("amount:", chunk.amount)
        #     print("marking:", chunk.marking)
        #     print("barcode:", chunk.barcode)
        #     print("---")
        #     print(chunk.unique_materials)
        #     print("===")

        main_chunk = merge_chunks(chunks)
        if main_chunk is None:
            return None
        # print("\n")
        # print("Main chunk")
        # print("size:", main_chunk.nrows)
        # print("material:", main_chunk.material)
        # print("X:", main_chunk.X)
        # print("Y:", main_chunk.Y)
        # print("amount:", main_chunk.amount)
        # print("marking:", main_chunk.marking)
        # print("barcode:", main_chunk.barcode)
        # print("---")
        # print(main_chunk.unique_materials)
        # print("===")

        return main_chunk
