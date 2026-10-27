"""Which OCR tests run.

- Excel, the format registry and the HTTP layer: always (seconds).
- OpenCV-only tests (page rendering, ruling-line detection): when requirements-ocr.txt is installed.
- Tests that run PaddleOCR on whole scans (minutes on a CPU): only with RUN_OCR_TESTS=1.

    RUN_OCR_TESTS=1 python -m pytest tests/ocr -q
"""
import importlib.util
import os

import pytest

HAS_CV2 = importlib.util.find_spec("cv2") is not None
HAS_PADDLE = importlib.util.find_spec("paddleocr") is not None
RUN_ENGINE = os.environ.get("RUN_OCR_TESTS") == "1"

# modules that import the raster pipeline (OpenCV) at import time
RASTER_MODULES = ["test_loader.py", "test_shapes.py", "test_pipeline.py", "test_corpus.py",
                  "test_client_scans.py", "test_read_form.py"]
ENGINE_MODULES = {"test_client_scans", "test_corpus", "test_pipeline"}
ENGINE_TESTS = ("test_filled_scan_reads_back",)

collect_ignore = [] if HAS_CV2 else RASTER_MODULES


def pytest_collection_modifyitems(config, items):
    reason = ("runs PaddleOCR on whole pages (minutes): set RUN_OCR_TESTS=1"
              if HAS_PADDLE else "needs requirements-ocr.txt (PaddleOCR)")
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        module = item.module.__name__.rsplit(".", 1)[-1]
        if (module in ENGINE_MODULES or item.name.startswith(ENGINE_TESTS)) and not (RUN_ENGINE and HAS_PADDLE):
            item.add_marker(skip)
