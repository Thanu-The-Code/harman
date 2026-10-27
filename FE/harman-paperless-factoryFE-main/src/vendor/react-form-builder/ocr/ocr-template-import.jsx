import React, { useMemo, useState } from 'react';
import store from '../stores/store';
import createOcrClient from './ocr-client';
import OcrDocumentView from './ocr-document-view';
import { OcrFileAction, OcrModal, useFormats } from './ocr-shared';

/** Put generated elements into the builder's store, replacing or appending to the current form. */
export function loadIntoBuilder(taskData, mode = 'replace') {
  const current = mode === 'append' ? (store.state.data || []).filter(Boolean) : [];
  const merged = [...current, ...taskData];
  const top = merged.filter(x => !x.parentId);
  merged.forEach((x) => {
    if (x.parentId) {
      // eslint-disable-next-line no-param-reassign
      x.parentIndex = top.findIndex(p => p.id === x.parentId);
    }
  });
  store.dispatch('updateOrder', merged);
}

function summary(stats) {
  const parts = [
    [stats.field, 'input field'], [stats.choice, 'checkbox group'], [stats.table, 'table'], [stats.static, 'text block'],
    [stats.image, 'picture'],
  ].filter(([n]) => n);
  if (!parts.length) return 'Nothing recognisable was found.';
  return `Detected ${parts.map(([n, name]) => `${n} ${name}${n > 1 ? 's' : ''}`).join(', ')}.`;
}

/** Requirement B: upload an image/PDF of a form and turn it into editable builder elements. */
export default function OcrTemplateImport({ baseUrl, onClose, onImport = loadIntoBuilder }) {
  const client = useMemo(() => createOcrClient(baseUrl), [baseUrl]);
  const formats = useFormats(client, 'template');
  const [result, setResult] = useState(null);
  const [mode, setMode] = useState('replace');
  const hasForm = (store.state.data || []).filter(Boolean).length > 0;

  const apply = () => {
    onImport(result.task_data, hasForm ? mode : 'replace');
    onClose();
  };

  const footer = result && (
    <>
      {hasForm && (
        <div className="mr-auto">
          <div className="custom-control custom-radio custom-control-inline">
            <input type="radio" id="ocr-mode-replace" className="custom-control-input" checked={mode === 'replace'} onChange={() => setMode('replace')} />
            <label className="custom-control-label" htmlFor="ocr-mode-replace">Replace current form</label>
          </div>
          <div className="custom-control custom-radio custom-control-inline">
            <input type="radio" id="ocr-mode-append" className="custom-control-input" checked={mode === 'append'} onChange={() => setMode('append')} />
            <label className="custom-control-label" htmlFor="ocr-mode-append">Add to end of current form</label>
          </div>
        </div>
      )}
      <button type="button" className="btn btn-primary" onClick={apply} disabled={!result.task_data.length}>Load into form builder</button>
    </>
  );

  return (
    <OcrModal title="Create form from a document" onClose={onClose} footer={footer}>
      <p className="text-muted">
        Upload a blank (or filled) form as an Excel workbook, PDF or image. Text, labels, input lines and boxes,
        checkboxes and tables (with merged cells and multi-row headings) become editable form elements.
      </p>
      <OcrFileAction formats={formats} actionLabel="Convert" busyLabel="Analysing..." onRun={async (file) => setResult(await client.template(file))} />
      {result && (
        <div className="mt-3">
          <div className="alert alert-info">{summary(result.stats || {})} Review the detection below, then load it into the builder.</div>
          <OcrDocumentView document={result.document} />
        </div>
      )}
    </OcrModal>
  );
}
