import type { SxProps, Theme } from "@mui/material/styles";

const BORDER = "#e5e7eb";

export const customDialogStyles: SxProps<Theme> = {
  "& .MuiDialog-paper": {
    borderRadius: "12px",
    boxShadow: "0 12px 40px rgba(15, 23, 42, 0.18)",
    fontFamily: '"Plus Jakarta Sans", "Inter", Roboto, sans-serif',
    margin: "16px",
    width: "100%",
  },

  "& .dialog-header": {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "16px",
    padding: "14px 20px",
    borderBottom: `1px solid ${BORDER}`,
  },
  "& .dialog-title": { fontSize: 14, fontWeight: 600, color: "#111827", margin: 0 },
  "& .dialog-subtitle": { fontSize: 11, color: "#6b7280", margin: "2px 0 0", "& b": { color: "#374151", fontWeight: 600 } },
  "& .dialog-close": {
    width: 34,
    height: 34,
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    background: "#f3f4f6",
    color: "#374151",
    "&:hover": { background: "#e5e7eb" },
  },

  "& .dialog-body": { padding: "16px 20px 20px", display: "flex", flexDirection: "column", gap: "16px" },
  "& .field-label": { fontSize: 14, color: "#1f2937", marginBottom: "6px" },

  "& .dialog-footer": {
    display: "flex",
    justifyContent: "flex-end",
    gap: "12px",
    padding: "14px 20px",
    borderTop: `1px solid ${BORDER}`,
  },
  "& .dialog-btn": {
    textTransform: "none",
    fontSize: 14,
    fontWeight: 600,
    borderRadius: "6px",
    padding: "6px 22px",
    boxShadow: "none",
    whiteSpace: "nowrap",
  },
  "& .cancel-btn": {
    color: "#6b7280",
    background: "#fff",
    border: `1px solid ${BORDER}`,
    "&:hover": { background: "#f9fafb" },
  },
  "& .confirm-btn": {
    color: "#fff",
    background: "#14b8a6",
    "&:hover": { background: "#0f9e8e", boxShadow: "none" },
    "&.Mui-disabled": { background: "#a7e3dc", color: "#fff" },
  },
};

export const customTextAreaStyles: SxProps<Theme> = {
  "& .field-label": { fontSize: 14, color: "#1f2937", marginBottom: "6px" },
  "& .field-optional": { color: "#6b7280" },
  "& .MuiOutlinedInput-root": {
    background: "#f7f8fa",
    borderRadius: "8px",
    fontSize: 14,
    padding: "10px 12px",
    "& fieldset": { borderColor: "#e5e7eb" },
    "&:hover fieldset": { borderColor: "#cbd5e1" },
    "&.Mui-focused fieldset": { borderColor: "#14b8a6", borderWidth: 1 },
  },
};


export const formFieldStyles: SxProps<Theme> = {
  minWidth: 0,
  "& .form-field-label": { fontSize: 12, color: "#232F3D", margin: "12px 0" },
  "& .form-field-helper": { fontSize: 11, color: "#6b7280", marginTop: "4px", lineHeight: 1.4 },
};



export const customTextFieldStyles: SxProps<Theme> = {
  "& .MuiOutlinedInput-root": {
    background: "#f7f8fa",
    borderRadius: "8px",
    fontSize: 14,
    "& fieldset": { borderColor: "#e5e7eb" },
    "&:hover fieldset": { borderColor: "#cbd5e1" },
    "&.Mui-focused fieldset": { borderColor: "#14b8a6", borderWidth: 1 },
  },
  "& .MuiOutlinedInput-input": { padding: "9px 12px", height: "auto" },
};