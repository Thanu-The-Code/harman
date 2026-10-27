"""Draw a blank test form and a filled (shifted, rescaled) copy of it with known answers."""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "C:/Windows/Fonts/arial.ttf"
BOLD = "C:/Windows/Fonts/arialbd.ttf"
W, H = 1654, 2339  # A4 at 200 dpi

ANSWERS = {
    "Full Name": "Priya Sharma",
    "Email": "priya.sharma@example.com",
    "Date of Birth": "14/03/1992",
    "Phone": "9876543210",
    "Address": "221 MG Road, Pune",
    "Gender": "Female",
    "table": [["B.Tech", "2014", "Pune University"], ["MBA", "2017", "IIM Indore"]],
}


def _font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def draw_form(filled=False):
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f, small, title = _font(32), _font(30), _font(54, bold=True)
    ink = (20, 20, 20)
    pen = (20, 40, 160)

    d.text((W // 2, 140), "EMPLOYEE REGISTRATION FORM", font=title, fill=ink, anchor="mm")

    # Underline field
    d.text((150, 300), "Full Name:", font=f, fill=ink)
    d.line((340, 338, 1500, 338), fill=ink, width=3)
    # Boxed field
    d.text((150, 420), "Email:", font=f, fill=ink)
    d.rectangle((340, 405, 1500, 465), outline=ink, width=3)
    # Two fields on one row
    d.text((150, 560), "Date of Birth:", font=f, fill=ink)
    d.line((380, 598, 780, 598), fill=ink, width=3)
    d.text((880, 560), "Phone:", font=f, fill=ink)
    d.line((1010, 598, 1500, 598), fill=ink, width=3)
    # Checkboxes
    d.text((150, 680), "Gender:", font=f, fill=ink)
    for x, label in ((340, "Male"), (560, "Female")):
        d.rectangle((x, 682, x + 34, 716), outline=ink, width=3)
        d.text((x + 50, 680), label, font=f, fill=ink)
    # Tall box -> multi-line
    d.text((150, 800), "Address:", font=f, fill=ink)
    d.rectangle((340, 790, 1500, 960), outline=ink, width=3)
    # Table
    d.text((150, 1040), "Education Details", font=_font(36, bold=True), fill=ink)
    cols, top, row_h = [150, 600, 900, 1500], 1100, 70
    for r in range(4):
        d.line((cols[0], top + r * row_h, cols[-1], top + r * row_h), fill=ink, width=3)
    for x in cols:
        d.line((x, top, x, top + 3 * row_h), fill=ink, width=3)
    for c, head in enumerate(("Degree", "Year", "University")):
        d.text((cols[c] + 15, top + 18), head, font=f, fill=ink)
    # Signature
    d.text((150, 1500), "Signature:", font=f, fill=ink)
    d.line((340, 1538, 900, 1538), fill=ink, width=3)

    if filled:
        a = ANSWERS
        d.text((360, 296), a["Full Name"], font=small, fill=pen)
        d.text((360, 418), a["Email"], font=small, fill=pen)
        d.text((400, 556), a["Date of Birth"], font=small, fill=pen)
        d.text((1030, 556), a["Phone"], font=small, fill=pen)
        d.text((360, 805), a["Address"], font=small, fill=pen)
        x = 560
        d.line((x + 6, 700, x + 15, 711), fill=pen, width=5)
        d.line((x + 15, 711, x + 30, 686), fill=pen, width=5)
        for r, row in enumerate(a["table"]):
            for c, val in enumerate(row):
                d.text((cols[c] + 15, top + (r + 1) * row_h + 18), val, font=small, fill=pen)
        d.line((360, 1520, 420, 1490), fill=pen, width=4)
        d.line((420, 1490, 470, 1525), fill=pen, width=4)
        d.line((470, 1525, 560, 1495), fill=pen, width=4)

    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    if filled:
        # Simulate a different scan: 92% scale, shifted, slightly rotated.
        m = cv2.getRotationMatrix2D((W / 2, H / 2), 0.8, 0.92)
        m[0, 2] += 35
        m[1, 2] += 60
        arr = cv2.warpAffine(arr, m, (W, H), borderValue=(255, 255, 255))
    return arr


def png_bytes(arr):
    ok, buf = cv2.imencode(".png", arr)
    assert ok
    return buf.tobytes()
