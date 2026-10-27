import React, { useMemo, useState } from 'react';
import store from '../stores/store';
import createOcrClient from './ocr-client';
import OcrDocumentView from './ocr-document-view';
import { OcrFileAction, OcrModal, useFormats } from './ocr-shared';
import ReviewTable, { ReviewSummary, defaultSelection, selectedAnswers } from './ocr-review';
import { loadIntoBuilder } from './ocr-template-import';

function supports(formats, file, capability) {
  const name = (file.name || '').toLowerCase();
  const fmt = formats.find(f => (f.extensions || []).some(ext => name.endsWith(ext)));
  return !!fmt && (fmt.capabilities || []).indexOf(capability) > -1;
}

/**
 * Requirement A.ii: digitize a document as-is, then optionally
 *   - "Edit as form": turn it into an editable form in the builder (onEditForm), or
 *   - "Fill in values": turn it into a form already filled with the values read from it,
 *     ready to review and change (onFillValues).
 * The document is read once; the form and its values come with the digitized copy.
 */
export default function OcrDigitize({
  baseUrl, onClose, onEditForm = loadIntoBuilder, onFillValues,
}) {
  const client = useMemo(() => createOcrClient(baseUrl), [baseUrl]);
  const formats = useFormats(client, 'digitize');
  const [result, setResult] = useState(null); // { document, task_data?, answers?, fields? }
  const [selected, setSelected] = useState({});
  const [showValues, setShowValues] = useState(false);
  const [mode, setMode] = useState('replace');
  const hasForm = (store.state.data || []).filter(Boolean).length > 0;

  const run = async (file) => {
    if (supports(formats, file, 'read_form')) {
      const res = await client.readForm(file);
      setResult(res);
      setSelected(defaultSelection(res));
    } else {
      setResult({ document: await client.digitize(file) });
    }
  };

  const asForm = result && result.task_data && result.task_data.length > 0;
  const chosenMode = hasForm ? mode : 'replace';
  const footer = asForm && (
    <>
      {hasForm && (
        <div className="mr-auto">
          <div className="custom-control custom-radio custom-control-inline">
            <input type="radio" id="dg-mode-replace" className="custom-control-input" checked={mode === 'replace'} onChange={() => setMode('replace')} />
            <label className="custom-control-label" htmlFor="dg-mode-replace">Replace current form</label>
          </div>
          <div className="custom-control custom-radio custom-control-inline">
            <input type="radio" id="dg-mode-append" className="custom-control-input" checked={mode === 'append'} onChange={() => setMode('append')} />
            <label className="custom-control-label" htmlFor="dg-mode-append">Add to current form</label>
          </div>
        </div>
      )}
      <button type="button" className="btn btn-outline-primary" onClick={() => { onEditForm(result.task_data, chosenMode); onClose(); }}>
        <i className="fas fa-edit"></i> Edit as form
      </button>
      {onFillValues && (
        <button type="button" className="btn btn-primary" onClick={() => onFillValues(result.task_data, selectedAnswers(result, selected), chosenMode, result)}>
          <i className="fas fa-pen"></i> Fill in values
        </button>
      )}
    </>
  );

  return (
    <OcrModal title="Digitize document" onClose={onClose} footer={footer}>
      <OcrFileAction formats={formats} actionLabel="Digitize" busyLabel="Reading document..." onRun={run} />
      {result && (
        <div className="mt-3">
          {asForm && (
            <div className="alert alert-info d-flex align-items-center flex-wrap">
              <span className="mr-auto">
                <ReviewSummary result={result} /> Use <b>Edit as form</b> to change the layout in the builder,
                or <b>Fill in values</b> to open it as a filled form you can correct.
              </span>
              <button type="button" className="btn btn-link btn-sm" onClick={() => setShowValues(!showValues)}>
                {showValues ? 'Hide' : 'Review'} values
              </button>
            </div>
          )}
          {asForm && showValues && <ReviewTable result={result} selected={selected} onSelect={setSelected} />}
          <OcrDocumentView document={result.document} defaultMode="digital" />
        </div>
      )}
    </OcrModal>
  );
}
