import { InputAdornment, MenuItem, TextField, ToggleButton, ToggleButtonGroup } from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutlineOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import type { RecordValue } from "../api/records.api";
import { currentRemark, currentValue, verdict, type Edits } from "./recordValue";

interface Props {
  value: RecordValue;
  edits: Edits;
  onChange: (id: string, patch: { value?: string; remark?: string }) => void;
  readOnly?: boolean;
  /** Overrides the record's label (a layout item's own label). */
  label?: string;
  /** The designer's placeholder for this entry. */
  placeholder?: string;
}

const OK_NOK = ["OK", "N-OK"];

/** One reading on a record: the input for its type, its limit, and whether it meets it. */
/** One entry outside a table (inside a table: ValueCell). */
const ValueField = ({ value: v, edits, onChange, readOnly, label, placeholder }: Props) => {
  const raw = currentValue(v, edits);
  // the backend's rule (missing_required): the entry's own Required flag decides
  const required = v.required;
  const ok = verdict(v, edits);
  const outOfSpec = ok === false;
  const set = (next: string) => onChange(v.id, { value: next });
  const size = "small" as const;

  // the backend writes "-" when there is no limit
  const helper = [v.spec_label && !["-", "—"].includes(v.spec_label) ? `Spec: ${v.spec_label}` : "", v.help_text ?? ""]
    .filter(Boolean)
    .join(" · ");

  let input;
  if (v.field_type === "boolean") {
    input = (
      <ToggleButtonGroup
        exclusive
        size={size}
        value={raw.toLowerCase() || null}
        onChange={(_, next: string | null) => !readOnly && set(next ?? "")}
        aria-label={v.label}
        disabled={readOnly}
      >
        <ToggleButton value="yes">Yes</ToggleButton>
        <ToggleButton value="no">No</ToggleButton>
      </ToggleButtonGroup>
    );
  } else if (v.field_type === "select") {
    const options = v.options?.length ? v.options : OK_NOK;
    input = (
      <TextField
        select
        size={size}
        fullWidth
        value={options.includes(raw) ? raw : ""}
        onChange={(e) => set(e.target.value)}
        disabled={readOnly}
        error={outOfSpec}
        slotProps={{ htmlInput: { "aria-label": v.label } }}
      >
        <MenuItem value="">
          <em>Select</em>
        </MenuItem>
        {options.map((o) => (
          <MenuItem key={o} value={o}>
            {o}
          </MenuItem>
        ))}
      </TextField>
    );
  } else {
    input = (
      <TextField
        size={size}
        fullWidth
        type={v.field_type === "number" ? "number" : v.field_type === "date" ? "date" : "text"}
        value={raw}
        onChange={(e) => set(e.target.value)}
        disabled={readOnly}
        error={outOfSpec}
        placeholder={placeholder || "Enter"}
        slotProps={{
          htmlInput: { "aria-label": v.label, step: "any" },
          input: v.unit ? { endAdornment: <InputAdornment position="end">{v.unit}</InputAdornment> } : undefined,
        }}
      />
    );
  }

  const badge =
    ok === null ? null : ok ? (
      <span className="spec-badge ok" title="Within specification">
        <CheckCircleOutlineIcon fontSize="inherit" /> OK
      </span>
    ) : (
      <span className="spec-badge nok" title="Outside specification">
        <ErrorOutlineIcon fontSize="inherit" /> N-OK
      </span>
    );

  return (
    <div className={`value-field ${outOfSpec ? "nok" : ""}`}>
      <div className="field-label">
        {label ?? v.label}
        {required && <span className="required-mark"> *</span>}
        {badge}
      </div>
      {input}
      {helper && <div className="field-helper">{helper}</div>}
      {(outOfSpec || currentRemark(v, edits)) && (
        <TextField
          size="small"
          fullWidth
          className="remark-input"
          placeholder="Remark (what was seen, action taken)"
          value={currentRemark(v, edits)}
          onChange={(e) => onChange(v.id, { remark: e.target.value })}
          disabled={readOnly}
        />
      )}
    </div>
  );
};

export default ValueField;
