import React from "react";
import { Box } from "@mui/material";
import { formFieldStyles } from "./style";

interface Props {
  label: string;
  helperText?: string;
  children: React.ReactNode;
  className?: string;
}

/** Label above + helper text below any input (text field, select, ...). */
const FormField = ({ label, helperText, children, className }: Props) => (
  <Box className={className} sx={formFieldStyles}>
    <div className="form-field-label">{label}</div>
    {children}
    {helperText && <div className="form-field-helper">{helperText}</div>}
  </Box>
);

export default FormField;