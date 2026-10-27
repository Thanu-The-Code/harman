"""Turn an uploaded PDF / JPEG / PNG into a list of BGR page images."""
import cv2
import numpy as np
import pypdfium2 as pdfium

from .errors import UnsupportedFile  # noqa: F401  (re-exported for callers)

PDF_DPI = 200
MAX_PAGES = 20
MAX_SIDE = 3000


def _is_pdf(data, filename):
    return data[:5] == b"%PDF-" or filename.lower().endswith(".pdf")


def _is_image(data, filename):
    name = filename.lower()
    magic_png = data[:8] == b"\x89PNG\r\n\x1a\n"
    magic_jpg = data[:3] == b"\xff\xd8\xff"
    return magic_png or magic_jpg or name.endswith((".png", ".jpg", ".jpeg"))


def _limit_size(img):
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def pdf_pages(data):
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise UnsupportedFile(f"Could not read PDF: {exc}") from exc
    pages = []
    try:
        for i in range(min(len(pdf), MAX_PAGES)):
            bitmap = pdf[i].render(scale=PDF_DPI / 72)
            arr = bitmap.to_numpy()
            mode = bitmap.mode
            if arr.ndim == 2:
                arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            elif mode == "BGRA" or (arr.shape[2] == 4 and mode != "RGBA"):
                arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            elif mode == "RGBA":
                arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            elif mode == "RGB":
                arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            pages.append(_limit_size(np.ascontiguousarray(arr)))
    finally:
        pdf.close()
    if not pages:
        raise UnsupportedFile("PDF has no pages")
    return pages


def image_pages(data):
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise UnsupportedFile("Could not decode image")
    return [_limit_size(img)]


def load_pages(data: bytes, filename: str = ""):
    if not data:
        raise UnsupportedFile("Empty file")
    filename = filename or ""
    if _is_pdf(data, filename):
        return pdf_pages(data)
    if _is_image(data, filename):
        return image_pages(data)
    raise UnsupportedFile("Only PDF, JPG, JPEG and PNG files are supported")


def _profile_score(binary, angle):
    h, w = binary.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rows = cv2.warpAffine(binary, m, (w, h), flags=cv2.INTER_NEAREST).sum(axis=1, dtype=np.float64)
    return float(np.var(rows))


def skew_angle(img, max_angle=5.0):
    """Rotation (degrees, OpenCV convention) that makes text rows and rules horizontal.

    Projection-profile search on a downscaled page: the right angle gives the sharpest row
    profile. Works on photos and JPEG scans where thin lines are too broken for line detection.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    scale = 1000.0 / max(gray.shape)
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    binary = cv2.adaptiveThreshold(small, 1, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    best = max(np.arange(-max_angle, max_angle + 1e-6, 0.25), key=lambda a: _profile_score(binary, a))
    return float(max(np.arange(best - 0.25, best + 0.25 + 1e-6, 0.05), key=lambda a: _profile_score(binary, a)))


def deskew(img, max_angle=5.0):
    """Rotate small scan / photo skew away."""
    angle = skew_angle(img, max_angle)
    if abs(angle) < 0.1:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
