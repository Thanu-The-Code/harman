#!/usr/bin/env python
"""
Draw a filled HARMAN inspection sheet, as a scan.

For demonstrating the hard-copy route (B3): a Process Owner photographs the
paper form they filled at the end of a shift, and the readings come back off it
matched to the format's own fields.

**The output is deliberately image-only.** A PDF generated the ordinary way
carries a text layer, and the engine chain reads that *before* it reaches
PaddleOCR - so a demo using one would prove nothing about OCR. This renders the
page to an image first, exactly as a scanner or a phone camera does, and wraps
that in the PDF. There is no text layer, so the OCR has to do real work.

The readings match the seeded QF-PQ-001 format field for field, so the
suggestions come back complete and the demo lands.

    python scripts/make_sample_sheet.py            # the standard pair
    python scripts/make_sample_sheet.py --fresh   # a new batch, to demo again

Writes, into the project root:

    harman-inspection-sheet.pdf        every reading within specification
    harman-inspection-sheet-nok.pdf    bore diameter out of specification

The second one is what shows the N-ok flag being raised to the Overall Process
Owner (B5), which is hard to demonstrate convincingly without a sheet that
actually fails.

No sheet can be the evidence for two records - the system refuses a hard copy it
has already filed, so nobody can quietly reuse one. That makes a second demo run
fail on the same files, which is what `--fresh` is for: it stamps a new batch
number, leaving every reading alone so the demo script still matches.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "frontend" / "ui" / "assets" / "brand" / "harman.png"

# A4 at 200 dpi - what a desk scanner produces, and enough resolution for the
# text detector to resolve the thin rules of a ruled form.
DPI = 200
WIDTH, HEIGHT = int(8.27 * DPI), int(11.69 * DPI)

INK = (28, 28, 32)
RULE = (70, 70, 78)
FADE = (110, 110, 118)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in (("arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf") if bold
                 else ("arial.ttf", "calibri.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_sheet(rows: list[tuple[str, str, str, str]], observations: str,
               nok: bool, batch: str) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    d = ImageDraw.Draw(image)

    h1, h2, body, small = font(38, True), font(23, True), font(23), font(20)
    left, right = 90, WIDTH - 90
    y = 80

    # ------------------------------------------------------------- letterhead
    if BRAND.exists():
        try:
            logo = Image.open(BRAND).convert("RGBA")
            logo.thumbnail((300, 90))
            image.paste(logo, (left, y), logo)
        except Exception:
            d.text((left, y + 20), "HARMAN", font=h1, fill=INK)
    else:
        d.text((left, y + 20), "HARMAN", font=h1, fill=INK)

    d.text((right - 430, y + 4), "IN-PROCESS DIMENSIONAL CHECK", font=h2, fill=INK)
    d.text((right - 430, y + 38), "Format: QF-PQ-001      Rev: 00", font=small, fill=INK)
    d.text((right - 430, y + 66), "Work Instruction: WI-PQ-014", font=small, fill=INK)

    y += 118
    d.line([(left, y), (right, y)], fill=RULE, width=3)

    # ------------------------------------------------------------ job details
    y += 26
    for line_left, line_right in (
        ("Plant: Chakan, Pune", "Part No: HRM-4471-A"),
        ("Line: CNC-3", f"Batch: {batch}"),
        ("Shift: A  (06:00 - 14:00)", "Date: 02-09-2026"),
    ):
        d.text((left, y), line_left, font=body, fill=INK)
        d.text((left + 620, y), line_right, font=body, fill=INK)
        y += 34

    # ----------------------------------------------------------- the readings
    y += 26
    widths = [470, 300, 240, 320]
    header = ("Characteristic", "Specification", "Reading", "Remark")
    row_h = 58

    def row(cells, at, header_row=False):
        x = left
        for index, cell in enumerate(cells):
            d.rectangle([x, at, x + widths[index], at + row_h],
                        outline=RULE, width=2)
            if header_row:
                d.rectangle([x + 2, at + 2, x + widths[index] - 2, at + row_h - 2],
                            fill=(238, 238, 242))
            colour = INK
            if index == 3 and cell.strip().upper().startswith("N"):
                colour = (150, 20, 20)
            d.text((x + 16, at + 17), cell,
                   font=(h2 if header_row else body), fill=colour)
            x += widths[index]

    row(header, y, header_row=True)
    y += row_h
    for entry in rows:
        row(entry, y)
        y += row_h

    # ---------------------------------------------------------- observations
    y += 40
    d.text((left, y), "Observations:", font=h2, fill=INK)
    y += 34
    for line in observations.split("\n"):
        d.text((left, y), line, font=body,
               fill=(150, 20, 20) if nok else INK)
        y += 32

    # -------------------------------------------------------------- sign-off
    y += 50
    d.line([(left, y), (right, y)], fill=RULE, width=2)
    y += 24
    d.text((left, y), "Filled by: R. Kumar", font=body, fill=INK)
    d.text((left + 620, y), "Date: 02-09-2026", font=body, fill=INK)
    y += 46
    d.text((left, y), "Signature: ______________________", font=body, fill=FADE)
    d.text((left + 620, y), "Verified by: ____________________", font=body, fill=FADE)

    d.text((left, HEIGHT - 90),
           "HARMAN International  ·  Quality Management System  ·  "
           "QF-PQ-001 Rev 00  ·  Page 1 of 1",
           font=small, fill=FADE)

    return image


def like_a_scan(image: Image.Image, seed: int) -> Image.Image:
    """
    Make it look photographed rather than printed.

    A demo that reads a pristine render proves less than one that reads a page
    which is slightly crooked, slightly grey and slightly soft - which is what
    every real sheet coming off a desk scanner looks like.
    """
    random.seed(seed)

    # A page is never quite square in the tray.
    image = image.rotate(random.uniform(-0.45, 0.45), resample=Image.BICUBIC,
                         fillcolor="white", expand=False)

    # Scanner glass and paper are not pure white.
    tint = Image.new("RGB", image.size, (250, 249, 246))
    image = Image.blend(image, tint, 0.16)

    # And the optics are never perfectly sharp.
    return image.filter(ImageFilter.GaussianBlur(0.4))


OK_ROWS = [
    ("Bore diameter (mm)", "24.90 - 25.10", "25.02", "OK"),
    ("Surface finish (Ra)", "max 1.6", "0.84", "OK"),
    ("Run-out (mm)", "max 0.05", "0.021", "OK"),
    ("Gauge serial", "-", "BG-4471", "Calibrated"),
    ("Operator", "-", "R. Kumar", ""),
]

NOK_ROWS = [
    ("Bore diameter (mm)", "24.90 - 25.10", "26.45", "N-OK"),
    ("Surface finish (Ra)", "max 1.6", "0.92", "OK"),
    ("Run-out (mm)", "max 0.05", "0.038", "OK"),
    ("Gauge serial", "-", "BG-4471", "Calibrated"),
    ("Operator", "-", "R. Kumar", ""),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Draw filled HARMAN inspection sheets for the OCR demo.")
    parser.add_argument(
        "--fresh", action="store_true",
        help="stamp a new batch number so the sheets count as new evidence. "
             "A sheet can only ever be attached to one record, so use this "
             "before demonstrating again.")
    args = parser.parse_args()

    # Same readings every time, so the demo script always matches. Only the
    # batch number moves - which is enough to make it a different sheet.
    batch = ("B-" + datetime.now().strftime("%d%m-%H%M") if args.fresh
             else "B-2609-14")

    sheets = [
        ("harman-inspection-sheet.pdf", OK_ROWS,
         "All readings within specification.\nNo abnormality noted during the shift.",
         False, 11),
        ("harman-inspection-sheet-nok.pdf", NOK_ROWS,
         "Bore diameter found oversize on the third part.\n"
         "Machine stopped, tool offset corrected, batch held for review.",
         True, 29),
    ]

    for name, rows, observations, nok, seed in sheets:
        page = like_a_scan(draw_sheet(rows, observations, nok, batch), seed)
        target = ROOT / name
        # Image-only: no text layer, so the OCR has to actually read it.
        page.save(target, "PDF", resolution=DPI)
        size_kb = target.stat().st_size / 1024
        print(f"  {name:<38} {page.width}x{page.height}px  {size_kb:.0f} KB")

    print(f"\nBatch on both sheets: {batch}")
    print("Both are image-only PDFs - no text layer - so attaching one really")
    print("does exercise the OCR. Use them in Fill Record -> Attach the scanned")
    print("hard copy.")
    if not args.fresh:
        print("\nA sheet can only be the evidence for one record. Before running")
        print("the demo a second time, run this again with --fresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
