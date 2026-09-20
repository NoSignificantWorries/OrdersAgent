from dataclasses import dataclass


@dataclass(slots=True)
class ReportCell:
    value: int | str | tuple[int, int] | None = None
    is_merged_parent: bool = False
    is_merged_child: bool = False
    group: str = "empty"

    def to_html(self) -> str:
        if self.value is None:
            fmt_val = "n/a"
        elif isinstance(self.value, tuple):
            fmt_val = f"{self.value[0]}x{self.value[1]}"
        else:
            fmt_val = self.value
        return f"<td data-group=\"{self.group}\">{fmt_val}</td>"


class TableReport:
    def __init__(self, name: str | None, origin_nrows: int, origin_ncols: int) -> None:
        self.name: str | None = name

        self.origin_nrows: int = origin_nrows
        self.origin_ncols: int = origin_ncols
        self.result_nrows: int = self.origin_nrows
        self.result_ncols: int = self.origin_ncols

        self.rows_match: dict[int, int] = {i: i for i in range(self.origin_nrows)}
        self.cols_match: dict[int, int] = {i: i for i in range(self.origin_ncols)}

        self.cells: list[list[ReportCell]] = [[ReportCell() for _ in range(self.origin_ncols)] for _ in range(self.origin_nrows)]

    def _match_row(self, row: int) -> int:
        return self.rows_match[row]

    def _match_col(self, col: int) -> int:
        return self.cols_match[col]

    def normilized_table(self, new_nrows: int, new_ncols: int, keeped_rows: list[int], keeped_cols: list[int]) -> None:
        self.rows_match = {i: r for i, r in enumerate(keeped_rows)}
        self.cols_match = {i: c for i, c in enumerate(keeped_cols)}
        self.result_nrows = new_nrows
        self.result_ncols = new_ncols

    def add_cell(self, row: int, col: int, cell: ReportCell, origin_coords: bool = True) -> None:
        if not origin_coords:
            row = self._match_row(row)
            col = self._match_col(col)
        self.cells[row][col] = cell

    def add_parent(self, row: int, col: int) -> None:
        self.cells[row][col].is_merged_parent = True

    def to_html(self) -> str:
        print(self.cells)
        rows = []
        for row in self.cells:
            row = "\n".join([cell.to_html() for cell in row])
            row = "<tr>\n" + row + "\n</tr>"
            rows.append(row)
        return "<table border=\"1\" class=\"grid\"><tbody>\n" + "\n".join(rows) + "\n</tbody></table>"


class WorkbookReport:
    def __init__(self, name: str | None, with_metadata: bool = True) -> None:
        self.name: str | None = name
        self.nsheets: int = 0
        self.with_metadata: bool = with_metadata

        self.sheets: list[TableReport] = []

    def add_sheet(self, name: str | None, nrows: int, ncols: int) -> None:
        self.sheets.append(TableReport(name, nrows, ncols))
        self.nsheets += 1

    def add_cell_on_last_sheet(self, row: int, col: int, value: int | str | tuple[int, int] | None, is_merged_child: bool, origin_coords: bool = True) -> None:
        self.sheets[-1].add_cell(row, col, ReportCell(value=value, is_merged_child=is_merged_child), origin_coords=origin_coords)

    def add_parent_on_last_sheet(self, row: int, col: int) -> None:
        self.sheets[-1].add_parent(row, col)

    def last_table_normalized(self, new_nrows: int, new_ncols: int, keeped_rows: list[int], keeped_cols: list[int]) -> None:
        self.sheets[-1].normilized_table(new_nrows, new_ncols, keeped_rows, keeped_cols)

    def to_html(self) -> str:
        content = f'''
        <!DOCTYPE html>
        <html lang="ru">
        <head>
        <meta charset="utf-8">
        <title>Parse Log \"{self.name}\"</title>'''

        content += """
        <style>
          table.grid { border-collapse: collapse; table-layout: fixed; width: 100%; font: 12px monospace; }
          table.grid th, table.grid td { border: 1px solid #999; padding: 3px 6px; vertical-align: top; }
          table.grid th { background: #f0f0f0; }
          .sheet[hidden] { display: none; }
          .tabs button.active { background: #2b6cb0; color: #fff; }
        </style>
        """

        content += "\n</head>\n<body>\n"

        content += "<div class=\"tabs\" id=\"tabs\">"
        for i, sheet in enumerate(self.sheets):
            if i == 0:
                content += f"<button class=\"active\" data-target=\"sheet-{i}\">{sheet.name} <span class=\"badge\">metainfo</span></button>\n"
            else:
                content += f"<button data-target=\"sheet-{i}\">{sheet.name} <span class=\"badge\">metainfo</span></button>\n"
        content += "\n</div>"

        for i, sheet in enumerate(self.sheets):
            content += f"<section class=\"sheet\" id=\"sheet-{i}\">"
            content += "\n" + sheet.to_html()
            content += "\n</section>\n"

        content += """
        <script>
          // переключение листов
          document.getElementById('tabs').addEventListener('click', e => {
            const btn = e.target.closest('button'); if (!btn) return;
            document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('active', b === btn));
            document.querySelectorAll('.sheet').forEach(s => s.hidden = s.id !== btn.dataset.target);
          });

          // фильтр по группам внутри листа
          document.querySelectorAll('.groups').forEach(box => {
            box.addEventListener('click', e => {
              const btn = e.target.closest('button'); if (!btn) return;
              box.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
              const table = box.parentElement.querySelector('table.grid');
              const f = btn.dataset.filter;
              if (f) table.setAttribute('data-filter', f);
              else table.removeAttribute('data-filter');
            });
          });
        </script>
        """

        content += "\n</body></html>"
        return content
