import { api } from "./baseApi";
import type { LayoutItem } from "./formats.api";

/**
 * Document digitisation (BE /api/ocr, app/ocr): an Excel workbook, PDF or image
 * of a form becomes template elements for the designer.
 */

export type OcrCapability = "template" | "extract" | "digitize" | "read_form" | "export";

export interface DocumentFormat {
  key: string;
  label: string;
  extensions: string[];
  mime_types: string[];
  capabilities: OcrCapability[];
}

export interface OcrFormats {
  formats: DocumentFormat[];
  /** False when the server has no OCR engine: Excel only. */
  ocr_available: boolean;
  ocr_unavailable_reason: string | null;
}

/** What was read off one page (or one Excel sheet); positions are fractions of the page. */
export interface OcrPage {
  index: number;
  width: number;
  height: number;
  sheet?: string;
  image: string | null;
  lines: { text: string; conf: number; bbox: number[] }[];
  checkboxes: { bbox: number[]; kind: "checkbox" | "radio"; checked: boolean }[];
  tables: { bbox: number[]; n_rows: number; n_cols: number; cells: unknown[] }[];
  text: string;
}

export interface OcrDocument {
  pages: OcrPage[];
  text: string;
}

export interface OcrTemplate {
  task_data: LayoutItem[];
  /** Counts of what was detected: field, choice, table, static, image. */
  stats: Partial<Record<"field" | "choice" | "table" | "static" | "image", number>>;
  document: OcrDocument;
  /** The text that reads as the form's title (backend app/ocr/title.py), if any. */
  title?: string | null;
}

export const ocrApi = api.injectEndpoints({
  endpoints: (build) => ({
    ocrFormats: build.query<OcrFormats, void>({
      query: () => ({ url: "api/ocr/formats" }),
    }),
    templateFromDocument: build.mutation<OcrTemplate, File>({
      query: (file) => {
        const data = new FormData();
        data.append("file", file, file.name);
        return { url: "api/ocr/template", method: "POST", data };
      },
    }),
  }),
});

export const { useOcrFormatsQuery, useTemplateFromDocumentMutation } = ocrApi;

/** Formats that support a capability. */
export const formatsFor = (formats: DocumentFormat[] = [], capability: OcrCapability) =>
  formats.filter((f) => f.capabilities.includes(capability));

/** For <input type="file" accept>. */
export const acceptFor = (formats: DocumentFormat[]) => formats.flatMap((f) => [...f.extensions, ...f.mime_types]).join(",");

export const describeFormats = (formats: DocumentFormat[]) =>
  formats.map((f) => `${f.label} (${f.extensions.join(", ")})`).join(", ");

export const isAccepted = (file: File, formats: DocumentFormat[]) => {
  const name = file.name.toLowerCase();
  return formats.some((f) => f.extensions.some((ext) => name.endsWith(ext)));
};

/** "Detected 4 input fields, 1 table and 8 text blocks." */
export const describeDetection = (stats: OcrTemplate["stats"]) => {
  const parts = (
    [
      [stats.field, "input field"],
      [stats.choice, "tick-box group"],
      [stats.table, "table"],
      [stats.static, "text block"],
      [stats.image, "picture"],
    ] as const
  )
    .filter(([n]) => n)
    .map(([n, name]) => `${n} ${name}${n! > 1 ? "s" : ""}`);
  if (!parts.length) return "Nothing recognisable was found.";
  const last = parts.pop();
  return `Detected ${parts.length ? `${parts.join(", ")} and ${last}` : last}.`;
};
