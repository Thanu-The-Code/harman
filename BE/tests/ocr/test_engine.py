"""The OCR engine's thread and its retry (no models are loaded here)."""
import threading

import pytest

from app.ocr import engine


def test_a_failing_page_is_retried_once_with_the_models_rebuilt(monkeypatch):
    monkeypatch.setattr(engine, "_ocr", object())
    calls = []

    def flaky():
        calls.append(engine._ocr)
        if len(calls) == 1:
            raise RuntimeError("Unknown exception")  # what Paddle raised on the client's scan
        return "page"

    assert engine._on_engine_thread(engine._with_retry, flaky) == "page"
    assert len(calls) == 2 and calls[1] is None  # the second try rebuilds the model


def test_a_page_that_fails_twice_is_reported_as_an_engine_error():
    def broken():
        raise RuntimeError("Unknown exception")

    with pytest.raises(engine.EngineError, match="could not read this document"):
        engine._on_engine_thread(engine._with_retry, broken)


def test_everything_runs_on_one_engine_thread():
    names = {engine._on_engine_thread(lambda: threading.current_thread().name) for _ in range(5)}
    assert len(names) == 1 and next(iter(names)).startswith("ocr-engine")
