import React from 'react';
import { ConfidenceBadge } from './ocr-shared';

export const LOW_CONFIDENCE = 0.6;
const METHODS = {
  zone: 'position', label: 'label text', cell: 'cell address', none: '-',
};

function display(value) {
  if (value === null || value === undefined) return <span className="text-muted">not found</span>;
  if (Array.isArray(value)) {
    return (
      <table className="table table-sm table-bordered mb-0">
        <tbody>
          {value.map((row, r) => <tr key={r}>{row.map((cell, c) => <td key={c}>{cell}</td>)}</tr>)}
        </tbody>
      </table>
    );
  }
  return String(value);
}

/** Which fields were read, with confidence; `selected` decides which values get used. */
export function defaultSelection(result) {
  const sel = {};
  result.fields.forEach((f) => { sel[f.field_name] = f.field_name in result.answers; });
  return sel;
}

export function selectedAnswers(result, selected) {
  const answers = {};
  Object.keys(result.answers).forEach((k) => {
    if (selected[k]) answers[k] = result.answers[k];
  });
  return answers;
}

export function ReviewSummary({ result }) {
  const found = result.fields.filter(f => f.field_name in result.answers).length;
  const low = result.fields.some(f => f.method !== 'none' && f.confidence < LOW_CONFIDENCE);
  return (
    <>
      Found values for {found} of {result.fields.length} fields.
      {low && ' Rows in red have low confidence; please check them.'}
    </>
  );
}

export default function ReviewTable({ result, selected, onSelect }) {
  return (
    <table className="table table-sm ocr-review">
      <thead>
        <tr><th style={{ width: '1%' }}>Use</th><th>Field</th><th>Value read from document</th><th>Confidence</th><th>Matched by</th></tr>
      </thead>
      <tbody>
        {result.fields.map((f) => {
          const has = f.field_name in result.answers;
          const low = has && f.confidence < LOW_CONFIDENCE;
          return (
            <tr key={f.field_name} className={low ? 'table-danger' : ''}>
              <td>
                <input type="checkbox" disabled={!has} checked={!!selected[f.field_name]}
                  onChange={(e) => onSelect({ ...selected, [f.field_name]: e.target.checked })} />
              </td>
              <td>{f.label}<br /><small className="text-muted">{f.element}</small></td>
              <td>{display(f.value)}</td>
              <td>{has && <ConfidenceBadge value={f.confidence} />}</td>
              <td><small>{METHODS[f.method]}</small></td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
