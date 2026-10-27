import { forwardRef, useEffect, useState } from "react";
import "./TableGrid.css";
import { columnKind, type ColumnType, type GridColumn, type GridRow, type TableDefinition } from "./layoutUtils";

/**
 * The "Table / Grid" element of the template designer.
 *
 * Printed columns describe each row (stage, control item, method) and are typed
 * in here by the template author. Recorded columns are filled in on the shop
 * floor; a number column is judged against the row's limits. The backend turns
 * every row x recorded column into one field (form_layout.to_fields).
 *
 * The designer keeps table definitions in its own state, so every change is
 * also announced with a `table-grid-change` window event.
 */

interface TableGridProps extends Partial<TableDefinition> {
  data?: Partial<TableDefinition> & { id?: string; field_name?: string };
  mutable?: boolean;
  updateElement?: (element: Record<string, unknown>) => void;
}

export const TABLE_GRID_CHANGE = "table-grid-change";

export interface TableGridChange extends TableDefinition {
  id?: string;
  field_name?: string;
}

const uid = (): string => Math.random().toString(36).substring(2, 9);

const createColumn = (index: number): GridColumn => ({
  id: `col_${uid()}`,
  name: `Column ${index + 1}`,
  width: 140,
  type: "text",
  kind: "fixed",
});

const createRow = (): GridRow => ({ id: `row_${uid()}`, cells: {} });

const DEFAULT_COLUMNS: GridColumn[] = [
  { id: "col_1", name: "S.NO", width: 70, type: "text", kind: "fixed" },
  { id: "col_2", name: "STAGE", width: 140, type: "text", kind: "fixed" },
  { id: "col_3", name: "CONTROL ITEM", width: 220, type: "text", kind: "fixed" },
  { id: "col_4", name: "CHECKING METHOD", width: 160, type: "text", kind: "fixed" },
  { id: "col_5", name: "FREQUENCY", width: 130, type: "text", kind: "fixed" },
  { id: "col_6", name: "READING", width: 130, type: "number", kind: "input" },
];

const TYPE_OPTIONS: { value: ColumnType; label: string }[] = [
  { value: "number", label: "Number" },
  { value: "text", label: "Text" },
  { value: "dropdown", label: "OK / N-OK" },
  { value: "checkbox", label: "Checkbox" },
  { value: "date", label: "Date" },
];

const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();

const numberOrNull = (value: string) => (value.trim() === "" || Number.isNaN(Number(value)) ? null : Number(value));

const TableGrid = forwardRef<HTMLDivElement, TableGridProps>(function TableGrid(props, ref) {
  const data = (props.data ?? props) as TableGridProps["data"] & Record<string, unknown>;
  const isDesigner = props.mutable !== true;

  const [columns, setColumns] = useState<GridColumn[]>(() =>
    Array.isArray(data?.columns) && data.columns.length ? data.columns : DEFAULT_COLUMNS.map((c) => ({ ...c })),
  );
  const [rows, setRows] = useState<GridRow[]>(() =>
    Array.isArray(data?.rows) && data.rows.length ? data.rows : [createRow(), createRow()],
  );

  // Sync state with incoming props (e.g., when the form schema is loaded from API/localstorage)
  useEffect(() => {
    if (Array.isArray(data?.columns) && data.columns.length && JSON.stringify(data.columns) !== JSON.stringify(columns)) {
      setColumns(data.columns);
    }
    if (Array.isArray(data?.rows) && data.rows.length && JSON.stringify(data.rows) !== JSON.stringify(rows)) {
      setRows(data.rows);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.columns, data?.rows]);

  const hasLimits = columns.some((c) => columnKind(c) === "input" && c.type === "number");

  const announce = (newCols: GridColumn[], newRows: GridRow[]) => {
    // 1. Mutate the builder's own item so its store keeps the definition
    if (data && typeof data === "object") {
      data.columns = newCols;
      data.rows = newRows;
    }

    // 2. Trigger react-form-builder's element store update when it offers one
    props.updateElement?.({ ...data, columns: newCols, rows: newRows });

    // 3. Tell the designer, which saves what it hears here
    window.dispatchEvent(
      new CustomEvent<TableGridChange>(TABLE_GRID_CHANGE, {
        detail: { id: data?.id, field_name: data?.field_name, columns: newCols, rows: newRows },
      }),
    );
  };

  const updateGridSchema = (newCols: GridColumn[], newRows: GridRow[]) => {
    setColumns(newCols);
    setRows(newRows);
    announce(newCols, newRows);
  };

  // A table just dropped onto the canvas starts from the default columns; the
  // designer has to hear about them even if nobody edits the table.
  useEffect(() => {
    if (isDesigner && !(Array.isArray(data?.columns) && data.columns.length)) announce(columns, rows);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateColumn = (id: string, patch: Partial<GridColumn>) =>
    updateGridSchema(columns.map((c) => (c.id === id ? { ...c, ...patch } : c)), rows);

  const updateRow = (id: string, patch: Partial<GridRow>) =>
    updateGridSchema(columns, rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));

  const updateCell = (row: GridRow, columnId: string, value: string) =>
    updateRow(row.id, { cells: { ...(row.cells ?? {}), [columnId]: value } });

  const renderPreview = (column: GridColumn) => {
    switch (column.type) {
      case "number":
        return <input type="number" placeholder={column.name} disabled />;
      case "date":
        return <input type="date" disabled />;
      case "checkbox":
        return <input type="checkbox" disabled />;
      case "dropdown":
        return (
          <select disabled>
            <option value="">OK / N-OK</option>
          </select>
        );
      default:
        return <input type="text" placeholder={column.name} disabled />;
    }
  };

  const renderCell = (row: GridRow, column: GridColumn) => {
    if (columnKind(column) === "input") return renderPreview(column);
    const text = row.cells?.[column.id] ?? "";
    return isDesigner ? (
      <input
        type="text"
        className="tg-fixed-input"
        value={text}
        placeholder="Printed text"
        onChange={(e) => updateCell(row, column.id, e.target.value)}
        onMouseDown={stop}
        onKeyDown={stop}
      />
    ) : (
      <span className="tg-fixed-text">{text}</span>
    );
  };

  const renderLimits = (row: GridRow) =>
    isDesigner ? (
      <div className="tg-limits" onMouseDown={stop}>
        <input
          type="number"
          placeholder="Min"
          aria-label="Minimum"
          value={row.spec_min ?? ""}
          onChange={(e) => updateRow(row.id, { spec_min: numberOrNull(e.target.value) })}
          onKeyDown={stop}
        />
        <input
          type="number"
          placeholder="Max"
          aria-label="Maximum"
          value={row.spec_max ?? ""}
          onChange={(e) => updateRow(row.id, { spec_max: numberOrNull(e.target.value) })}
          onKeyDown={stop}
        />
        <input
          type="text"
          placeholder="Unit"
          aria-label="Unit"
          value={row.unit ?? ""}
          onChange={(e) => updateRow(row.id, { unit: e.target.value || null })}
          onKeyDown={stop}
        />
      </div>
    ) : (
      <span className="tg-fixed-text">
        {row.spec_min ?? "–"} – {row.spec_max ?? "–"} {row.unit ?? ""}
      </span>
    );

  return (
    <div
      ref={ref}
      className="table-grid-wrapper"
      onMouseDown={(e) => {
        // Prevent form builder from initiating drag-and-drop actions on input fields and buttons
        const target = e.target;
        if (!(target instanceof Element)) return;
        if (
          target.tagName === "BUTTON" ||
          target.tagName === "INPUT" ||
          target.tagName === "SELECT" ||
          target.closest(".tg-designer-toolbar") ||
          target.closest(".tg-header-edit")
        ) {
          e.stopPropagation();
        }
      }}
    >
      {/* INLINE TOOLBAR */}
      {isDesigner && (
        <div className="tg-designer-toolbar">
          <button
            type="button"
            className="tg-designer-btn"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              updateGridSchema([...columns, createColumn(columns.length)], rows);
            }}
          >
            + Add Column
          </button>
          <button
            type="button"
            className="tg-designer-btn"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              updateGridSchema(columns, [...rows, createRow()]);
            }}
          >
            + Add Row
          </button>
          <button
            type="button"
            className="tg-designer-btn tg-danger-btn"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              updateGridSchema(columns, rows.length > 1 ? rows.slice(0, -1) : rows);
            }}
          >
            − Remove Row
          </button>
          <span className="tg-hint">
            Printed columns are typed in here. Recorded columns are filled in on the floor; number readings are checked
            against each row's limits.
          </span>
        </div>
      )}

      <div className="table-grid-scroll">
        <table className="table-grid">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.id} style={{ width: col.width, minWidth: col.width }}>
                  {isDesigner ? (
                    <div className="tg-header-edit">
                      <input
                        type="text"
                        value={col.name}
                        placeholder="Column Name"
                        onChange={(e) => updateColumn(col.id, { name: e.target.value })}
                        onMouseDown={stop}
                        onFocus={stop}
                        onKeyDown={stop}
                      />
                      <div className="tg-header-actions">
                        <select
                          value={columnKind(col)}
                          title="Printed or recorded"
                          onChange={(e) => updateColumn(col.id, { kind: e.target.value as GridColumn["kind"] })}
                          onMouseDown={stop}
                          onFocus={stop}
                        >
                          <option value="fixed">Printed</option>
                          <option value="input">Recorded</option>
                        </select>
                        {columnKind(col) === "input" && (
                          <select
                            value={col.type}
                            title="What is recorded"
                            onChange={(e) => updateColumn(col.id, { type: e.target.value as ColumnType })}
                            onMouseDown={stop}
                            onFocus={stop}
                          >
                            {TYPE_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        )}
                        <input
                          type="number"
                          value={col.width}
                          title="Width (px)"
                          onChange={(e) => updateColumn(col.id, { width: Number(e.target.value) || 40 })}
                          onMouseDown={stop}
                          onFocus={stop}
                          onKeyDown={stop}
                        />
                        <button
                          type="button"
                          className="tg-header-del"
                          title="Remove Column"
                          onMouseDown={stop}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            if (columns.length > 1) updateGridSchema(columns.filter((x) => x.id !== col.id), rows);
                          }}
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="column-header">
                      <span>{col.name}</span>
                    </div>
                  )}
                </th>
              ))}
              {hasLimits && (
                <th style={{ minWidth: 190 }}>
                  <div className="column-header">
                    <span>LIMITS (min – max, unit)</span>
                  </div>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                {columns.map((col) => (
                  <td key={`${row.id}_${col.id}`}>{renderCell(row, col)}</td>
                ))}
                {hasLimits && <td>{renderLimits(row)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});

export default TableGrid;
