/**
 * Table element model.
 *
 * element.columns: [{ key, text, title? }]           leaf columns
 * element.header:  [[cell]]                           optional heading rows (default: one row of column texts)
 * element.rows:    [{ key, cells: [cell] }]           body rows
 *
 * A cell is { text } (fixed text), { input: 'text'|'number'|'date'|'check' } (to fill in) or
 * { covered: true } (hidden under a neighbour's rowspan/colspan). Legacy string cells are accepted:
 * '' means an input, any other string is fixed text. Every grid row has one entry per column.
 *
 * Values are 2-D arrays [row][column] of strings, '' for fixed and covered cells.
 */
import ID from './UUID';

export const INPUT_TYPES = ['text', 'number', 'date', 'check'];
export const CHECK_VALUES = ['', '✓', '✗'];

export function normalizeCell(cell) {
  if (cell && typeof cell === 'object') return cell;
  return cell ? { text: String(cell) } : { input: 'text' };
}

export function isInput(cell) {
  const c = normalizeCell(cell);
  return !c.covered && ('input' in c || !(c.text || '').trim());
}

export function inputType(cell) {
  const c = normalizeCell(cell);
  return INPUT_TYPES.indexOf(c.input) > -1 ? c.input : 'text';
}

function pad(cells, n, filler) {
  const out = (cells || []).slice(0, n).map(normalizeCell);
  while (out.length < n) out.push(filler());
  return out;
}

export function headerGrid(element) {
  const n = (element.columns || []).length;
  if (element.header && element.header.length) {
    return element.header.map(row => pad(row, n, () => ({ text: '' })));
  }
  return [(element.columns || []).map(col => ({ text: col.text || '' }))];
}

export function bodyGrid(element) {
  const n = (element.columns || []).length;
  return (element.rows || []).map(row => pad(row.cells, n, () => ({ input: 'text' })));
}

/** Convert a legacy element to explicit header/body grids (in place) before editing. */
export function ensureGrids(element) {
  element.columns = element.columns || [];
  element.header = headerGrid(element);
  const body = bodyGrid(element);
  element.rows = (element.rows || []).map((row, r) => ({ ...row, key: row.key || `row_${ID.uuid()}`, cells: body[r] }));
  return element;
}

/** [[{ r, c }]] owner anchor of every grid position. */
export function owners(grid) {
  const own = grid.map(row => row.map(() => null));
  grid.forEach((row, r) => row.forEach((cell, c) => {
    if (cell.covered) return;
    const rs = cell.rowspan || 1;
    const cs = cell.colspan || 1;
    for (let i = r; i < Math.min(grid.length, r + rs); i++) {
      for (let j = c; j < Math.min(row.length, c + cs); j++) own[i][j] = { r, c };
    }
  }));
  return own;
}

function setSpan(cell, key, n) {
  if (n > 1) cell[key] = n; else delete cell[key]; // eslint-disable-line no-param-reassign
}

export function mergeRight(grid, r, c) {
  const a = grid[r][c];
  const cs = a.colspan || 1;
  const rs = a.rowspan || 1;
  const b = grid[r][c + cs];
  if (!b || b.covered || (b.rowspan || 1) !== rs) return false;
  const bcs = b.colspan || 1;
  if (!a.input && b.text) a.text = [a.text, b.text].filter(Boolean).join(' ');
  for (let i = r; i < r + rs; i++) for (let j = c + cs; j < c + cs + bcs; j++) grid[i][j] = { covered: true };
  setSpan(a, 'colspan', cs + bcs);
  return true;
}

export function mergeDown(grid, r, c) {
  const a = grid[r][c];
  const cs = a.colspan || 1;
  const rs = a.rowspan || 1;
  const b = grid[r + rs] && grid[r + rs][c];
  if (!b || b.covered || (b.colspan || 1) !== cs) return false;
  const brs = b.rowspan || 1;
  if (!a.input && b.text) a.text = [a.text, b.text].filter(Boolean).join('\n');
  for (let i = r + rs; i < r + rs + brs; i++) for (let j = c; j < c + cs; j++) grid[i][j] = { covered: true };
  setSpan(a, 'rowspan', rs + brs);
  return true;
}

export function split(grid, r, c, isBody) {
  const a = grid[r][c];
  const rs = a.rowspan || 1;
  const cs = a.colspan || 1;
  for (let i = r; i < r + rs; i++) {
    for (let j = c; j < c + cs; j++) {
      if (i !== r || j !== c) grid[i][j] = isBody ? { input: a.input || 'text' } : { text: '' };
    }
  }
  setSpan(a, 'rowspan', 1);
  setSpan(a, 'colspan', 1);
}

function insertLine(grid, at, width, makeCell, axis) {
  // axis 'row': insert a grid row before index `at`; 'col': insert a column in every row.
  const own = owners(grid);
  if (axis === 'row') {
    const line = [];
    for (let c = 0; c < width; c++) {
      const o = at > 0 && at < grid.length ? own[at][c] : null;
      if (o && o.r < at) {
        const anchor = grid[o.r][o.c];
        if (o.c === c) setSpan(anchor, 'rowspan', (anchor.rowspan || 1) + 1);
        line.push({ covered: true });
      } else line.push(makeCell(c));
    }
    grid.splice(at, 0, line);
    return;
  }
  const extended = new Set();
  grid.forEach((row, r) => {
    const o = at > 0 && at < row.length ? own[r][at] : null;
    if (o && o.c < at) {
      const key = `${o.r}_${o.c}`;
      if (!extended.has(key)) {
        const anchor = grid[o.r][o.c];
        setSpan(anchor, 'colspan', (anchor.colspan || 1) + 1);
        extended.add(key);
      }
      row.splice(at, 0, { covered: true });
    } else row.splice(at, 0, makeCell(r));
  });
}

function removeLine(grid, at, axis) {
  const own = owners(grid);
  const done = new Set();
  if (axis === 'row') {
    grid[at].forEach((cell, c) => {
      const o = own[at][c];
      if (!o) return;
      const key = `${o.r}_${o.c}`;
      if (done.has(key)) return;
      done.add(key);
      const anchor = grid[o.r][o.c];
      const rs = anchor.rowspan || 1;
      if (o.r === at && rs > 1) {
        const moved = { ...anchor };
        setSpan(moved, 'rowspan', rs - 1);
        grid[at + 1][o.c] = moved;
      } else if (o.r < at) setSpan(anchor, 'rowspan', rs - 1);
    });
    grid.splice(at, 1);
    return;
  }
  grid.forEach((row, r) => {
    const o = own[r][at];
    if (o) {
      const key = `${o.r}_${o.c}`;
      if (!done.has(key)) {
        done.add(key);
        const anchor = grid[o.r][o.c];
        const cs = anchor.colspan || 1;
        if (o.c === at && cs > 1) {
          const moved = { ...anchor };
          setSpan(moved, 'colspan', cs - 1);
          grid[o.r][at + 1] = moved;
        } else if (o.c < at) setSpan(anchor, 'colspan', cs - 1);
      }
    }
  });
  grid.forEach(row => row.splice(at, 1));
}

function writeBack(element, header, body) {
  element.header = header; // eslint-disable-line no-param-reassign
  element.rows = body.map((cells, r) => ({ key: (element.rows[r] && element.rows[r].key) || `row_${ID.uuid()}`, cells })); // eslint-disable-line no-param-reassign
}

/**
 * Keep per-cell source maps (Excel cell addresses, scan positions) aligned with the body grid
 * when rows or columns are inserted or removed, so filling still reads the right cells.
 */
function spliceMeta(element, axis, at, remove, insert) {
  const maps = [element.excel && element.excel.cells, element.ocr && element.ocr.cell_bboxes].filter(Array.isArray);
  maps.forEach((grid) => {
    if (axis === 'row') {
      const width = grid[0] ? grid[0].length : 0;
      grid.splice(at, remove, ...Array.from({ length: insert }, () => Array(width).fill(null)));
    } else {
      grid.forEach(row => row.splice(at, remove, ...Array(insert).fill(null)));
    }
  });
}

export function addRow(element, at) {
  ensureGrids(element);
  const body = element.rows.map(row => row.cells);
  const keys = element.rows.map(row => row.key);
  insertLine(body, at, element.columns.length, c => ({ input: inputType(body[at - 1] ? body[at - 1][c] : null) }), 'row');
  keys.splice(at, 0, `row_${ID.uuid()}`);
  element.rows = body.map((cells, r) => ({ key: keys[r], cells })); // eslint-disable-line no-param-reassign
  spliceMeta(element, 'row', at, 0, 1);
}

export function removeRow(element, at) {
  ensureGrids(element);
  if (element.rows.length <= 1) return;
  const body = element.rows.map(row => row.cells);
  const keys = element.rows.map(row => row.key);
  removeLine(body, at, 'row');
  keys.splice(at, 1);
  element.rows = body.map((cells, r) => ({ key: keys[r], cells })); // eslint-disable-line no-param-reassign
  spliceMeta(element, 'row', at, 1, 0);
}

export function addColumn(element, at) {
  ensureGrids(element);
  const header = element.header;
  const body = element.rows.map(row => row.cells);
  const bottom = header.length - 1;
  insertLine(header, at, 0, r => ({ text: r === bottom ? `Column ${element.columns.length + 1}` : '' }), 'col');
  insertLine(body, at, 0, () => ({ input: 'text' }), 'col');
  element.columns.splice(at, 0, { key: `col_${ID.uuid()}`, text: `Column ${element.columns.length + 1}` });
  writeBack(element, header, body);
  spliceMeta(element, 'col', at, 0, 1);
}

export function removeColumn(element, at) {
  ensureGrids(element);
  if (element.columns.length <= 1) return;
  const header = element.header;
  const body = element.rows.map(row => row.cells);
  removeLine(header, at, 'col');
  removeLine(body, at, 'col');
  element.columns.splice(at, 1);
  writeBack(element, header, body);
  spliceMeta(element, 'col', at, 1, 0);
}

export function addHeaderRow(element) {
  ensureGrids(element);
  element.header.unshift(element.columns.map(() => ({ text: '' })));
}

export function removeHeaderRow(element, at) {
  ensureGrids(element);
  if (element.header.length <= 1) return;
  removeLine(element.header, at, 'row');
}

/** Keep column texts (used for matching scans) in sync with the bottom heading row. */
export function syncColumnTexts(element) {
  const header = headerGrid(element);
  const own = owners(header);
  element.columns.forEach((col, c) => {
    const texts = [];
    header.forEach((row, r) => {
      const o = own[r][c];
      const t = o ? (header[o.r][o.c].text || '').trim() : '';
      if (t && texts.indexOf(t) === -1) texts.push(t);
    });
    col.text = texts.length ? texts[texts.length - 1] : ''; // eslint-disable-line no-param-reassign
    col.title = texts.join(' '); // eslint-disable-line no-param-reassign
  });
}
