import { TextField } from "@mui/material";
import { customTextFieldStyles } from "./style";
import FormField from "./FormField";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  helperText?: string;
  type?: "text" | "password" | "email";
  className?: string;
}

const CustomTextField = ({ label, value, onChange, placeholder, helperText, type = "text", className }: Props) => (
  <FormField label={label} helperText={helperText} className={className}>
    <TextField
      fullWidth
      sx={customTextFieldStyles}
      type={type}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      slotProps={{ htmlInput: { "aria-label": label } }}
    />
  </FormField>
);

export default CustomTextField;