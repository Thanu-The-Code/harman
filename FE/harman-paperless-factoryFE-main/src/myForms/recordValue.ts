import type { RecordValue } from "../api/records.api";

/** What the person has typed but not yet saved, by value id. */
export type Edits = Record<string, { value?: string; remark?: string }>;

export const currentValue = (v: RecordValue, edits: Edits) => edits[v.id]?.value ?? v.value ?? "";
export const currentRemark = (v: RecordValue, edits: Edits) => edits[v.id]?.remark ?? v.remark ?? "";

/**
 * Was this reading within specification? Mirrors `record_service.evaluate`
 * in the backend so the answer shows while typing; the server's verdict
 * replaces it once the reading is saved.
 */
export const evaluate = (v: RecordValue, raw: string): boolean | null => {
  const hasNumeric = v.spec_min !== null || v.spec_max !== null;
  if (!hasNumeric && !v.spec_text) return null;
  if (hasNumeric) {
    if (raw.trim() === "" || Number.isNaN(Number(raw))) return null;
    const n = Number(raw);
    if (v.spec_min !== null && n < v.spec_min) return false;
    if (v.spec_max !== null && n > v.spec_max) return false;
    return true;
  }
  const given = raw.trim().toLowerCase();
  return given ? given === (v.spec_text ?? "").trim().toLowerCase() : null;
};

/** The verdict to show: the server's for saved readings, the local one for edits. */
export const verdict = (v: RecordValue, edits: Edits): boolean | null =>
  edits[v.id]?.value !== undefined ? evaluate(v, edits[v.id].value ?? "") : v.in_spec;

export const isBlank = (v: RecordValue, edits: Edits) => currentValue(v, edits).trim() === "";
