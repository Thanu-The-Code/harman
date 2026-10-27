import io

import pytest
from PIL import Image

from app.ocr.loader import UnsupportedFile, load_pages

from .synthetic import draw_form, png_bytes


def _pdf(pages):
    buf = io.BytesIO()
    imgs = [Image.fromarray(p[:, :, ::-1]) for p in pages]
    imgs[0].save(buf, format="PDF", save_all=True, append_images=imgs[1:], resolution=200)
    return buf.getvalue()


def test_pdf_pages_are_rendered():
    form = draw_form()
    pages = load_pages(_pdf([form, form]), "form.pdf")
    assert len(pages) == 2
    h, w = pages[0].shape[:2]
    assert abs(w - form.shape[1]) < 10 and abs(h - form.shape[0]) < 10
    assert pages[0].shape[2] == 3


def test_images_and_rejects():
    assert len(load_pages(png_bytes(draw_form()), "x.png")) == 1
    with pytest.raises(UnsupportedFile):
        load_pages(b"hello", "notes.txt")
    with pytest.raises(UnsupportedFile):
        load_pages(b"", "empty.png")
