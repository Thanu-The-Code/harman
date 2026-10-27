/* eslint-disable react-hooks/immutability -- the builder hands the edit form its own element
   object and saves that same object (vendor preview.jsx updateElement), so the panel changes
   it in place, as the builder's own edit form does. */
import { useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { IconButton, MenuItem, Switch, TextField } from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
import CheckIcon from "@mui/icons-material/Check";
import AddIcon from "@mui/icons-material/Add";
import FormatListBulletedIcon from "@mui/icons-material/FormatListBulleted";
import { ElementStore, type EditFormProps } from "../../vendor/react-form-builder";
import type { LayoutItem } from "../../api/formats.api";
import { elementTitle } from "./palette";
import { FIELD_WIDTH_OPTIONS, plainText } from "./layoutUtils";
import { RichTextEditor } from "./richText";
import TableLayoutSection from "./TableLayoutSection";
import type { TableElementLike } from "../../vendor/react-form-builder/table-model";

/**
 * Field Properties (Figma: Document create, Field Properties tab): the selected
 * element's settings. Changes are written into the element and saved to the canvas
 * shortly after typing stops (straight away for switches and lists).
 */

interface Option {
  value: string;
  text: string;
  key: string;
}

type Element = LayoutItem & {
  id: string;
  element: string;
  dirty?: boolean;
  options?: Option[];
};

const TEXT_ELEMENTS = new Set(["Header", "Label", "Paragraph"]);
const PLACEHOLDER_ELEMENTS = new Set(["TextInput", "EmailInput", "PhoneNumber", "NumberInput", "TextArea"]);
const OPTION_ELEMENTS = new Set(["Dropdown", "Tags", "Checkboxes", "RadioButtons"]);
const SINGLE_CHOICE = new Set(["Dropdown", "RadioButtons", "Checkboxes"]);
const NO_FIELD = new Set(["Header", "Label", "Paragraph", "LineBreak", "HyperLink", "Download", "Image", "FieldSet",
  "TwoColumnRow", "ThreeColumnRow", "MultiColumnRow"]);
const OPTION_COLORS = ["#10b981", "#f59e0b", "#3b82f6", "#ef4444", "#8b5cf6", "#14b8a6"];

// the builder's own keys look like "dropdown_D2AA0FE5-CDAE-4028-..."
const KEY_RE = /^[A-Za-z][A-Za-z0-9_-]*$/;
const escapeHtml = (text: string) => text.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
const slug = (text: string) => text.replace(/[^A-Za-z0-9]+/g, "_").toLowerCase();
const numberOrNull = (value: string) => (value.trim() === "" || Number.isNaN(Number(value)) ? null : Number(value));

/* ------------------------------------------------------------ layout pieces */

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="fp-section">
    <h4 className="fp-section-title">{title}</h4>
    {children}
  </section>
);

const Labelled = ({ label, required, children, hint }: { label: string; required?: boolean; children: ReactNode; hint?: string }) => (
  <div className="fp-field">
    <div className="fp-label">
      {label}
      {required && <span className="fp-required"> *</span>}
    </div>
    {children}
    {hint && <div className="fp-hint">{hint}</div>}
  </div>
);

/* ------------------------------------------------------------ options */

const OptionList = ({ el, set }: { el: Element; set: (patch: Partial<Element>, now?: boolean) => void }) => {
  const [adding, setAdding] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const options = el.options ?? [];
  const prefix = `${String(el.element).toLowerCase()}_option_`;
  const noun = el.element === "Dropdown" ? "dropdown option" : "option";

  const add = () => {
    const text = adding.trim();
    if (!text) return;
    set({ options: [...options, { value: slug(text) || `option_${options.length + 1}`, text, key: prefix + crypto.randomUUID() }] }, true);
    setAdding("");
  };
  const save = (key: string) => {
    const text = draft.trim();
    if (text) set({ options: options.map((o) => (o.key === key ? { ...o, text, value: slug(text) || o.value } : o)) }, true);
    setEditing(null);
  };

  return (
    <Section title="Option">
      <div className="fp-label">Add {noun}</div>
      <ul className="fp-options">
        {options.map((o, i) => (
          <li key={o.key}>
            <FormatListBulletedIcon className="fp-option-grip" fontSize="small" />
            <div className="fp-option-text">
              <span className="fp-dot" style={{ background: OPTION_COLORS[i % OPTION_COLORS.length] }} />
              {editing === o.key ? (
                <input
                  autoFocus
                  value={draft}
                  aria-label={`Rename ${o.text}`}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && save(o.key)}
                  onBlur={() => save(o.key)}
                />
              ) : (
                <span>{o.text}</span>
              )}
            </div>
            <IconButton
              size="small"
              className="fp-icon-btn"
              aria-label={editing === o.key ? `Save ${o.text}` : `Edit ${o.text}`}
              onClick={() => (editing === o.key ? save(o.key) : (setEditing(o.key), setDraft(o.text)))}
            >
              {editing === o.key ? <CheckIcon fontSize="small" /> : <EditOutlinedIcon fontSize="small" />}
            </IconButton>
            <IconButton
              size="small"
              className="fp-icon-btn"
              aria-label={`Delete ${o.text}`}
              disabled={options.length <= 1}
              onClick={() => set({ options: options.filter((x) => x.key !== o.key) }, true)}
            >
              <DeleteOutlinedIcon fontSize="small" />
            </IconButton>
          </li>
        ))}
      </ul>
      <div className="fp-option-add">
        <input
          value={adding}
          placeholder="Add option"
          aria-label="New option"
          onChange={(e) => setAdding(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <button type="button" className="fp-add-btn" onClick={add} disabled={!adding.trim()}>
          <AddIcon fontSize="small" /> Add
        </button>
      </div>
    </Section>
  );
};

/* ------------------------------------------------------------ the panel */

const FieldProperties = ({ element, updateElement, manualEditModeOff }: EditFormProps) => {
  const el = element as Element;
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  const [open, setOpen] = useState(true);
  const [keyDraft, setKeyDraft] = useState<string>(String(el.field_name ?? ""));
  const timer = useRef<number | undefined>(undefined);

  const commit = () => {
    window.clearTimeout(timer.current);
    if (el.dirty) {
      el.dirty = false;
      updateElement(el);
    }
  };
  /** Write into the element; save now (lists, switches) or once typing pauses. */
  const set = (patch: Partial<Element>, now = false) => {
    Object.assign(el, patch);
    el.dirty = true;
    rerender();
    window.clearTimeout(timer.current);
    if (now) commit();
    else timer.current = window.setTimeout(commit, 300);
  };

  // the panel closing (it is keyed by element, so choosing another one closes this one): save what was typed
  useEffect(
    () => () => commit(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const kind = el.element;
  const isText = TEXT_ELEMENTS.has(kind);
  const isField = !NO_FIELD.has(kind) && !el.static;
  const options = el.options ?? [];
  // the backend's rule (form_layout.to_fields): a field judged against a limit is always required
  const judged = el.spec_min != null || el.spec_max != null || !!el.spec_text;

  const otherKeys = new Set(
    (ElementStore.state.data ?? []).filter((x) => x && x.id !== el.id).map((x) => String(x.field_name ?? "")),
  );
  const keyError = !KEY_RE.test(keyDraft)
    ? "Letters, digits, _ and - only, starting with a letter"
    : otherKeys.has(keyDraft)
      ? "Another field already uses this key"
      : "";

  return (
    <div className="field-properties" data-rfb-keep-edit>
      <button type="button" className="fp-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{elementTitle(el)} Field</span>
        {open ? <KeyboardArrowUpIcon fontSize="small" /> : <KeyboardArrowDownIcon fontSize="small" />}
      </button>

      {open && (
        <>
          {isText && (
            <Section title="Content">
              <RichTextEditor
                elementId={el.id}
                html={String(el.content ?? "")}
                label="Text content"
                onChange={(html) => set({ content: html })}
              />
              <div className="fp-hint">Select text and use the toolbar above the page to format it.</div>
            </Section>
          )}

          {isField && (
            <Section title="Basic Setting">
              <Labelled label="Field Label" required>
                <TextField
                  size="small"
                  fullWidth
                  value={plainText(el.label)}
                  placeholder="Status"
                  slotProps={{ htmlInput: { "aria-label": "Field label" } }}
                  onChange={(e) => set({ label: escapeHtml(e.target.value) })}
                  onBlur={commit}
                />
              </Labelled>
              <Labelled label="Field Name(Key)" required hint={keyError || "How readings of this field are stored. Change it only before release."}>
                <TextField
                  size="small"
                  fullWidth
                  value={keyDraft}
                  error={!!keyError}
                  slotProps={{ htmlInput: { "aria-label": "Field key" } }}
                  onChange={(e) => {
                    const next = e.target.value.trim();
                    setKeyDraft(next);
                    if (KEY_RE.test(next) && !otherKeys.has(next)) set({ field_name: next });
                  }}
                  onBlur={commit}
                />
              </Labelled>
              {PLACEHOLDER_ELEMENTS.has(kind) && (
                <Labelled label="Placeholder">
                  <TextField
                    size="small"
                    fullWidth
                    value={String(el.placeholder ?? "")}
                    placeholder="Shown in the empty box, e.g. Enter the batch number"
                    slotProps={{ htmlInput: { "aria-label": "Placeholder" } }}
                    onChange={(e) => set({ placeholder: e.target.value })}
                    onBlur={commit}
                  />
                </Labelled>
              )}
              <div className="fp-switch-row">
                <span className="fp-label">
                  Required Field<span className="fp-required"> *</span>
                </span>
                <Switch
                  size="small"
                  checked={!!el.required || judged}
                  disabled={judged}
                  slotProps={{ input: { "aria-label": "Required field" } }}
                  onChange={(e) => set({ required: e.target.checked }, true)}
                />
              </div>
              {judged && <div className="fp-hint">Always required: it has a limit or a conforming value.</div>}
            </Section>
          )}

          {OPTION_ELEMENTS.has(kind) && <OptionList el={el} set={set} />}

          {isField && kind !== "Table" && kind !== "Signature" && kind !== "Camera" && kind !== "FileUpload" && (
            <Section title="Default Value">
              {SINGLE_CHOICE.has(kind) ? (
                <TextField
                  select
                  size="small"
                  fullWidth
                  value={options.some((o) => o.text === el.default_value) ? String(el.default_value) : ""}
                  slotProps={{ htmlInput: { "aria-label": "Default value" }, select: { displayEmpty: true } }}
                  onChange={(e) => set({ default_value: e.target.value || null }, true)}
                >
                  <MenuItem value="">None</MenuItem>
                  {options.map((o) => (
                    <MenuItem key={o.key} value={o.text}>
                      {o.text}
                    </MenuItem>
                  ))}
                </TextField>
              ) : (
                <TextField
                  size="small"
                  fullWidth
                  type={kind === "NumberInput" ? "number" : kind === "DatePicker" ? "date" : "text"}
                  value={String(el.default_value ?? "")}
                  placeholder="None"
                  slotProps={{ htmlInput: { "aria-label": "Default value" } }}
                  onChange={(e) => set({ default_value: e.target.value || null })}
                  onBlur={commit}
                />
              )}
            </Section>
          )}

          {isField && kind !== "Table" && (
            <Section title="Validation">
              {kind === "NumberInput" && (
                <Labelled label="Specification limits" hint="A reading outside them makes the record N-OK and flags the Overall Process Owner.">
                  <div className="fp-limits">
                    <TextField
                      size="small"
                      type="number"
                      placeholder="Min"
                      value={el.spec_min ?? ""}
                      slotProps={{ htmlInput: { "aria-label": "Minimum", step: "any" } }}
                      onChange={(e) => set({ spec_min: numberOrNull(e.target.value) })}
                      onBlur={commit}
                    />
                    <TextField
                      size="small"
                      type="number"
                      placeholder="Max"
                      value={el.spec_max ?? ""}
                      slotProps={{ htmlInput: { "aria-label": "Maximum", step: "any" } }}
                      onChange={(e) => set({ spec_max: numberOrNull(e.target.value) })}
                      onBlur={commit}
                    />
                    <TextField
                      size="small"
                      placeholder="Unit"
                      value={String(el.unit ?? "")}
                      slotProps={{ htmlInput: { "aria-label": "Unit" } }}
                      onChange={(e) => set({ unit: e.target.value || null })}
                      onBlur={commit}
                    />
                  </div>
                </Labelled>
              )}
              {SINGLE_CHOICE.has(kind) && (
                <Labelled label="Conforming value" hint="Any other answer makes the record N-OK.">
                  <TextField
                    select
                    size="small"
                    fullWidth
                    value={options.some((o) => o.text === el.spec_text) ? String(el.spec_text) : ""}
                    slotProps={{ htmlInput: { "aria-label": "Conforming value" }, select: { displayEmpty: true } }}
                    onChange={(e) => set({ spec_text: e.target.value || null }, true)}
                  >
                    <MenuItem value="">Any answer is fine</MenuItem>
                    {options.map((o) => (
                      <MenuItem key={o.key} value={o.text}>
                        {o.text}
                      </MenuItem>
                    ))}
                  </TextField>
                </Labelled>
              )}
              <Labelled label="Show Error Message">
                <TextField
                  size="small"
                  fullWidth
                  value={String(el.error_message ?? "")}
                  placeholder="Shown when the entry is missing or wrong"
                  slotProps={{ htmlInput: { "aria-label": "Error message" } }}
                  onChange={(e) => set({ error_message: e.target.value || null })}
                  onBlur={commit}
                />
              </Labelled>
            </Section>
          )}

          {kind === "Table" && (
            <Section title="Table layout">
              <TableLayoutSection element={el as TableElementLike} onChange={() => set({})} onStructureChange={() => set({}, true)} onCommit={commit} />
            </Section>
          )}

          {kind === "Image" && (
            <Section title="Image">
              <Labelled label="Image address" hint="Or choose a picture file; it is kept inside the template.">
                <TextField
                  size="small"
                  fullWidth
                  value={String(el.src ?? "").startsWith("data:") ? "(uploaded picture)" : String(el.src ?? "")}
                  slotProps={{ htmlInput: { "aria-label": "Image address" } }}
                  onChange={(e) => set({ src: e.target.value })}
                  onBlur={commit}
                />
              </Labelled>
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif"
                aria-label="Choose a picture"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = () => set({ src: String(reader.result) }, true);
                  reader.readAsDataURL(file);
                }}
              />
            </Section>
          )}

          {kind === "HyperLink" && (
            <Section title="Link">
              <Labelled label="Text">
                <TextField size="small" fullWidth value={plainText(el.content)} onChange={(e) => set({ content: escapeHtml(e.target.value) })} onBlur={commit} />
              </Labelled>
              <Labelled label="Address">
                <TextField size="small" fullWidth value={String(el.href ?? "")} onChange={(e) => set({ href: e.target.value })} onBlur={commit} />
              </Labelled>
            </Section>
          )}

          {kind !== "LineBreak" && (
            <Section title="Appearance">
              <Labelled label="Field width">
                <TextField
                  select
                  size="small"
                  fullWidth
                  value={String(el.field_width ?? "")}
                  slotProps={{ htmlInput: { "aria-label": "Field width" }, select: { displayEmpty: true } }}
                  onChange={(e) => set({ field_width: e.target.value || null }, true)}
                >
                  {FIELD_WIDTH_OPTIONS.map((o) => (
                    <MenuItem key={o.value} value={o.value}>
                      {o.label}
                    </MenuItem>
                  ))}
                </TextField>
              </Labelled>
            </Section>
          )}

          <div className="fp-footer">
            <button type="button" className="fp-done" onClick={() => (commit(), manualEditModeOff())}>
              Done
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default FieldProperties;
