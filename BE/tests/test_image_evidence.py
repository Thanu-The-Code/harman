"""
A photographed or scanned sheet attached as a record's hard copy is kept as a PDF.

Approval signatures are stamped onto the record's document, which only works
on a PDF: a JPG attached as the hard copy left every review without its signed
preview and every filed record without signatures.
"""
import io
from datetime import datetime

from PIL import Image
from PyPDF2 import PdfReader

from app.services import signature_stamp as stamp
from app.services.evidence_service import _as_pdf


def _picture(path, size=(1240, 1754), dpi=None, frames=1):
    pages = [Image.new("RGB", size, (255, 255, 255)) for _ in range(frames)]
    kwargs = {"dpi": (dpi, dpi)} if dpi else {}
    if frames > 1:
        pages[0].save(path, save_all=True, append_images=pages[1:], **kwargs)
    else:
        pages[0].save(path, **kwargs)
    return path


def test_a_photo_becomes_an_a4_pdf(tmp_path):
    pdf = _as_pdf(_picture(tmp_path / "sheet.jpg"))  # a phone photo says nothing of its resolution
    page = PdfReader(str(pdf)).pages[0]
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    assert pdf.suffix == ".pdf"
    assert abs(height - 842) < 2 and abs(width - 595) < 2  # A4 in points


def test_a_scanners_resolution_is_kept_and_every_page_converted(tmp_path):
    pdf = _as_pdf(_picture(tmp_path / "sheet.tif", size=(1700, 2200), dpi=200, frames=2))
    reader = PdfReader(str(pdf))
    assert len(reader.pages) == 2
    assert abs(float(reader.pages[0].mediabox.width) - 1700 / 200 * 72) < 2  # 8.5 in


def test_signatures_can_be_stamped_on_the_converted_scan(tmp_path):
    pdf = _as_pdf(_picture(tmp_path / "sheet.png"))
    block = stamp.Block(signature_id="s1", name="Ravi Kumar", designation="Process Owner", signed_at=datetime(2026, 10, 24, 16, 46))
    signed = stamp.stamp(pdf.read_bytes(), [block], title="REC-1")
    assert signed[:4] == b"%PDF" and len(PdfReader(io.BytesIO(signed)).pages) >= 1


class _Settings:
    allowed_extensions_list = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp", "txt", "md"]


def test_a_hard_copy_is_a_scan_or_photo_not_any_document():
    from app.services.evidence_service import scan_refusal, scan_types

    assert scan_types(_Settings()) == ["pdf", "png", "jpg", "jpeg", "tiff", "bmp"]
    assert scan_refusal("REC-1.pdf", _Settings()) is None and scan_refusal("IMG_0042.JPG", _Settings()) is None
    for name in ("notes.txt", "Daily check sheet.xlsx", "sheet"):
        assert "cannot be the hard copy" in scan_refusal(name, _Settings())
