from .annotate import Annotation, CellKind, TableShape
from .sparse_table import SparseTable


def build_sizes_header(table: SparseTable, annotation: Annotation) -> None:
    for cell_ann in annotation.cells



class Assembler:
    def __init__(self, table: SparseTable, annotation: Annotation) -> None:
        self.table: SparseTable = table
        self.annotation: Annotation = annotation
