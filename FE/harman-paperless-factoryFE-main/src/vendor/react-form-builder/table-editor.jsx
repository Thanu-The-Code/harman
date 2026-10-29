/**
  * <TableEditor /> - edit panel section for the Table element: headings, merged cells,
  * fixed text vs input cells and their input type.
  */

import React from 'react';
import IntlMessages from './language-provider/IntlMessages';
import * as T from './table-model';

const TYPE_LABELS = {
  text: 'Text', number: 'Number', date: 'Date', check: '✓ / ✗',
};

export default class TableEditor extends React.Component {
  constructor(props) {
    super(props);
    T.ensureGrids(props.element);
    this.state = { sel: null }; // { part: 'header' | 'body', r, c }
  }

  grid(part) {
    const { element } = this.props;
    return part === 'header' ? element.header : element.rows.map(row => row.cells);
  }

  selected() {
    const { sel } = this.state;
    if (!sel) return null;
    const grid = this.grid(sel.part);
    const cell = grid[sel.r] && grid[sel.r][sel.c];
    return cell && !cell.covered ? cell : null;
  }

  // Structural edits are saved at once; typing marks the element dirty and saves on blur.
  // `next` is the selection afterwards: true keeps it, null clears it, or a new { part, r, c }.
  structure(fn, next = true) {
    fn();
    T.syncColumnTexts(this.props.element);
    if (next === true) this.forceUpdate();
    else this.setState({ sel: next });
    this.props.onStructureChange();
  }

  setText(part, r, c, e) {
    const cell = this.grid(part)[r][c];
    if (part === 'body' && T.isInput(cell)) {
      delete cell.input;
    }
    cell.text = e.target.value;
    if (part === 'header') T.syncColumnTexts(this.props.element);
    this.props.onChange();
  }

  setKind(kind) {
    const { sel } = this.state;
    const cell = this.selected();
    if (!cell || sel.part !== 'body') return;
    this.structure(() => {
      if (kind === 'fixed') {
        delete cell.input;
        cell.text = cell.text || '';
      } else {
        delete cell.text;
        cell.input = kind;
      }
    });
  }

  // Host extension: one input type for every input cell of the row, or of the whole table
  // (a check sheet's 31 day columns are all ✓ / ✗).
  setRowKind(kind) {
    const { sel } = this.state;
    if (!sel || sel.part !== 'body') return;
    this.structure(() => {
      this.props.element.rows[sel.r].cells.forEach((cell) => {
        if (cell && !cell.covered && T.isInput(cell)) cell.input = kind; // eslint-disable-line no-param-reassign
      });
    });
  }

  setAllKind(kind) {
    this.structure(() => {
      this.props.element.rows.forEach(row => row.cells.forEach((cell) => {
        if (cell && !cell.covered && T.isInput(cell)) cell.input = kind; // eslint-disable-line no-param-reassign
      }));
    });
  }

  setColumnKind(kind) {
    const { sel } = this.state;
    if (!sel || sel.part !== 'body') return;
    this.structure(() => {
      this.props.element.rows.forEach((row) => {
        const cell = row.cells[sel.c];
        if (cell && !cell.covered && T.isInput(cell)) cell.input = kind;
      });
    });
  }

  renderCell(part, cell, r, c) {
    const { sel } = this.state;
    const active = sel && sel.part === part && sel.r === r && sel.c === c;
    const select = () => this.setState({ sel: { part, r, c } });
    const span = { rowSpan: cell.rowspan || undefined, colSpan: cell.colspan || undefined };
    const fixed = part === 'header' || !T.isInput(cell);
    return (
      <td key={c} {...span} className={`te-cell${active ? ' te-active' : ''}${fixed ? '' : ' te-input'}`} onMouseDown={select}>
        <textarea
          className="form-control form-control-sm"
          rows={1}
          value={cell.text || ''}
          placeholder=""
          aria-label={`${part === 'header' ? 'Header' : 'Body'} cell ${r + 1}, ${c + 1}`}
          onFocus={select}
          onChange={this.setText.bind(this, part, r, c)}
          onBlur={this.props.onCommit}
        />
      </td>
    );
  }

  // Host extension: what a filled-in cell must meet. A number outside its limits makes the
  // record N-OK; a required cell must be filled before the record is submitted.
  setRule(key, value) {
    const cell = this.selected();
    if (!cell) return;
    if (value === null || value === '') delete cell[key]; else cell[key] = value;
    this.forceUpdate();
    this.props.onChange();
  }

  // Host extension: the selected number cell's limits for every number cell of its row or
  // column (a lux reading taken each day of the month has the same limits in all 31 cells).
  applyRules(scope) {
    const { sel } = this.state;
    const source = this.selected();
    if (!sel || sel.part !== 'body' || !source) return;
    const rows = this.props.element.rows;
    const cells = scope === 'row' ? rows[sel.r].cells : rows.map(row => row.cells[sel.c]);
    this.structure(() => {
      cells.forEach((cell) => {
        if (!cell || cell === source || cell.covered || !T.isInput(cell) || T.inputType(cell) !== 'number') return;
        ['spec_min', 'spec_max', 'unit'].forEach((key) => {
          if (source[key] === undefined || source[key] === null || source[key] === '') delete cell[key]; // eslint-disable-line no-param-reassign
          else cell[key] = source[key]; // eslint-disable-line no-param-reassign
        });
      });
    });
  }

  renderCellRules(cell) {
    const num = (v) => (v === '' || Number.isNaN(Number(v)) ? null : Number(v));
    const isNumber = T.inputType(cell) === 'number';
    return (
      <div className="te-rules mb-1">
        {isNumber && (
          <>
            <input type="number" className="form-control form-control-sm te-rule" placeholder="Min" aria-label="Cell minimum"
              value={cell.spec_min ?? ''} onChange={e => this.setRule('spec_min', num(e.target.value))} onBlur={this.props.onCommit} />
            <input type="number" className="form-control form-control-sm te-rule" placeholder="Max" aria-label="Cell maximum"
              value={cell.spec_max ?? ''} onChange={e => this.setRule('spec_max', num(e.target.value))} onBlur={this.props.onCommit} />
            <input type="text" className="form-control form-control-sm te-rule" placeholder="Unit" aria-label="Cell unit"
              value={cell.unit ?? ''} onChange={e => this.setRule('unit', e.target.value)} onBlur={this.props.onCommit} />
            <button type="button" className="btn btn-sm btn-outline-secondary mr-1" title="Use these limits for every number cell in the row"
              onClick={() => this.applyRules('row')}>Limits to row</button>
            <button type="button" className="btn btn-sm btn-outline-secondary mr-1" title="Use these limits for every number cell in the column"
              onClick={() => this.applyRules('column')}>… to column</button>
          </>
        )}
        <label className="te-required">
          <input type="checkbox" checked={!!cell.required}
            onChange={e => { this.setRule('required', e.target.checked || null); this.props.onCommit(); }} /> Required
        </label>
      </div>
    );
  }

  renderToolbar() {
    const { element } = this.props;
    const { sel } = this.state;
    const cell = this.selected();
    if (!cell) {
      return <p className="help-block mb-1"><IntlMessages id="table-layout-desc" /></p>;
    }
    const grid = this.grid(sel.part);
    const isBody = sel.part === 'body';
    const btn = (label, fn, title, disabled = false) => (
      <button type="button" className="btn btn-sm btn-outline-secondary mr-1 mb-1" title={title} disabled={disabled} onClick={fn}>{label}</button>
    );
    const spanned = (cell.rowspan || 1) > 1 || (cell.colspan || 1) > 1;
    return (
      <div className="te-toolbar">
        {isBody && (
          <div className="mb-1">
            <select className="form-control form-control-sm d-inline-block w-auto mr-1"
              value={T.isInput(cell) ? T.inputType(cell) : 'fixed'} onChange={e => this.setKind(e.target.value)}>
              <option value="fixed">Fixed text</option>
              {T.INPUT_TYPES.map(t => <option key={t} value={t}>Input: {TYPE_LABELS[t]}</option>)}
            </select>
            {T.isInput(cell) && btn('Apply type to column', () => this.setColumnKind(T.inputType(cell)), 'Use this input type for every input cell in the column')}
            {T.isInput(cell) && btn('… to row', () => this.setRowKind(T.inputType(cell)), 'Use this input type for every input cell in the row')}
            {T.isInput(cell) && btn('… to all inputs', () => this.setAllKind(T.inputType(cell)), 'Use this input type for every input cell of the table')}
          </div>
        )}
        {isBody && T.isInput(cell) && this.renderCellRules(cell)}
        {btn('Merge →', () => this.structure(() => T.mergeRight(grid, sel.r, sel.c)), 'Merge with the cell on the right')}
        {btn('Merge ↓', () => this.structure(() => T.mergeDown(grid, sel.r, sel.c)), 'Merge with the cell below')}
        {btn('Split', () => this.structure(() => T.split(grid, sel.r, sel.c, isBody)), 'Undo merging', !spanned)}
        <span className="mx-1 text-muted">|</span>
        {btn('+ Column left', () => this.structure(() => T.addColumn(element, sel.c), { ...sel, c: sel.c + 1 }))}
        {btn('+ Column right', () => this.structure(() => T.addColumn(element, sel.c + (cell.colspan || 1))))}
        {btn('Delete column', () => this.structure(() => T.removeColumn(element, sel.c), null), '', element.columns.length <= 1)}
        <span className="mx-1 text-muted">|</span>
        {isBody ? (
          <>
            {btn('+ Row above', () => this.structure(() => T.addRow(element, sel.r), { ...sel, r: sel.r + 1 }))}
            {btn('+ Row below', () => this.structure(() => T.addRow(element, sel.r + (cell.rowspan || 1))))}
            {btn('Delete row', () => this.structure(() => T.removeRow(element, sel.r), null), '', element.rows.length <= 1)}
          </>
        ) : (
          <>
            {btn('+ Heading row', () => this.structure(() => T.addHeaderRow(element), { ...sel, r: sel.r + 1 }))}
            {btn('Delete heading row', () => this.structure(() => T.removeHeaderRow(element, sel.r), null), '', element.header.length <= 1)}
          </>
        )}
      </div>
    );
  }

  render() {
    const { element } = this.props;
    T.ensureGrids(element);
    return (
      <div className="form-group table-editor">
        <label className="control-label"><IntlMessages id="table-layout" /></label>
        {this.renderToolbar()}
        <div className="table-responsive te-grid">
          <table className="table table-bordered table-sm mb-1">
            <thead>
              {element.header.map((row, r) => (
                <tr key={`h${r}`}>{row.map((cell, c) => (cell.covered ? null : this.renderCell('header', cell, r, c)))}</tr>
              ))}
            </thead>
            <tbody>
              {element.rows.map((row, r) => (
                <tr key={row.key}>{row.cells.map((cell, c) => (cell.covered ? null : this.renderCell('body', cell, r, c)))}</tr>
              ))}
            </tbody>
          </table>
        </div>
        {element.header.length === 0 && (
          <button type="button" className="btn btn-outline-secondary btn-sm mb-1"
            onClick={() => this.structure(() => T.addHeaderRow(element), { part: 'header', r: 0, c: 0 })}>
            + Heading row
          </button>
        )}
        <button type="button" className="btn btn-success btn-sm" onClick={() => this.structure(() => T.addRow(this.props.element, this.props.element.rows.length))}>
          <i className="fas fa-plus-circle"></i> <IntlMessages id="add-row" />
        </button>
      </div>
    );
  }
}
