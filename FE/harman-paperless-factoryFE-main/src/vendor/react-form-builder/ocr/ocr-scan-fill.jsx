import React, { useMemo, useState } from 'react';
import createOcrClient from './ocr-client';
import OcrDocumentView from './ocr-document-view';
import { OcrFileAction, OcrModal, useFormats } from './ocr-shared';
import ReviewTable, { ReviewSummary, defaultSelection, selectedAnswers } from './ocr-review';

/**
 * Requirement A: read a filled document and fill the given form with what was read.
 * `data` is the form's task_data; onApply(answers) receives { field_name: value }.
 */
export default function OcrScanFill({
  baseUrl, data, onApply, onClose,
}) {
  const client = useMemo(() => createOcrClient(baseUrl), [baseUrl]);
  const formats = useFormats(client, 'extract');
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState({});
  const [showDoc, setShowDoc] = useState(false);

  const scan = async (file) => {
    const res = await client.extract(file, data);
    setResult(res);
    setSelected(defaultSelection(res));
  };

  const footer = result && (
    <button type="button" className="btn btn-primary" onClick={() => onApply(selectedAnswers(result, selected), result)}
      disabled={!Object.values(selected).some(Boolean)}>
      Fill form with selected values
    </button>
  );

  return (
    <OcrModal title="Fill from document" onClose={onClose} footer={footer}>
      <p className="text-muted">Upload a filled copy of this form: a filled Excel workbook, a PDF or a scan/photo. Values read from it are shown for review before they are put into the form.</p>
      <OcrFileAction formats={formats} actionLabel="Read values" busyLabel="Reading document..." onRun={scan} />
      {result && (
        <div className="mt-3">
          <div className="alert alert-info"><ReviewSummary result={result} /></div>
          <ReviewTable result={result} selected={selected} onSelect={setSelected} />
          <button type="button" className="btn btn-link px-0" onClick={() => setShowDoc(!showDoc)}>
            {showDoc ? 'Hide' : 'Show'} scanned document
          </button>
          {showDoc && <OcrDocumentView document={result.document} />}
        </div>
      )}
    </OcrModal>
  );
}
