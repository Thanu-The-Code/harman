// Types for table-model.js (the Table element's grid model; see the comment at its top).
export type TableCellInput = "text" | "number" | "date" | "check";

export interface TableCell {
  text?: string;
  input?: TableCellInput;
  covered?: boolean;
  rowspan?: number;
  colspan?: number;
  /** limits on a number cell (the designer's extension) */
  spec_min?: number | null;
  spec_max?: number | null;
  unit?: string | null;
  required?: boolean;
}

export interface TableColumn {
  key: string;
  text: string;
  title?: string;
}

export interface TableElementLike {
  /** printed for information only (a revision history): nothing in it is filled in */
  reference?: boolean;
  columns?: TableColumn[];
  header?: (TableCell | string)[][];
  rows?: { key: string; cells: (TableCell | string)[] }[];
}

export const INPUT_TYPES: TableCellInput[];
export const CHECK_VALUES: string[];
export function normalizeCell(cell: TableCell | string | null | undefined): TableCell;
export function isInput(cell: TableCell | string | null | undefined): boolean;
export function inputType(cell: TableCell | string | null | undefined): TableCellInput;
export function headerGrid(element: TableElementLike): TableCell[][];
export function bodyGrid(element: TableElementLike): TableCell[][];
export function ensureGrids<T extends TableElementLike>(element: T): T;
