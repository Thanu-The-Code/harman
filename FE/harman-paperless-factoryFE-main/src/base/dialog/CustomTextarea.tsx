import { Box, TextField } from "@mui/material";
import { customTextAreaStyles } from "./style";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  optional?: boolean;
  rows?: number;
  className?: string;
}

const CustomTextArea = ({ label, value, onChange, placeholder, optional, rows = 4, className }: Props) => (
  <Box className={className} sx={customTextAreaStyles}>
    <div className="field-label">
      {label} {optional && <span className="field-optional">(Optional)</span>}
    </div>
    <TextField
      fullWidth
      multiline
      minRows={rows}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      slotProps={{ htmlInput: { "aria-label": label } }}
    />
  </Box>
);

export default CustomTextArea;