"""PaddleOCR wrapper: one shared pipeline, lines with per-character x positions.

Every model is created and run on one dedicated thread. Paddle keeps per-thread state
(oneDNN on CPU), and a predictor created on one thread and run from another - the web
server's worker threads take turns - fails now and then with "RuntimeError: Unknown
exception". The one thread also serialises OCR, which uses all CPU cores anyway. A page
that still fails is retried once with the models rebuilt; then EngineError says so.

Configuration (environment variables):
  OCR_DET_MODEL / OCR_REC_MODEL  model names (default: PP-OCRv5 mobile, ~6 s per A4 page on CPU)
  OCR_DEVICE                     "cpu" (default) or e.g. "gpu:0" with paddlepaddle-gpu installed
  OCR_MKLDNN                     "0" to disable oneDNN on CPU. Paddle 3.2+/3.3 on Windows crashes
                                 with oneDNN, which is why requirements-ocr.txt pins paddlepaddle 3.1.1.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from .document import make_line

DET_MODEL = os.environ.get("OCR_DET_MODEL", "PP-OCRv5_mobile_det")
REC_MODEL = os.environ.get("OCR_REC_MODEL", "en_PP-OCRv5_mobile_rec")
DEVICE = os.environ.get("OCR_DEVICE", "cpu")
MKLDNN = os.environ.get("OCR_MKLDNN", "1") == "1"

log = logging.getLogger("ocr")

_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr-engine")
_ocr = None
_rec = None


class EngineError(RuntimeError):
    """The OCR engine could not read a page, even with its models rebuilt."""


def settings():
    return {"det_model": DET_MODEL, "rec_model": REC_MODEL, "device": DEVICE, "mkldnn": MKLDNN, "ready": _ocr is not None}


def _on_engine_thread(fn, *args):
    return _thread.submit(fn, *args).result()


def _load_ocr():
    global _ocr
    if _ocr is None:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR

        _ocr = PaddleOCR(
            text_detection_model_name=DET_MODEL,
            text_recognition_model_name=REC_MODEL,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=DEVICE,
            enable_mkldnn=MKLDNN,
        )
    return _ocr


def _load_recognizer():
    """Recognition-only model for single-line crops (form cells): ~3x faster than detect+recognise."""
    global _rec
    if _rec is None:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import TextRecognition

        _rec = TextRecognition(model_name=REC_MODEL, device=DEVICE, enable_mkldnn=MKLDNN)
    return _rec


def _with_retry(run):
    """Run on the engine thread; after a failure rebuild the models and try once more."""
    global _ocr, _rec
    try:
        return run()
    except RuntimeError as exc:
        log.warning("OCR engine failed (%s); rebuilding the models and trying again", exc)
        _ocr = _rec = None
        try:
            return run()
        except RuntimeError as again:
            raise EngineError("The OCR engine could not read this document. Please try again.") from again


def get_ocr():
    return _on_engine_thread(_load_ocr)


def get_recognizer():
    return _on_engine_thread(_load_recognizer)


def warm_up():
    """Load both models in the background, so the first scan is not also the slowest."""
    _thread.submit(_load_ocr)
    _thread.submit(_load_recognizer)


def recognize_lines(crops):
    """[(text, score)] for tightly cropped single-line images, batched."""
    if not crops:
        return []
    results = _on_engine_thread(_with_retry, lambda: list(_load_recognizer().predict(crops, batch_size=32)))
    return [(r.get("rec_text") or "", float(r.get("rec_score") or 0.0)) for r in results]


def _words(text, tokens, regions):
    """Recognised words as [token, x0, x1]; None if they don't line up with the text."""
    if not tokens or not regions or "".join(tokens) != text or len(tokens) != len(regions):
        return None
    out = []
    for token, region in zip(tokens, regions):
        xs = [float(p[0]) for p in region]
        out.append([token, min(xs), max(xs)])
    return out


def _chars(words):
    """Spread each recognised word's characters evenly across that word's box."""
    if not words:
        return None
    chars = []
    for token, x0, x1 in words:
        step = (x1 - x0) / max(1, len(token))
        chars.extend([ch, x0 + i * step, x0 + (i + 1) * step] for i, ch in enumerate(token))
    return chars


def recognize(img):
    result = _on_engine_thread(_with_retry, lambda: _load_ocr().predict(img, return_word_box=True)[0])
    texts = result.get("rec_texts") or []
    scores = result.get("rec_scores") or []
    boxes = result.get("rec_boxes")
    words = result.get("text_word") or [None] * len(texts)
    regions = result.get("text_word_region") or [None] * len(texts)
    lines = []
    for i, text in enumerate(texts):
        if not text or not text.strip():
            continue
        x0, y0, x1, y1 = [float(v) for v in boxes[i]]
        w = _words(text, words[i], regions[i])
        lines.append(make_line(text, [x0, y0, x1, y1], scores[i], _chars(w), w))
    return lines
