from .annotate import Annotation, CellKind, CellRole, TableShape
from .sparse_table import SparseTable


def build_sizes_header(table: SparseTable, annotation: Annotation) -> None: ...


def find_header_rows(shape: TableShape) -> None:
    for idx, row in shape.rows.items():
        if row.is_header:
            print("Header in", idx)
            for run in row.runs:
                if run.role == CellRole.HEADER:
                    print("\t", run)
