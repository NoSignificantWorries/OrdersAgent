from .annotate import Annotation
from .sparse_table import SparseTable


class Assembler:
    def __init__(self, table: SparseTable, annotation: Annotation) -> None:
        self.table: SparseTable = table
        self.annotation: Annotation = annotation

    def build_groups(self) -> None:
        for r, c, cell in self.table.iter_cells():
            ann = self.annotation.get_cell(r, c)
            if ann:
                print(ann, cell)
