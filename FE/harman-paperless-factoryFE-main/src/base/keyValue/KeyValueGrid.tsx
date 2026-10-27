import { Box } from "@mui/material";
import { keyValueGridStyles } from "./style";

export type KeyValue = [label: string, value: string];

interface Props {
  /** one array per column, e.g. [leftRows, rightRows] */
  columns: KeyValue[][];
  className?: string;
}

const KeyValueGrid = ({ columns, className }: Props) => (
  <Box
    className={className}
    sx={{ ...keyValueGridStyles, gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}
  >
    {columns.map((rows, i) => (
      <div key={i}>
        {rows.map(([label, value]) => (
          <div className="kv-row" key={label}>
            <span className="kv-label">{label}</span>
            <span className="kv-value">{value}</span>
          </div>
        ))}
      </div>
    ))}
  </Box>
);

export default KeyValueGrid;