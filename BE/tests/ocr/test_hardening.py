"""Limits against hostile/runaway files, and slow documents not blocking the service."""
import asyncio
import io
import time
import zipfile

import httpx
import openpyxl
import pytest

from app.ocr.formats import UnsupportedFile, UploadedFile, build_registry
from app.ocr.formats.base import Digitizer, FormatHandler
from app.ocr.formats.excel import workbook
from app.ocr.formats.registry import FormatRegistry


def _xlsx(build=None):
    wb = openpyxl.Workbook()
    wb.active["A1"] = "Name:"
    if build:
        build(wb.active)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_zip_bomb_is_refused():
    src = zipfile.ZipFile(io.BytesIO(_xlsx()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("xl/media/padding.bin", b"\0" * (64 * 1024 * 1024))  # 64 MB of zeros, ~64 KB zipped
    handler = build_registry("excel").get("excel")
    with pytest.raises(UnsupportedFile, match="malformed|expands"):
        handler.build_template(UploadedFile(out.getvalue(), "bomb.xlsx"))


def test_too_many_cells_is_refused(monkeypatch):
    monkeypatch.setattr(workbook, "MAX_CELLS", 500)
    data = _xlsx(lambda ws: [ws.cell(r, 1, r) for r in range(1, 1000)])
    with pytest.raises(UnsupportedFile, match="cells"):
        build_registry("excel").get("excel").build_template(UploadedFile(data, "big.xlsx"))


class SlowHandler(FormatHandler, Digitizer):
    key, label, extensions = "slow", "Slow", (".slow",)

    def sniff(self, data):
        return False

    def digitize(self, file):
        time.sleep(1.5)  # like OCR on a dense page
        return {"pages": [], "text": ""}


def test_slow_document_does_not_block_other_requests(monkeypatch):
    from app.routers import ocr as main

    from .api_app import app

    monkeypatch.setattr(main, "_registry", FormatRegistry([SlowHandler()]))

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            slow = asyncio.create_task(client.post("/ocr/digitize", files={"file": ("a.slow", b"x")}))
            await asyncio.sleep(0.2)
            start = time.time()
            health = await client.get("/ocr/formats")
            waited = time.time() - start
            assert (await slow).status_code == 200
            return health.status_code, waited

    status, waited = asyncio.run(scenario())
    assert status == 200 and waited < 1.0, waited
