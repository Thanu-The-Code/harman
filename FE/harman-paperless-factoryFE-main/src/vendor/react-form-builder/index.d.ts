/* eslint-disable max-classes-per-file */
// Types for the vendored form builder (index.jsx). Kept beside it so `import ... from "vendor/react-form-builder"`
// is typed; the host app's own element shape is LayoutItem (src/api/formats.api.ts).
import * as React from 'react';

type BaseElement = {
  id: string;
  element:
    | "Header Text"
    | "Label"
    | "Paragraph"
    | "Line Break"
    | "Dropdown"
    | "Tags"
    | "Checkboxes"
    | "Multiple Choice"
    | "Text Input"
    | "Number Input"
    | "Multi-line Input"
    | "Two Column Row"
    | "Three Column Row"
    | "Multi Column Row"
    | "Image"
    | "Rating"
    | "Date"
    | "Signature"
    | "Web site"
    | "Fieldset"
    | "File Attachment"
    | "Range"
    | "Camera"
    | "Table";
  showDescription?: boolean;
  required: boolean;
  canHaveAlternateForm: boolean;
  canHaveDisplayHorizontal: boolean;
  canHaveOptionCorrect: boolean;
  canHaveOptionValue: boolean;
  canHavePageBreakBefore: boolean;
  canPopulateFromApi: boolean;
  text: string;
};
export type StaticElement = {
  bold: boolean;
  content: string;
  inline?: boolean;
  italic: boolean;
  static: true;
};
export type FormBuilderInput = {
  canHaveAnswer?: true;
  field_name: string;
  label: string;
};
export type Option = {
  key: string;
  label?: string;
  text: string;
  value: string;
};
export type SelectableElement = {
  options: Option[];
} & FormBuilderInput;
export type ImageElement = {
  field_name: string;
  src: string;
};
export type DateElement = {
  dateFormat: string;
  defaultToday: boolean;
  readOnly: boolean;
  showTimeSelect: boolean;
  showTimeSelectOnly: boolean;
  showTimeInput: boolean;
  timeFormat: string;
} & FormBuilderInput;
export type RangeElement = {
  max_label: string;
  max_value: number;
  min_label: string;
  min_value: number;
} & FormBuilderInput;
export type FileElement = {
  _href: string;
  file_path: string;
  field_name: string;
} & StaticElement;
export type WebsiteElement = {
  href: string;
} & StaticElement;
export type SignatureElement = {
  readOnly: boolean;
} & FormBuilderInput;
export type TableColumn = { key: string; text: string; title?: string };
/** A table cell: fixed text, an input of some type, or hidden under a neighbour's span. */
export type TableCell =
  | string // legacy: '' = text input, anything else = fixed text
  | ({ text: string } | { input: "text" | "number" | "date" | "check" } | { covered: true }) & {
      rowspan?: number;
      colspan?: number;
    };
export type TableRow = { key: string; cells: TableCell[] };
export type TableElement = {
  columns: TableColumn[];
  /** Heading rows (default: one row of column texts). */
  header?: TableCell[][];
  rows: TableRow[];
} & FormBuilderInput;
/** Where an element's value lives in the source workbook (templates made from Excel). */
export type ExcelMeta = {
  sheet: string;
  cell?: string;
  label_cell?: string | null;
  inline?: boolean;
  cells?: (string | null)[][];
};
/** Position info added to elements generated from an image (normalised 0..1 coordinates). */
export type OcrMeta = {
  page: number;
  page_size: [number, number];
  bbox?: [number, number, number, number];
  label_text?: string;
  label_bbox?: [number, number, number, number] | null;
  value_bbox?: [number, number, number, number];
};
export type TaskData = BaseElement & { ocr?: OcrMeta; excel?: ExcelMeta } &
  (| StaticElement
    | FormBuilderInput
    | SelectableElement
    | ImageElement
    | DateElement
    | RangeElement
    | WebsiteElement
    | FileElement
    | SignatureElement
    | TableElement
    // eslint-disable-next-line no-use-before-define
    | FormBuilderLayout
  );
export type FormBuilderLayout = {
  isContainer: true;
  childItems: TaskData[];
  field_name: string;
};
export type FormBuilderPostData = {
  task_data: TaskData[];
};

export type ToolbarItem = {
  key: string;
  name: string;
  static: boolean;
  icon: string;
  content: string;
};

export interface FormBuilderProps {
  toolbarItems?: ToolbarItem[];
  files?: any[];
  locale?: string;
  url?: string;
  showCorrectColumn?: boolean;
  show_description?: boolean;
  onLoad?: () => Promise<FormBuilderPostData>;
  onPost?: (data: FormBuilderPostData) => void;
  saveUrl?: string;
  saveAlways?: boolean;
  editMode?: boolean;
  renderEditForm?: (props: BaseElement) => React.ReactNode;
}

export class ReactFormBuilder extends React.Component<FormBuilderProps> {}

export interface FormGeneratorOnSubmitParams {
  id: number;
  name: string;
  custom_name: string;
  value: string | string[];
}

export interface FormGeneratorProps {
  form_action: string;
  form_method: string;
  action_name?: string;
  onBlur?: (info: FormGeneratorOnSubmitParams[]) => void;
  onSubmit?: (info: FormGeneratorOnSubmitParams[]) => void;
  onChange?: (info: FormGeneratorOnSubmitParams[]) => void;
  data: any[];
  back_action?: string;
  back_name?: string;
  locale?: string;
  task_id?: number;
  answer_data?: any[];
  authenticity_token?: string;
  hide_actions?: boolean;
  skip_validations?: boolean;
  option_key_value?: 'key' | 'value';
  download_path?: string;
  display_short?: boolean;
  read_only?: boolean;
  // eslint-disable-next-line no-undef
  variables?: Record<any, any>;
  submitButton?: React.JSX.Element;
  /** Receives { getValues() } once mounted: the current values as answer_data ({ field_name: value }). */
  apiRef?: { current: { getValues(): Record<string, unknown> } | null };
}

export class ReactFormGenerator extends React.Component<FormGeneratorProps> {}

export type ActionType = "load" | "updateOrder" | "delete" | "create";

/** The builder's element store (one per page): the canvas, palette and host share it. */
export const ElementStore: {
  state: { data: any[] };
  dispatch: (type: ActionType, data: any) => void;
  subscribe: (callback: (state: { data: any[] }) => void) => boolean;
  unsubscribe: (callback: (state: { data: any[] }) => void) => void;
};

export class Registry {
  /** A custom element's component, looked up by key when a saved layout is rendered. */
  static register: (name: string, component: React.ComponentType<any>) => void;

  static list: () => string[];

  static get: (name: string) => React.ComponentType<any> | undefined;
}

/** Props the canvas passes to `renderEditForm` (the designer's Field Properties panel). */
export interface EditFormProps {
  element: any;
  updateElement: (element: any) => void;
  manualEditModeOff: () => void;
  preview: unknown;
  files: any[];
  showCorrectColumn: boolean;
}

export function BuilderProvider(props: { locale?: string; children: React.ReactNode }): React.JSX.Element;

export interface PreviewProps {
  data?: any[];
  className?: string;
  editMode: boolean;
  editElement: any | null;
  editModeOn: (data: any, e: React.SyntheticEvent) => void;
  manualEditModeOff: () => void;
  parent: unknown;
  registry: typeof Registry;
  variables?: Record<string, unknown>;
  onPost?: (data: { task_data: any[] }) => void;
  saveAlways?: boolean;
  renderEditForm?: (props: EditFormProps) => React.ReactNode;
  /** Render the edit form into this element instead of above the canvas. */
  editFormContainer?: HTMLElement | null;
  files?: any[];
  showCorrectColumn?: boolean;
}
export class Preview extends React.Component<PreviewProps> {}

export interface PaletteItem {
  key: string;
  name: string;
  /** Font Awesome class, or */
  icon?: string;
  /** a React icon of the host app */
  iconNode?: React.ReactNode;
  group_name?: string;
  [option: string]: unknown;
}
export const Toolbar: React.ComponentType<{ items?: PaletteItem[]; layout?: "list" | "tiles"; className?: string; show_description?: boolean }>;

export interface OcrFieldReport {
  id: string;
  field_name: string;
  label: string;
  element: string;
  value: unknown;
  confidence: number;
  method: "zone" | "label" | "cell" | "none";
}

export interface OcrDocument {
  pages: {
    index: number;
    width: number;
    height: number;
    image: string | null;
    lines: { text: string; conf: number; bbox: number[] }[];
    checkboxes: { bbox: number[]; kind: "checkbox" | "radio"; checked: boolean }[];
    tables: { bbox: number[]; n_rows: number; n_cols: number; cells: { row: number; col: number; rowspan: number; colspan: number; bbox: number[]; text: string }[] }[];
    text: string;
  }[];
  text: string;
}

export interface DocumentFormat {
  key: string;
  label: string;
  extensions: string[];
  mime_types: string[];
  capabilities: ("template" | "extract" | "digitize" | "read_form" | "export")[];
}

export interface OcrClient {
  health(): Promise<Record<string, unknown>>;
  formats(): Promise<DocumentFormat[]>;
  digitize(file: File): Promise<OcrDocument>;
  /** A filled-in document as an editable form plus the values read from it. */
  readForm(file: File): Promise<{ task_data: TaskData[]; stats: Record<string, number>; answers: Record<string, unknown>; fields: OcrFieldReport[]; document: OcrDocument }>;
  template(file: File): Promise<{ task_data: TaskData[]; stats: Record<string, number>; document: OcrDocument }>;
  extract(file: File, taskData: TaskData[]): Promise<{ answers: Record<string, unknown>; fields: OcrFieldReport[]; alignment: unknown[]; document: OcrDocument }>;
  /** The document with the form's values written in (formats with the "export" capability, e.g. Excel). */
  exportForm(file: File, taskData: TaskData[], answers: Record<string, unknown>): Promise<OcrExportResult>;
}

export interface OcrExportResult {
  filename: string;
  media_type: string;
  /** base64 */
  data: string;
  written: string[];
  skipped: { label: string; reason: string }[];
}

export function createOcrClient(baseUrl?: string, options?: { getHeaders?: () => Record<string, string> }): OcrClient;
export function loadIntoBuilder(taskData: TaskData[], mode?: "replace" | "append"): void;

export interface OcrDialogProps {
  baseUrl?: string;
  onClose: () => void;
}
export class OcrTemplateImport extends React.Component<OcrDialogProps & { onImport?: (taskData: TaskData[], mode: "replace" | "append") => void }> {}
export class OcrScanFill extends React.Component<OcrDialogProps & { data: TaskData[]; onApply: (answers: Record<string, unknown>, result: unknown) => void }> {}
export class OcrDigitize extends React.Component<OcrDialogProps & {
  /** "Edit as form" (default: load into the builder). */
  onEditForm?: (taskData: TaskData[], mode: "replace" | "append") => void;
  /** "Fill in values": shown when given; receives the form and the values read from the document. */
  onFillValues?: (taskData: TaskData[], answers: Record<string, unknown>, mode: "replace" | "append", result: unknown) => void;
}> {}
/** Save the form's values into a document (the workbook it came from, or another copy of the form). */
export class OcrExport extends React.Component<OcrDialogProps & { data: TaskData[]; answers: Record<string, unknown> }> {}
export class OcrDocumentView extends React.Component<{ document: OcrDocument; defaultMode?: "overlay" | "digital" | "text" }> {}
