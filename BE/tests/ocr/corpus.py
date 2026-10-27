"""A harder, two-page test form plus scan degradations, for end-to-end evaluation.

Form: bank account opening. Page 1 has a ruled key/value grid, per-letter PAN boxes, round radio
buttons, a 2x2 checkbox grid, a "Label:" field with no line, and two underlined fields on one row.
Page 2 has a nominee table, a declaration paragraph, Place/Date, and a signature line with its
label underneath. Filled copies use a handwriting-style font.
"""
import io

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1654, 2339
FONTS = "C:/Windows/Fonts/"
INK = (25, 25, 25)
PEN = (20, 45, 150)

FILLED = {
    "Applicant Name": "Rahul Verma",
    "Date of Birth": "23/07/1988",
    "Father's Name": "Suresh Verma",
    "Nationality": "Indian",
    "Mobile No.": "9123456780",
    "Email ID": "rahul.v@mail.com",
    "Occupation": "Engineer",
    "Annual Income": "8,50,000",
    "PAN Number": "ABCPV1234K",
    "Account Type": "Current",
    "Services Required": ["Debit Card", "Net Banking"],
    "Residential Address": "12 Park Street, Kolkata",
    "City": "Kolkata",
    "PIN Code": "700016",
    "Nominee Details": [["Anita Verma", "Spouse", "34", "60"], ["Rohan Verma", "Son", "8", "40"], ["", "", "", ""]],
    "Place": "Kolkata",
    "Date": "15/01/2025",
}

# What a correct extraction returns for each field (after type conversion).
EXPECTED = {
    "Applicant Name": "Rahul Verma",
    "Date of Birth": "07/23/1988",
    "Father's Name": "Suresh Verma",
    "Nationality": "Indian",
    "Mobile No.": "9123456780",
    "Email ID": "rahul.v@mail.com",
    "Occupation": "Engineer",
    "Annual Income": "850000",
    "PAN Number": "ABCPV1234K",
    "Account Type": ["Current"],
    "Services Required": ["Debit Card", "Net Banking"],
    "Residential Address": "12 Park Street, Kolkata",
    "City": "Kolkata",
    "PIN Code": "700016",
    "Nominee Details": FILLED["Nominee Details"],
    "Place": "Kolkata",
    "Date": "01/15/2025",
    "Signature of Applicant": "<image>",
}

EXPECTED_TYPES = {
    "Applicant Name": "TextInput",
    "Date of Birth": "DatePicker",
    "Father's Name": "TextInput",
    "Nationality": "TextInput",
    "Mobile No.": "PhoneNumber",
    "Email ID": "EmailInput",
    "Occupation": "TextInput",
    "Annual Income": "NumberInput",
    "PAN Number": "TextInput",
    "Account Type": "RadioButtons",
    "Services Required": "Checkboxes",
    "Residential Address": "TextArea",
    "City": "TextInput",
    "PIN Code": "TextInput",
    "Nominee Details": "Table",
    "Place": "TextInput",
    "Date": "DatePicker",
    "Signature of Applicant": "Signature",
}


def font(name, size):
    return ImageFont.truetype(FONTS + name, size)


def _page1(d, filled, hand):
    f, small = font("arial.ttf", 30), font("arial.ttf", 25)
    d.text((W // 2, 110), "SAVINGS ACCOUNT OPENING FORM", font=font("arialbd.ttf", 50), fill=INK, anchor="mm")
    d.text((120, 175), "Please fill in BLOCK LETTERS. Fields marked with an asterisk are mandatory.", font=small, fill=INK)
    d.text((120, 212), "Attach a self-attested copy of your identity proof with this form.", font=small, fill=INK)
    d.text((120, 290), "1. Personal Details", font=font("arialbd.ttf", 34), fill=INK)

    cols, rows = [120, 400, 830, 1080, 1540], [350, 430, 510, 590, 670]
    for y in rows:
        d.line((cols[0], y, cols[-1], y), fill=INK, width=3)
    for x in cols:
        d.line((x, rows[0], x, rows[-1]), fill=INK, width=3)
    grid = [("Applicant Name", "Date of Birth"), ("Father's Name", "Nationality"), ("Mobile No.", "Email ID"), ("Occupation", "Annual Income")]
    for r, (a, b) in enumerate(grid):
        y = rows[r] + 24
        d.text((cols[0] + 12, y), a, font=f, fill=INK)
        d.text((cols[2] + 12, y), b, font=f, fill=INK)
        if filled:
            d.text((cols[1] + 14, y - 4), FILLED[a], font=hand, fill=PEN)
            d.text((cols[3] + 14, y - 4), FILLED[b], font=hand, fill=PEN)

    d.text((120, 742), "PAN Number", font=f, fill=INK)
    for i in range(10):
        x = 420 + i * 54
        d.rectangle((x, 730, x + 50, 780), outline=INK, width=3)
        if filled:
            d.text((x + 25, 755), FILLED["PAN Number"][i], font=hand, fill=PEN, anchor="mm")

    d.text((120, 842), "Account Type:", font=f, fill=INK)
    for x, label in ((420, "Savings"), (700, "Current"), (980, "Fixed Deposit")):
        d.ellipse((x, 845, x + 34, 879), outline=INK, width=3)
        d.text((x + 48, 842), label, font=f, fill=INK)
        if filled and label == FILLED["Account Type"]:
            d.ellipse((x + 9, 854, x + 25, 870), fill=PEN)

    d.text((120, 942), "Services Required:", font=f, fill=INK)
    for (x, y), label in (((420, 945), "Debit Card"), ((800, 945), "Cheque Book"), ((420, 1015), "Net Banking"), ((800, 1015), "SMS Alerts")):
        d.rectangle((x, y, x + 34, y + 34), outline=INK, width=3)
        d.text((x + 48, y - 3), label, font=f, fill=INK)
        if filled and label in FILLED["Services Required"]:
            d.line((x + 5, y + 5, x + 29, y + 29), fill=PEN, width=5)
            d.line((x + 29, y + 5, x + 5, y + 29), fill=PEN, width=5)

    d.text((120, 1110), "Residential Address:", font=f, fill=INK)
    d.text((120, 1210), "City:", font=f, fill=INK)
    d.line((230, 1246, 760, 1246), fill=INK, width=3)
    d.text((860, 1210), "PIN Code:", font=f, fill=INK)
    d.line((1020, 1246, 1540, 1246), fill=INK, width=3)
    if filled:
        d.text((480, 1104), FILLED["Residential Address"], font=hand, fill=PEN)
        d.text((260, 1200), FILLED["City"], font=hand, fill=PEN)
        d.text((1050, 1200), FILLED["PIN Code"], font=hand, fill=PEN)


def _page2(d, filled, hand):
    f = font("arial.ttf", 30)
    d.text((120, 120), "2. Nominee Details", font=font("arialbd.ttf", 34), fill=INK)
    cols, top, rh = [120, 620, 960, 1180, 1540], 180, 70
    for r in range(5):
        d.line((cols[0], top + r * rh, cols[-1], top + r * rh), fill=INK, width=3)
    for x in cols:
        d.line((x, top, x, top + 4 * rh), fill=INK, width=3)
    for c, head in enumerate(("Nominee Name", "Relationship", "Age", "Share (%)")):
        d.text((cols[c] + 12, top + 18), head, font=f, fill=INK)
    if filled:
        for r, row in enumerate(FILLED["Nominee Details"]):
            for c, val in enumerate(row):
                if val:
                    d.text((cols[c] + 14, top + (r + 1) * rh + 12), val, font=hand, fill=PEN)

    d.text((120, 520), "Declaration", font=font("arialbd.ttf", 34), fill=INK)
    for i, line in enumerate((
        "I hereby declare that the information given above is true and correct to the best",
        "of my knowledge. I agree to abide by the terms and conditions of the bank as",
        "amended from time to time.",
    )):
        d.text((120, 580 + i * 40), line, font=font("arial.ttf", 27), fill=INK)

    d.text((120, 780), "Place:", font=f, fill=INK)
    d.line((230, 816, 700, 816), fill=INK, width=3)
    d.text((860, 780), "Date:", font=f, fill=INK)
    d.line((960, 816, 1400, 816), fill=INK, width=3)
    d.line((120, 980, 620, 980), fill=INK, width=3)
    d.text((120, 995), "Signature of Applicant", font=f, fill=INK)
    if filled:
        d.text((260, 770), FILLED["Place"], font=hand, fill=PEN)
        d.text((990, 770), FILLED["Date"], font=hand, fill=PEN)
        pts = [(160, 965), (200, 920), (230, 960), (270, 925), (300, 962), (360, 930), (420, 958)]
        d.line(pts, fill=PEN, width=4)


def draw(filled=False, hand_font="Inkfree.ttf", hand_size=34):
    hand = font(hand_font, hand_size)
    pages = []
    for painter in (_page1, _page2):
        img = Image.new("RGB", (W, H), "white")
        painter(ImageDraw.Draw(img), filled, hand)
        pages.append(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
    return pages


# ---- scan degradations ----------------------------------------------------------------

def _warp(img, angle, scale, dx, dy):
    m = cv2.getRotationMatrix2D((W / 2, H / 2), angle, scale)
    m[0, 2] += dx
    m[1, 2] += dy
    return cv2.warpAffine(img, m, (img.shape[1], img.shape[0]), borderValue=(255, 255, 255))


def _jpeg(img, q):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def degrade(img, kind, seed=0):
    rng = np.random.default_rng(seed)
    if kind == "clean":
        return img
    if kind == "jpeg30":
        return _jpeg(img, 30)
    if kind == "skewed":
        return _warp(img, 2.5, 0.9, 60, 90)
    if kind == "blur_noise":
        out = cv2.GaussianBlur(img, (5, 5), 1.3).astype(np.int16)
        out += rng.normal(0, 14, out.shape).astype(np.int16)
        return np.clip(out, 0, 255).astype(np.uint8)
    if kind == "lowres_150dpi":
        small = cv2.resize(img, (int(W * 0.75), int(H * 0.75)), interpolation=cv2.INTER_AREA)
        return _jpeg(small, 60)
    if kind == "phone_photo":
        # Uneven lighting, slight perspective, grey paper, noise, JPEG.
        src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        dst = np.float32([[40, 30], [W - 25, 60], [W - 60, H - 20], [20, H - 50]])
        out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (W, H), borderValue=(200, 200, 200))
        yy, xx = np.mgrid[0:H, 0:W]
        light = 0.72 + 0.28 * (xx / W) * (1 - 0.4 * yy / H)
        out = (out.astype(np.float32) * light[..., None] * np.array([0.93, 0.97, 1.0])).astype(np.int16)
        out += rng.normal(0, 8, out.shape).astype(np.int16)
        return _jpeg(np.clip(out, 0, 255).astype(np.uint8), 55)
    if kind == "faded":
        out = img.astype(np.float32) * 0.45 + 140
        return np.clip(out, 0, 255).astype(np.uint8)
    raise ValueError(kind)


KINDS = ["clean", "jpeg30", "skewed", "blur_noise", "lowres_150dpi", "phone_photo", "faded"]


def to_pdf(pages):
    buf = io.BytesIO()
    imgs = [Image.fromarray(cv2.cvtColor(p, cv2.COLOR_BGR2RGB)) for p in pages]
    imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:], resolution=200)
    return buf.getvalue()


def to_jpg(img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()
