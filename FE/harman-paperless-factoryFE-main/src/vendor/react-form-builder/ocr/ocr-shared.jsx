import React, { useEffect, useState } from 'react';
import {
  DEFAULT_FORMATS, acceptAttribute, describeFormats, formatsFor, isAcceptedFile,
} from './ocr-client';

export function OcrModal({
  title, onClose, children, footer,
}) {
  return (
    <div className="modal show d-block ocr-modal" role="dialog">
      <div className="modal-dialog modal-xl" role="document">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title">{title}</h5>
            <button type="button" className="close" aria-label="Close" onClick={onClose}>
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div className="modal-body">{children}</div>
          <div className="modal-footer">
            {footer}
            <button type="button" className="btn btn-default" onClick={onClose}>Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Formats the service has enabled for a capability; falls back to the defaults if unreachable. */
export function useFormats(client, capability) {
  const [formats, setFormats] = useState(formatsFor(DEFAULT_FORMATS, capability));
  useEffect(() => {
    let live = true;
    client.formats()
      .then(list => live && setFormats(formatsFor(list, capability)))
      .catch(() => {});
    return () => { live = false; };
  }, [client, capability]);
  return formats;
}

/** File chooser + action button with busy and error states. */
export function OcrFileAction({
  actionLabel, busyLabel, onRun, formats,
}) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const allowed = formats || DEFAULT_FORMATS;

  const choose = (e) => {
    const f = e.target.files && e.target.files[0];
    setError(null);
    if (f && !isAcceptedFile(f, allowed)) {
      setFile(null);
      setError(`Please choose a supported file: ${describeFormats(allowed)}.`);
      return;
    }
    setFile(f || null);
  };

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await onRun(file);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ocr-file-action">
      <div className="form-row align-items-center">
        <div className="col">
          <input type="file" className="form-control-file" accept={acceptAttribute(allowed)} onChange={choose} disabled={busy} />
          <small className="form-text text-muted">Supported: {describeFormats(allowed)}</small>
        </div>
        <div className="col-auto">
          <button type="button" className="btn btn-primary" disabled={!file || busy} onClick={run}>
            {busy ? <><span className="spinner-border spinner-border-sm mr-2" role="status" />{busyLabel}</> : actionLabel}
          </button>
        </div>
      </div>
      {busy && <small className="form-text text-muted">Scans and PDFs are read with OCR and can take up to a minute per page; Excel files are read directly.</small>}
      {error && <div className="alert alert-danger mt-2 mb-0">{error}</div>}
    </div>
  );
}

export function ConfidenceBadge({ value }) {
  let cls = 'badge-success';
  if (value < 0.6) cls = 'badge-danger';
  else if (value < 0.85) cls = 'badge-warning';
  return <span className={`badge ${cls}`}>{Math.round(value * 100)}%</span>;
}
