import React from 'react';
import ComponentHeader from './component-header';
import ComponentLabel from './component-label';
import {
  CHECK_VALUES, bodyGrid, headerGrid, inputType, isInput,
} from '../table-model';

/** Tri-state tick cell: blank -> ✓ -> ✗ -> blank. The value travels in a hidden input. */
class CheckCell extends React.Component {
  constructor(props) {
    super(props);
    this.state = { value: CHECK_VALUES.indexOf(props.defaultValue) > -1 ? props.defaultValue : '' };
  }

  get value() {
    return this.state.value;
  }

  cycle = () => {
    if (this.props.disabled) return;
    const next = CHECK_VALUES[(CHECK_VALUES.indexOf(this.state.value) + 1) % CHECK_VALUES.length];
    this.setState({ value: next }, () => this.props.onChange && this.props.onChange());
  };

  render() {
    const { value } = this.state;
    const cls = value === '✓' ? 'is-ok' : (value === '✗' ? 'is-not-ok' : '');
    return (
      <>
        <button type="button" className={`rfb-check-cell ${cls}`} onClick={this.cycle} disabled={this.props.disabled}
          title={value === '✓' ? 'OK' : (value === '✗' ? 'NOT OK' : 'Click to mark')}>
          {value || ' '}
        </button>
        <input type="hidden" name={this.props.name} value={value} />
      </>
    );
  }
}

/**
 * Grid of fixed text and input cells with optional multi-row headings and merged cells
 * (see table-model.js). The value is a 2-D array of strings, rows x columns.
 */
class Table extends React.Component {
  constructor(props) {
    super(props);
    this.cells = {};
  }

  getValue() {
    const rows = bodyGrid(this.props.data);
    return rows.map((row, r) => row.map((cell, c) => {
      if (!isInput(cell)) return '';
      const input = this.cells[`${r}_${c}`];
      return input ? (input.value || '') : '';
    }));
  }

  renderInput(cell, r, c) {
    const { data, mutable, read_only, defaultValue } = this.props;
    const value = defaultValue && defaultValue[r] ? defaultValue[r][c] : undefined;
    const name = `${data.field_name}[${r}][${c}]`;
    const disabled = !mutable || read_only;
    const ref = (el) => {
      if (el) this.cells[`${r}_${c}`] = el;
    };
    const type = inputType(cell);
    if (type === 'check') {
      return <CheckCell ref={ref} name={name} defaultValue={mutable ? value : ''} disabled={disabled} onChange={this.props.handleChange} />;
    }
    return (
      <input type={type === 'number' ? 'number' : (type === 'date' ? 'date' : 'text')} className="form-control form-control-sm"
        name={name} defaultValue={mutable ? value : undefined} disabled={disabled} ref={ref} />
    );
  }

  render() {
    const { data } = this.props;
    const header = headerGrid(data);
    const body = bodyGrid(data);
    const wide = (data.columns || []).length > 12;

    let baseClasses = 'SortableItem rfb-item';
    if (data.pageBreakBefore) {
      baseClasses += ' alwaysbreak';
    }

    const span = cell => ({ rowSpan: cell.rowspan || undefined, colSpan: cell.colspan || undefined });
    return (
      <div style={{ ...this.props.style }} className={baseClasses}>
        <ComponentHeader {...this.props} />
        <div className="form-group">
          <ComponentLabel {...this.props} />
          <div className={`table-responsive${wide ? ' rfb-table-scroll-wide' : ''}`}>
            <table className={`table table-bordered table-sm rfb-table${wide ? ' rfb-table-wide' : ''}`}>
              <thead>
                {header.map((row, r) => (
                  <tr key={`h${r}`}>
                    {row.map((cell, c) => (cell.covered ? null : <th key={c} {...span(cell)}>{cell.text}</th>))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {body.map((row, r) => (
                  <tr key={(data.rows[r] && data.rows[r].key) || r}>
                    {row.map((cell, c) => {
                      if (cell.covered) return null;
                      if (!isInput(cell)) {
                        return <td key={c} className="rfb-table-static" {...span(cell)}>{cell.text}</td>;
                      }
                      return <td key={c} className="rfb-input-cell" {...span(cell)}>{this.renderInput(cell, r, c)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }
}

export default Table;
