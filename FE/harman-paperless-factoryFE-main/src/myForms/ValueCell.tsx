import { memo } from "react";
import type { RecordValue } from "../api/records.api";
import { evaluate } from "./recordValue";

interface Props {
  value: RecordValue;
  /** Only this entry's unsaved change, so a cell re-renders when its own value changes, not the whole sheet. */
  edit?: { value?: string; remark?: string };
  onChange: (id: string, patch: { value?: string; remark?: string }) => void;
  readOnly?: boolean;
}

const OK_NOK = ["OK", "N-OK"];

/**
 * One entry inside a table on the fill screen. A check sheet has hundreds of them
 * (a column per day of the month), so this is a native input - a full form field per
 * cell took half a minute to draw 800 of them - and is memoised.
 */
const ValueCell = ({ value: v, edit, onChange, readOnly }: Props) => {
  const raw = edit?.value ?? v.value ?? "";
  // the server's verdict for what is saved, the local one while typing (as ValueField)
  const ok = edit?.value !== undefined ? evaluate(v, raw) : v.in_spec;
  const set = (next: string) => onChange(v.id, { value: next });
  const hint = v.spec_label && v.spec_label !== "-" ? v.spec_label : undefined;

  let input;
  if (v.field_type === "select" || v.field_type === "boolean") {
    const options = v.field_type === "boolean" ? ["Yes", "No"] : v.options?.length ? v.options : OK_NOK;
    input = (
      <select
        className={`cell-input${ok === false ? " nok" : ""}`}
        value={options.includes(raw) ? raw : ""}
        onChange={(e) => set(e.target.value)}
        disabled={readOnly}
        aria-label={v.label}
        title={v.label}
      >
        <option value="">–</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o === "OK" ? "✓ OK" : o === "N-OK" ? "✗ N-OK" : o}
          </option>
        ))}
      </select>
    );
  } else {
    input = (
      <input
        className={`cell-input${ok === false ? " nok" : ""}`}
        type={v.field_type === "number" ? "number" : v.field_type === "date" ? "date" : "text"}
        step={v.field_type === "number" ? "any" : undefined}
        value={raw}
        onChange={(e) => set(e.target.value)}
        disabled={readOnly}
        placeholder={hint}
        aria-label={v.label}
        title={hint ? `${v.label} (${hint}${v.unit ? ` ${v.unit}` : ""})` : v.label}
      />
    );
  }

  return (
    <div className={`value-cell ${ok === false ? "nok" : ""}`}>
      {input}
      {ok === true && (
        <span className="spec-badge ok" title="Within specification">
          OK
        </span>
      )}
      {ok === false && (
        <span className="spec-badge nok" title="Outside specification">
          N-OK
        </span>
      )}
    </div>
  );
};

export default memo(ValueCell);
