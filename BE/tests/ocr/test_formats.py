"""The format registry: routing uploads, enabling/disabling formats, capabilities, HTTP errors."""
import pytest
from fastapi.testclient import TestClient

from app.ocr.formats import (
    AVAILABLE, OCR_UNAVAILABLE, Digitizer, FormatHandler, UnsupportedFormat, UploadedFile, build_registry,
)


def test_routes_by_content_then_extension():
    if OCR_UNAVAILABLE:
        pytest.skip("PDF / image need requirements-ocr.txt")
    from .synthetic import draw_form, png_bytes  # OpenCV

    reg = build_registry()
    assert reg.resolve(UploadedFile(b"%PDF-1.7 ...", "scan.bin")).key == "pdf"
    assert reg.resolve(UploadedFile(png_bytes(draw_form()), "noext")).key == "image"
    assert reg.resolve(UploadedFile(b"PK\x03\x04 not a zip", "form.xlsx")).key == "excel"
    with pytest.raises(UnsupportedFormat):
        reg.resolve(UploadedFile(b"hello", "notes.txt"))


def test_formats_can_be_switched_off():
    if OCR_UNAVAILABLE:
        pytest.skip("PDF / image need requirements-ocr.txt")
    reg = build_registry("pdf,image")
    assert [h.key for h in reg.handlers()] == ["pdf", "image"]
    with pytest.raises(UnsupportedFormat):
        reg.resolve(UploadedFile(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "old.xls"))
    with pytest.raises(ValueError):
        build_registry("pdf,word")


def test_capabilities_are_declared_by_interfaces():
    class TextOnly(FormatHandler, Digitizer):
        key, label, extensions = "txt", "Text", (".txt",)

        def sniff(self, data):
            return False

        def digitize(self, file):
            return {"pages": [], "text": file.data.decode()}

    reg = build_registry("pdf")
    reg.register(TextOnly())
    up = UploadedFile(b"hello", "a.txt")
    assert reg.resolve(up, "digitize").digitize(up)["text"] == "hello"
    with pytest.raises(UnsupportedFormat):
        reg.resolve(up, "template")
    assert reg.get("txt").describe()["capabilities"] == ["digitize"]
    # PDF and image need requirements-ocr.txt; Excel is always there
    assert set(AVAILABLE) == ({"pdf", "image", "excel"} if OCR_UNAVAILABLE is None else {"excel"})


def test_http_errors():
    from .api_app import app

    client = TestClient(app)
    formats = client.get("/ocr/formats").json()["formats"]
    assert {f["key"] for f in formats} == set(AVAILABLE)
    assert ".xls" in next(f for f in formats if f["key"] == "excel")["extensions"]
    r = client.post("/ocr/template", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415 and "Supported" in r.json()["detail"]
    r = client.post("/ocr/template", files={"file": ("broken.xlsx", b"PK\x03\x04garbage", "application/octet-stream")})
    assert r.status_code == 400
    r = client.post("/ocr/template", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert r.status_code == 400
