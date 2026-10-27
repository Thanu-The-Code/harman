import React, { useEffect, useRef, useState } from 'react';
import { saveAs } from 'file-saver';

const pct = (v) => `${(v * 100).toFixed(3)}%`;

function boxStyle(b) {
  return {
    left: pct(b[0]), top: pct(b[1]), width: pct(b[2] - b[0]), height: pct(b[3] - b[1]),
  };
}

function useWidth(ref) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => setWidth(el.clientWidth);
    measure();
    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(measure);
      ro.observe(el);
      return () => ro.disconnect();
    }
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [ref]);
  return width;
}

function Page({ page, mode }) {
  const ref = useRef(null);
  const width = useWidth(ref);
  const height = width * (page.height / page.width);
  // Text size follows its box, capped near the page's typical line so a tall box (a merged
  // cell, a multi-line block) does not blow its text up; long text wraps inside its box.
  const heights = page.lines.map(l => l.bbox[3] - l.bbox[1]).sort((a, b) => a - b);
  const typical = heights.length ? heights[Math.floor(heights.length / 2)] : 0.02;
  const fontSize = (l) => {
    if (l.size) return Math.max(6, l.size * height); // spreadsheet cells carry their real font size
    const rows = Math.max(1, (l.text.match(/\n/g) || []).length + 1);
    const box = (l.bbox[3] - l.bbox[1]) / rows;
    return Math.max(6, Math.min(box, typical * 1.8) * height * 0.72);
  };
  const digital = mode === 'digital';

  return (
    <div ref={ref} className={`ocr-page ${digital ? 'ocr-page-digital' : ''} ${page.image ? '' : 'ocr-page-sheet'}`} style={{ paddingTop: pct(page.height / page.width) }}>
      <div className="ocr-page-inner">
        {!digital && page.image && <img src={page.image} alt={`Page ${page.index + 1}`} className="ocr-page-image" />}
        {page.tables.map((t, i) => (
          <React.Fragment key={`t${i}`}>
            <div className="ocr-box ocr-box-table" style={boxStyle(t.bbox)} title={`Table ${t.n_rows} x ${t.n_cols}`} />
            {digital && t.cells.map((c, k) => <div key={k} className="ocr-cell" style={boxStyle(c.bbox)} />)}
          </React.Fragment>
        ))}
        {page.lines.map((l, i) => (
          digital ? (
            <div
              key={`l${i}`}
              className="ocr-text"
              style={{ ...boxStyle(l.bbox), fontSize: `${fontSize(l)}px` }}
              title={`${Math.round(l.conf * 100)}%`}
            >
              {l.text}
            </div>
          ) : (
            <div key={`l${i}`} className={`ocr-box ocr-box-line ${l.conf < 0.6 ? 'ocr-low' : ''}`} style={boxStyle(l.bbox)} title={`${l.text} (${Math.round(l.conf * 100)}%)`} />
          )
        ))}
        {page.checkboxes.map((c, i) => (
          <div
            key={`c${i}`}
            className={`ocr-box ocr-box-check ${c.checked ? 'is-checked' : ''} ${c.kind === 'radio' ? 'is-radio' : ''}`}
            style={boxStyle(c.bbox)}
            title={c.checked ? 'Ticked' : 'Empty'}
          >
            {digital && c.checked && <i className="fas fa-check" />}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Shows an OCR'd document: the scan with detected text / boxes / tables outlined,
 * a re-typeset "digital copy" with text at its original positions, or plain text.
 */
export default function OcrDocumentView({ document: doc, defaultMode = 'overlay' }) {
  const [pageIndex, setPageIndex] = useState(0);
  const [mode, setMode] = useState(defaultMode);
  if (!doc || !doc.pages || !doc.pages.length) return null;
  const page = doc.pages[Math.min(pageIndex, doc.pages.length - 1)];
  // Excel sheets have no page image: show the re-typeset copy instead of an empty overlay.
  const hasImage = doc.pages.some(p => p.image);
  const shown = mode === 'overlay' && !hasImage ? 'digital' : mode;

  const download = () => {
    saveAs(new Blob([doc.text], { type: 'text/plain;charset=utf-8' }), 'document.txt');
  };
  const copy = () => {
    if (navigator.clipboard) navigator.clipboard.writeText(doc.text);
  };

  const modes = [['overlay', 'Scan + detected'], ['digital', 'Digital copy'], ['text', 'Text']].filter(([key]) => hasImage || key !== 'overlay');
  return (
    <div className="ocr-document">
      <div className="d-flex align-items-center mb-2 flex-wrap">
        <div className="btn-group btn-group-sm mr-3" role="group">
          {modes.map(([key, name]) => (
            <button key={key} type="button" className={`btn ${shown === key ? 'btn-secondary' : 'btn-outline-secondary'}`} onClick={() => setMode(key)}>{name}</button>
          ))}
        </div>
        {doc.pages.length > 1 && (
          <select className="form-control form-control-sm w-auto mr-3" value={pageIndex} onChange={(e) => setPageIndex(Number(e.target.value))}>
            {doc.pages.map((p) => <option key={p.index} value={p.index}>{p.sheet ? `Sheet: ${p.sheet}` : `Page ${p.index + 1}`}</option>)}
          </select>
        )}
        <button type="button" className="btn btn-sm btn-outline-primary mr-2" onClick={download}><i className="fas fa-download" /> .txt</button>
        <button type="button" className="btn btn-sm btn-outline-primary" onClick={copy}><i className="fas fa-copy" /> Copy text</button>
      </div>
      {shown === 'text' ? <pre className="ocr-plain-text">{doc.text}</pre> : <Page page={page} mode={shown} />}
      {shown === 'overlay' && (
        <small className="text-muted">
          <span className="ocr-legend ocr-box-line" /> text
          <span className="ocr-legend ocr-box-check" /> tick box
          <span className="ocr-legend ocr-box-check is-checked" /> ticked
          <span className="ocr-legend ocr-box-table" /> table
          <span className="ocr-legend ocr-box-line ocr-low" /> low confidence
        </small>
      )}
    </div>
  );
}
