import { useState } from "react";

export interface Reading {
  id: string;
  label: string;
  value: string | null;
  unit?: string | null;
  remark?: string | null;
  /** "10 to 20 bar"; "-" or empty = no limit */
  spec_label?: string | null;
  in_spec: boolean | null;
}

/** More blank entries than this are folded away (a monthly check sheet fills one day's column at a time). */
const FOLD_BLANKS_OVER = 10;

/**
 * A record's readings, as the review page and the Doc Repository show them. On a record
 * with many blank entries the filled ones come first and the blanks are behind a button,
 * so the readings are not lost among hundreds of empty cells. Out-of-spec readings are
 * filled, so they are always shown.
 */
const ReadingsTable = ({ readings, showSpec = false }: { readings: Reading[]; showSpec?: boolean }) => {
  const [showBlanks, setShowBlanks] = useState(false);
  const blanks = readings.filter((r) => !r.value);
  const fold = blanks.length > FOLD_BLANKS_OVER;
  const shown = fold && !showBlanks ? readings.filter((r) => r.value) : readings;

  return (
    <>
      <table className="readings-table">
        <thead>
          <tr>
            <th>Entry</th>
            <th>Reading</th>
            {showSpec && <th>Specification</th>}
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.id} className={r.in_spec === false ? "nok" : ""}>
              <td>{r.label}</td>
              <td>
                {r.value ? `${r.value}${r.unit ? ` ${r.unit}` : ""}` : <span className="muted">blank</span>}
                {r.remark && <div className="muted">“{r.remark}”</div>}
              </td>
              {showSpec && <td className="muted">{r.spec_label && r.spec_label !== "-" ? r.spec_label : "—"}</td>}
              <td>{r.in_spec === null ? "—" : r.in_spec ? "OK" : "N-OK"}</td>
            </tr>
          ))}
          {shown.length === 0 && (
            <tr>
              <td colSpan={showSpec ? 4 : 3} className="muted">
                Nothing has been filled in.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {fold && (
        <button type="button" className="readings-fold" onClick={() => setShowBlanks(!showBlanks)}>
          {showBlanks
            ? `Hide the ${blanks.length} blank entries`
            : `${readings.length - blanks.length} of ${readings.length} entries filled · show the ${blanks.length} blank entries`}
        </button>
      )}
    </>
  );
};

export default ReadingsTable;
