import type { LayoutItem } from "../../api/formats.api";

/**
 * Helpers shared by the designer and the fill screen. They mirror the backend's
 * `form_layout.to_fields`, which decides what on a designed form is recorded.
 */

// Builder elements that print something but record nothing (kept in step with
// PRESENTATION_ELEMENTS in BE app/services/form_layout.py).
const PRESENTATION = new Set([
  "header", "label", "paragraph", "text", "html", "divider", "section",
  "title", "linebreak", "image", "hyperlink", "download", "signature",
  "fieldset", "twocolumnrow", "threecolumnrow", "multicolumnrow",
]);

const NUMBER_ELEMENTS = new Set(["NumberInput", "Range", "Rating"]);

export type ColumnType = "text" | "number" | "date" | "dropdown" | "checkbox";

export interface GridColumn {
  id: string;
  name: string;
  width: number;
  type: ColumnType;
  /** "fixed" = printed on the sheet, "input" = filled in. Older tables have no kind: every column was an input. */
  kind?: "fixed" | "input";
}

export interface GridRow {
  id: string;
  /** Printed text, by column id. */
  cells?: Record<string, string>;
  unit?: string | null;
  spec_min?: number | null;
  spec_max?: number | null;
}

export interface TableDefinition {
  columns: GridColumn[];
  rows: GridRow[];
}

export interface ItemSpec {
  unit?: string | null;
  spec_min?: number | null;
  spec_max?: number | null;
  spec_text?: string | null;
}

export const SPEC_KEYS = ["unit", "spec_min", "spec_max", "spec_text"] as const;

export const columnKind = (column: GridColumn) => column.kind ?? "input";

/** "<b>Bore</b>&nbsp;diameter" -> "Bore diameter" */
export const plainText = (value: unknown): string => {
  const raw = String(value ?? "");
  if (!/[<&]/.test(raw)) return raw.trim();
  // an inert document: nothing in the markup loads or runs (a detached <div> would fire <img onerror>)
  const doc = new DOMParser().parseFromString(raw, "text/html");
  return (doc.body.textContent ?? "").replace(/\s+/g, " ").trim();
};

export const fieldName = (item: LayoutItem) => (typeof item.field_name === "string" ? item.field_name : "");

/** The earlier table element (columns printed or recorded, limits per row). Still rendered; no longer offered. */
export const isTableGrid = (item: LayoutItem) => item.element === "CustomElement" && item.key === "TableGrid";

/** The designer's Table / Grid: heading rows, merged cells, printed text and input cells (vendor table-model.js). */
export const isTable = (item: LayoutItem) => item.element === "Table";

/** Records a single value (a table records one per input cell). */
export const isRecordable = (item: LayoutItem) =>
  !!item.element &&
  !!fieldName(item) &&
  !PRESENTATION.has(String(item.element).toLowerCase()) &&
  !isTableGrid(item) &&
  !isTable(item);

/** The record value key of a Table cell; the backend's form_layout.add_table writes the same. */
export const tableCellKey = (item: LayoutItem, rowKey: string, columnKey: string) => `${fieldName(item)}:${rowKey}:${columnKey}`;

/** Field Properties -> Appearance -> Field width. */
export const FIELD_WIDTH_OPTIONS = [
  { value: "", label: "Auto (full width)", css: "100%" },
  { value: "two_thirds", label: "Two thirds", css: "66.666%" },
  { value: "half", label: "Half", css: "50%" },
  { value: "third", label: "One third", css: "33.333%" },
  { value: "quarter", label: "Quarter", css: "25%" },
] as const;

export const fieldWidth = (item: LayoutItem) =>
  FIELD_WIDTH_OPTIONS.find((o) => o.value && o.value === item.field_width)?.css;

export const isNumberItem = (item: LayoutItem) => NUMBER_ELEMENTS.has(String(item.element));

/** The builder's display name for an element type. */
export const elementLabel = (item: LayoutItem) =>
  ({
    NumberInput: "Number",
    TextInput: "Text",
    TextArea: "Multi-line text",
    Dropdown: "Dropdown",
    RadioButtons: "Radio buttons",
    Checkboxes: "Checkboxes",
    DatePicker: "Date",
    EmailInput: "Email",
    PhoneNumber: "Phone",
    Tags: "Tags",
    Range: "Range",
    Rating: "Rating",
    Camera: "Camera",
    FileUpload: "File upload",
  })[String(item.element)] ?? String(item.element);

const numberOrNull = (value: unknown) =>
  value === null || value === undefined || value === "" || Number.isNaN(Number(value)) ? null : Number(value);

const pickSpec = (item: LayoutItem): ItemSpec => ({
  unit: (item.unit as string) ?? null,
  spec_min: numberOrNull(item.spec_min),
  spec_max: numberOrNull(item.spec_max),
  spec_text: (item.spec_text as string) ?? null,
});

const pickTable = (item: LayoutItem): TableDefinition => {
  const grid = (item.table_grid ?? {}) as Partial<TableDefinition>;
  return {
    columns: ((item.columns as GridColumn[]) ?? grid.columns ?? []).map((c) => ({ ...c })),
    rows: ((item.rows as GridRow[]) ?? grid.rows ?? []).map((r) => ({ ...r })),
  };
};

/** Limits already saved on the layout, by field name. */
export const readSpecs = (layout: LayoutItem[]): Record<string, ItemSpec> =>
  Object.fromEntries(layout.filter(isRecordable).map((item) => [fieldName(item), pickSpec(item)]));

/** Table definitions already saved on the layout, by field name. */
export const readTables = (layout: LayoutItem[]): Record<string, TableDefinition> =>
  Object.fromEntries(layout.filter(isTableGrid).map((item) => [fieldName(item), pickTable(item)]));

/**
 * The layout to save: the builder's items with the limits and table
 * definitions the designer keeps outside the builder's own store.
 */
export const mergeLayout = (
  layout: LayoutItem[],
  specs: Record<string, ItemSpec>,
  tables: Record<string, TableDefinition>,
): LayoutItem[] =>
  layout.map((item) => {
    const name = fieldName(item);
    const table = tables[name];
    if (isTableGrid(item) && table) {
      return { ...item, columns: table.columns, rows: table.rows, table_grid: table };
    }
    const spec = specs[name];
    if (isRecordable(item) && spec) {
      const cleaned = Object.fromEntries(SPEC_KEYS.map((key) => [key, spec[key] === "" ? null : (spec[key] ?? null)]));
      return { ...item, ...cleaned };
    }
    return item;
  });

/** One-line description of a limit, the way the record shows it. */
export const specSummary = (spec?: ItemSpec | GridRow | null) => {
  if (!spec) return "";
  const unit = spec.unit ? ` ${spec.unit}` : "";
  const min = spec.spec_min ?? null;
  const max = spec.spec_max ?? null;
  if (min !== null && max !== null) return `${min} – ${max}${unit}`;
  if (min !== null) return `≥ ${min}${unit}`;
  if (max !== null) return `≤ ${max}${unit}`;
  return "spec_text" in spec && spec.spec_text ? `= ${spec.spec_text}` : "";
};
