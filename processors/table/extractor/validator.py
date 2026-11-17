from .pipeline import Block


class ValidatorPipeline:
    @classmethod
    def fill_forward_materials(cls, blocks: list[Block]) -> list[Block]:
        processed_blocks: list[Block] = []
        for block in blocks:
            if block.fill_forward_material():
                processed_blocks.append(block)
        return processed_blocks

    @classmethod
    def valildate_schemes(cls, blocks: list[Block]) -> list[Block]:
        ...

    @classmethod
    def run(cls, blocks: list[Block]) -> None:
        print("=============================")
        filled_blocks = cls.fill_forward_materials(blocks)
        print("Fill forward material")
        for block in filled_blocks:
            print(block.header.index)
            for irow, data_row in block.data.items():
                print(f"{irow}:", [(data.role.name, data.value) for data in data_row])

        cls.valildate_schemes(filled_blocks)
