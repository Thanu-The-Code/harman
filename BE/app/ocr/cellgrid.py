"""Format-neutral model of a ruled form: anchor cells with row/col spans.

Excel sheets map onto it exactly; OCR'd pages build it from detected ruling lines plus the
text found inside each cell. Everything that interprets forms works on this model only.
"""
from dataclasses import dataclass, field


@dataclass(eq=False)
class GridCell:
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    text: str = ""
    boxed: bool = True          # drawn with borders: an empty boxed cell is a place to write
    bbox: list = None           # page pixels [x0, y0, x1, y1]
    ref: str = None             # source address, e.g. Excel "F9" or "F9:H9"
    size: float = 0.0           # text height (pixels or points), for title detection
    bold: bool = False
    occupied: bool = False      # holds a tick box / picture rather than being blank
    image: dict = None          # {"src": data-url, "width": px, "height": px}
    lines: list = field(default_factory=list)  # OCR line indexes inside the cell
    text_bbox: list = None      # where the text sits inside the cell (OCR only)
    hint: dict = None           # what the source says about the input: {"element", "options"?, "strong"}
    options: list = field(default_factory=list)  # tick boxes in the cell: {"text", "checked", "kind", "source"}
    option_prefix: str = ""     # text before the first tick box ("Married:" in "Married: ☐ Yes ☐ No")
    computed: bool = False      # a calculated value (Excel formula): shown, never filled in

    @property
    def end_row(self):
        return self.row + self.rowspan

    @property
    def end_col(self):
        return self.col + self.colspan

    @property
    def is_blank(self):
        return not self.text.strip() and not self.occupied and self.image is None


class CellGrid:
    def __init__(self, cells, n_rows, n_cols):
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.cells = sorted(cells, key=lambda c: (c.row, c.col))
        self._cover = {}
        for cell in self.cells:
            for r in range(cell.row, cell.end_row):
                for c in range(cell.col, cell.end_col):
                    self._cover.setdefault((r, c), cell)

    def at(self, r, c):
        return self._cover.get((r, c))

    def row_anchors(self, r, c0=0, c1=None):
        c1 = self.n_cols if c1 is None else c1
        return [x for x in self.cells if x.row == r and c0 <= x.col < c1]

    def left_of(self, cell):
        return self.at(cell.row, cell.col - 1) if cell.col > 0 else None

    def right_of(self, cell):
        return self.at(cell.row, cell.end_col)

    def above(self, cell):
        return self.at(cell.row - 1, cell.col) if cell.row > 0 else None

    def below(self, cell):
        return self.at(cell.end_row, cell.col)
