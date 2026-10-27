import { useState } from "react";
import { Box, Button, Popover, TextField } from "@mui/material";
import CalendarMonthOutlinedIcon from "@mui/icons-material/CalendarMonthOutlined";
import { dateRangePopoverStyles, dateRangeStyles } from "./style";

export interface DateRange {
  from: string; // yyyy-mm-dd
  to: string; // yyyy-mm-dd
}

const format = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });

interface Props {
  value: DateRange;
  onChange: (range: DateRange) => void;
  placeholder?: string;
  className?: string;
}

const CustomDateRange = ({ value, onChange, placeholder = "Select date range", className }: Props) => {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [draft, setDraft] = useState<DateRange>(value);

  const hasValue = !!value.from && !!value.to;
  const invalid = !draft.from || !draft.to || draft.from > draft.to;

  const open = (e: React.MouseEvent<HTMLElement>) => {
    setDraft(value);
    setAnchor(e.currentTarget);
  };
  const close = () => setAnchor(null);

  return (
    <Box className={className} sx={dateRangeStyles} component="span">
      <Button className={`date-range-btn ${hasValue ? "" : "empty"}`} onClick={open} aria-label="Select date range">
        <CalendarMonthOutlinedIcon />
        {hasValue ? `${format(value.from)} - ${format(value.to)}` : placeholder}
      </Button>

      <Popover open={!!anchor} anchorEl={anchor} onClose={close} sx={dateRangePopoverStyles}>
        <div className="date-range-panel">
          <div>
            <div className="date-range-label">From</div>
            <TextField
              fullWidth
              type="date"
              value={draft.from}
              slotProps={{ htmlInput: { max: draft.to || undefined, "aria-label": "From date" } }}
              onChange={(e) => setDraft((d) => ({ ...d, from: e.target.value }))}
            />
          </div>
          <div>
            <div className="date-range-label">To</div>
            <TextField
              fullWidth
              type="date"
              value={draft.to}
              slotProps={{ htmlInput: { min: draft.from || undefined, "aria-label": "To date" } }}
              onChange={(e) => setDraft((d) => ({ ...d, to: e.target.value }))}
            />
          </div>
          <div className="date-range-actions">
            <Button
              className="range-btn range-clear"
              onClick={() => {
                onChange({ from: "", to: "" });
                close();
              }}
            >
              Clear
            </Button>
            <Button
              className="range-btn range-apply"
              variant="contained"
              disabled={invalid}
              onClick={() => {
                onChange(draft);
                close();
              }}
            >
              Apply
            </Button>
          </div>
        </div>
      </Popover>
    </Box>
  );
};

export default CustomDateRange;