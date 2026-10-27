import React, { useMemo, useState } from 'react';
import createOcrClient, {
  describeFormats, isAcceptedFile, recentSources, saveExport,
} from './ocr-client';
import { OcrFileAction, OcrModal, useFormats } from './ocr-shared';

function Report({ result }) {
  return (
    <div className="alert alert-success mt-3 mb-0">
      Saved <b>{result.filename}</b>: {result.written.length} value{result.written.length === 1 ? '' : 's'} written.
      {result.skipped.length > 0 && (
        <ul className="mb-0 mt-2">
          {result.skipped.map((s, i) => <li key={i}>{s.label}: not written ({s.reason})</li>)}
        </ul>
      )}
    </div>
  );
}

/**
 * Save the form's values into a document: the workbook the form was made from (remembered from this
 * session), or another copy of the same blank form. Only the value cells and tick boxes change;
 * formatting, logos, formulas and drop-down lists stay as they are.
 */
export default function OcrExport({
  baseUrl, data, answers, onClose,
}) {
  const client = useMemo(() => createOcrClient(baseUrl), [baseUrl]);
  const formats = useFormats(client, 'export');
  const source = recentSources().find(f => isAcceptedFile(f, formats));
  const [useSource, setUseSource] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const run = async (file) => {
    const res = await client.exportForm(file, data, answers);
    saveExport(res);
    setResult(res);
  };
  const runSource = async () => {
    setBusy(true);
    setError(null);
    try {
      await run(source);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!formats.length) {
    return (
      <OcrModal title="Save values to a document" onClose={onClose}>
        <div className="alert alert-warning mb-0">No enabled document format can be written back.</div>
      </OcrModal>
    );
  }
  const fromSource = source && useSource;
  return (
    <OcrModal title="Save values to a document" onClose={onClose}>
      <p className="text-muted">
        Writes the form&apos;s current values into the blank form&apos;s file ({describeFormats(formats)}) and downloads
        the filled copy. Formatting, logos, formulas, drop-down lists and check boxes stay as they are.
      </p>
      {source && (
        <div className="mb-3">
          <div className="custom-control custom-radio">
            <input type="radio" id="ex-source" className="custom-control-input" checked={useSource} onChange={() => setUseSource(true)} />
            <label className="custom-control-label" htmlFor="ex-source">Use <b>{source.name}</b> (opened in this session)</label>
          </div>
          <div className="custom-control custom-radio">
            <input type="radio" id="ex-other" className="custom-control-input" checked={!useSource} onChange={() => setUseSource(false)} />
            <label className="custom-control-label" htmlFor="ex-other">Choose another file</label>
          </div>
        </div>
      )}
      {fromSource ? (
        <>
          <button type="button" className="btn btn-success" disabled={busy} onClick={runSource}>
            {busy ? <><span className="spinner-border spinner-border-sm mr-2" role="status" />Saving...</> : <><i className="fas fa-download"></i> Download filled copy</>}
          </button>
          {error && <div className="alert alert-danger mt-2 mb-0">{error}</div>}
        </>
      ) : (
        <OcrFileAction formats={formats} actionLabel="Download filled copy" busyLabel="Saving..." onRun={run} />
      )}
      {result && <Report result={result} />}
    </OcrModal>
  );
}
