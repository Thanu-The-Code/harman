import { saveAs } from 'file-saver';

// Used until /ocr/formats answers (or if it cannot be reached).
export const DEFAULT_FORMATS = [
  { key: 'pdf', label: 'PDF', extensions: ['.pdf'], mime_types: ['application/pdf'], capabilities: ['template', 'extract', 'digitize', 'read_form'] },
  { key: 'image', label: 'Image', extensions: ['.png', '.jpg', '.jpeg'], mime_types: ['image/png', 'image/jpeg'], capabilities: ['template', 'extract', 'digitize', 'read_form'] },
  { key: 'excel', label: 'Excel', extensions: ['.xlsx', '.xlsm', '.xls'], mime_types: [], capabilities: ['template', 'extract', 'digitize', 'read_form', 'export'] },
];

/** Formats that support a capability ('template' | 'extract' | 'digitize' | 'read_form' | 'export'). */
export function formatsFor(formats, capability) {
  return (formats || DEFAULT_FORMATS).filter(f => !capability || (f.capabilities || []).indexOf(capability) > -1);
}

/** Value for <input type="file" accept>. */
export function acceptAttribute(formats) {
  return formats.reduce((acc, f) => acc.concat(f.extensions || [], f.mime_types || []), []).join(',');
}

export function isAcceptedFile(file, formats) {
  if (!file) return false;
  const name = (file.name || '').toLowerCase();
  return formats.some(f => (f.extensions || []).some(ext => name.endsWith(ext)));
}

export function describeFormats(formats) {
  return formats.map(f => `${f.label} (${(f.extensions || []).join(', ')})`).join(', ');
}

async function send(url, body, headers) {
  let response;
  try {
    response = await fetch(url, { method: 'POST', body, headers });
  } catch (e) {
    throw new Error(`Could not reach the OCR service (${url}). Is it running?`);
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (e) {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && payload.detail;
    throw new Error(typeof detail === 'string' ? detail : `OCR service error (${response.status})`);
  }
  return payload;
}

// Documents used in this session, newest first: a form made from a workbook can be saved back into it.
const recent = [];
const MAX_RECENT = 5;

export function rememberSource(file) {
  if (!file) return;
  const i = recent.indexOf(file);
  if (i > -1) recent.splice(i, 1);
  recent.unshift(file);
  recent.length = Math.min(recent.length, MAX_RECENT);
}

export function recentSources() {
  return recent.slice();
}

/** Save an /ocr/export result as a file download. */
export function saveExport(result) {
  const bytes = atob(result.data);
  const buf = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i += 1) buf[i] = bytes.charCodeAt(i);
  saveAs(new Blob([buf], { type: result.media_type }), result.filename);
}

function fileBody(file) {
  rememberSource(file);
  const body = new FormData();
  body.append('file', file, file.name);
  return body;
}

/**
 * Client for the document service (the backend's /api/ocr routes).
 * `getHeaders` supplies per-request headers, e.g. the bearer token.
 */
export default function createOcrClient(baseUrl = '/api', { getHeaders = () => ({}) } = {}) {
  const root = `${(baseUrl || '').replace(/\/$/, '')}/ocr`;
  const get = path => fetch(`${root}${path}`, { headers: getHeaders() });
  const post = (path, body) => send(`${root}${path}`, body, getHeaders());
  return {
    health: () => get('/health').then(r => r.json()),
    formats: () => get('/formats').then(r => (r.ok ? r.json() : Promise.reject(r))).then(r => r.formats),
    digitize: (file) => post('/digitize', fileBody(file)),
    // A filled-in document as an editable form plus the values read from it, in one pass.
    readForm: (file) => post('/read-form', fileBody(file)),
    template: (file) => post('/template', fileBody(file)),
    extract: (file, taskData) => {
      const body = fileBody(file);
      // Custom element components are functions; JSON.stringify drops them.
      body.append('form', JSON.stringify(taskData || []));
      return post('/extract', body);
    },
    // The document (e.g. the blank Excel form) with the form's values written in: { filename, media_type, data (base64), written, skipped }.
    exportForm: (file, taskData, answers) => {
      const body = fileBody(file);
      body.append('form', JSON.stringify(taskData || []));
      body.append('answers', JSON.stringify(answers || {}));
      return post('/export', body);
    },
  };
}
