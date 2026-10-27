import { useEffect, type ReactNode } from "react";
import type { LayoutItem } from "../api/formats.api";
import type { RecordValue } from "../api/records.api";
import {
  columnKind,
  fieldName,
  fieldWidth,
  isRecordable,
  isTable,
  isTableGrid,
  plainText,
  specSummary,
  tableCellKey,
  type GridColumn,
  type GridRow,
} from "../templateBuilder/designer/layoutUtils";
import { bodyGrid, headerGrid, isInput, type TableElementLike } from "../vendor/react-form-builder/table-model";
import myxss from "../vendor/react-form-builder/form-elements/myxss";
import ValueField from "./ValueField";
import ValueCell from "./ValueCell";
import { currentValue, type Edits } from "./recordValue";

interface FormProps {
  values: RecordValue[];
  edits: Edits;
  onChange: (id: string, patch: { value?: string; remark?: string }) => void;
  readOnly?: boolean;
}

/* ------------------------------------------------------------ Mode A */

/** Every reading in order, for formats without a designed layout. */
export const ValuesForm = ({ values, edits, onChange, readOnly }: FormProps) => (
  <div className="values-grid">
    {[...values]
      .sort((a, b) => a.order - b.order)
      .map((v) => (
        <ValueField key={v.id} value={v} edits={edits} onChange={onChange} readOnly={readOnly} />
      ))}
  </div>
);

/* ------------------------------------------------------------ Mode B */

const ROW_ELEMENTS = new Set(["TwoColumnRow", "ThreeColumnRow", "MultiColumnRow"]);

/** Text the designer formatted (bold, lists, alignment), cleaned the way the designer shows it. */
const RichText = ({ html, as: Tag = "p", className }: { html: unknown; as?: "p" | "h3"; className: string }) => (
  <Tag className={className} dangerouslySetInnerHTML={{ __html: myxss.process(String(html ?? "")) }} />
);

interface LayoutProps extends FormProps {
  layout: LayoutItem[];
}

/**
 * The record drawn as it was designed. Inputs are matched to the record's
 * values by `layout_key`; anything the layout does not place is listed at the end.
 */
export const LayoutRecordForm = ({ layout, values, edits, onChange, readOnly }: LayoutProps) => {
  const byKey = new Map(values.filter((v) => v.layout_key).map((v) => [v.layout_key as string, v]));
  const byId = new Map(layout.filter((i) => i.id).map((i) => [String(i.id), i]));
  const placed = new Set<string>();

  // a default value from the designer is put in once, while the entry is still empty
  useEffect(() => {
    if (readOnly) return;
    layout.forEach((item) => {
      const preset = item.default_value;
      if (!isRecordable(item) || preset === undefined || preset === null || preset === "") return;
      const v = byKey.get(fieldName(item));
      if (v && !currentValue(v, edits)) onChange(v.id, { value: String(preset) });
    });
    // only when the record (or its layout) arrives, not on every keystroke
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, values, readOnly]);

  const field = (key: string, props: { compact?: boolean; label?: string; placeholder?: string } = {}) => {
    const v = byKey.get(key);
    if (!v) return null;
    placed.add(v.id);
    // inside a table: the light cell (a check sheet has hundreds); otherwise the full field
    if (props.compact) return <ValueCell value={v} edit={edits[v.id]} onChange={onChange} readOnly={readOnly} />;
    return <ValueField value={v} edits={edits} onChange={onChange} readOnly={readOnly} {...props} />;
  };

  /** The earlier Table / Grid element (printed or recorded columns, a limit per row). */
  const renderTableGrid = (item: LayoutItem) => {
    const grid = (item.table_grid ?? {}) as { columns?: GridColumn[]; rows?: GridRow[] };
    const columns = (item.columns as GridColumn[]) ?? grid.columns ?? [];
    const rows = (item.rows as GridRow[]) ?? grid.rows ?? [];
    const name = fieldName(item);
    const hasLimits = columns.some((c) => columnKind(c) === "input" && c.type === "number");
    return (
      <div className="record-table-block">
        {plainText(item.label) && <div className="record-table-title">{plainText(item.label)}</div>}
        <div className="record-table-scroll">
          <table className="record-table">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.id} style={{ minWidth: c.width }}>
                    {c.name}
                  </th>
                ))}
                {hasLimits && <th style={{ minWidth: 130 }}>Limits</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  {columns.map((c) => (
                    <td key={c.id}>
                      {columnKind(c) === "input"
                        ? field(`${name}:${row.id}:${c.id}`, { compact: true })
                        : (row.cells?.[c.id] ?? "")}
                    </td>
                  ))}
                  {hasLimits && <td className="limits-cell">{specSummary(row) || "—"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  /** The designer's Table / Grid: heading rows and merged cells as on the sheet; each input cell is a value. */
  const renderTable = (item: LayoutItem) => {
    const table = item as LayoutItem & TableElementLike;
    const columns = table.columns ?? [];
    const rows = table.rows ?? [];
    const span = (cell: { rowspan?: number; colspan?: number }) => ({ rowSpan: cell.rowspan, colSpan: cell.colspan });
    return (
      <div className="record-table-block">
        {plainText(item.label) && <div className="record-table-title">{plainText(item.label)}</div>}
        <div className="record-table-scroll">
          <table className="record-table">
            <thead>
              {headerGrid(table).map((row, r) => (
                <tr key={`h${r}`}>
                  {row.map((cell, c) =>
                    cell.covered ? null : (
                      <th key={c} {...span(cell)}>
                        {cell.text}
                      </th>
                    ),
                  )}
                </tr>
              ))}
            </thead>
            <tbody>
              {bodyGrid(table).map((row, r) => (
                <tr key={rows[r]?.key ?? r}>
                  {row.map((cell, c) => {
                    if (cell.covered) return null;
                    if (!isInput(cell)) {
                      return (
                        <td key={c} className="printed-cell" {...span(cell)}>
                          {cell.text}
                        </td>
                      );
                    }
                    const column = columns[c];
                    return (
                      <td key={c} {...span(cell)}>
                        {rows[r] && column ? field(tableCellKey(item, rows[r].key, column.key), { compact: true }) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderItem = (item: LayoutItem): ReactNode => {
    const element = String(item.element ?? "");
    if (isTable(item)) return renderTable(item);
    if (isTableGrid(item)) return renderTableGrid(item);
    if (isRecordable(item)) {
      return field(fieldName(item), {
        label: plainText(item.label) || undefined,
        placeholder: typeof item.placeholder === "string" ? item.placeholder : undefined,
      });
    }
    if (ROW_ELEMENTS.has(element)) {
      const children = (item.childItems as (string | null)[] | undefined) ?? [];
      return (
        <div className="record-columns" style={{ gridTemplateColumns: `repeat(${Math.max(children.length, 1)}, minmax(0, 1fr))` }}>
          {children.map((childId, i) => {
            const child = childId ? byId.get(childId) : undefined;
            return <div key={childId ?? i}>{child ? renderItem(child) : null}</div>;
          })}
        </div>
      );
    }
    switch (element) {
      case "Header":
        return <RichText as="h3" className="record-heading" html={item.content} />;
      case "Label":
      case "Paragraph":
        return <RichText className="record-text" html={item.content} />;
      case "LineBreak":
        return <hr className="record-rule" />;
      case "Signature":
        return <p className="record-text muted">{plainText(item.label) || "Signature"} — signed during the approval.</p>;
      case "Image":
        return typeof item.src === "string" && item.src ? <img className="record-image" src={item.src} alt="" /> : null;
      default:
        return null;
    }
  };

  const topLevel = layout.filter((item) => !item.parentId);
  const body = topLevel.map((item, i) => {
    // Field Properties -> Appearance: width and text alignment, as on the designer's canvas
    const width = fieldWidth(item);
    const align = typeof item.text_align === "string" ? (item.text_align as "left" | "center" | "right") : undefined;
    return (
      <div
        className="record-item"
        key={String(item.id ?? i)}
        style={width || align ? { width, display: width ? "inline-block" : undefined, verticalAlign: "top", textAlign: align } : undefined}
      >
        {renderItem(item)}
      </div>
    );
  });
  const leftovers = values.filter((v) => !placed.has(v.id));

  return (
    <>
      <div className="record-layout">{body}</div>
      {leftovers.length > 0 && (
        <div className="record-leftovers">
          <div className="record-table-title">Other entries</div>
          <ValuesForm values={leftovers} edits={edits} onChange={onChange} readOnly={readOnly} />
        </div>
      )}
    </>
  );
};
