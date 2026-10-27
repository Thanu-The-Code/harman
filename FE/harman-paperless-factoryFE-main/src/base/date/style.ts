import styled from "styled-components";

export const DateWrapper = styled.div`
  position: relative;
  min-width: 180px;
  width: 220px;

  @media (max-width: 768px) {
    width: 100%;
    min-width: 100%;
  }
`;

export const DateField = styled.input`
  width: 100%;
  height: 40px;
  padding: 0 40px 0 12px;
  border: 1px solid #dce3f1;
  border-radius: 9px;
  outline: none;
  background: #fff;
  color: #222838;
  font: inherit;
  font-size: 14px;
  box-sizing: border-box;

  &::placeholder {
    color: #9196a2;
  }

  &:focus {
    border-color: #4c43c6;
    box-shadow: 0 0 0 3px #4c43c61a;
  }

  &:disabled {
    background: #f7f8fb;
    color: #98a2b3;
    cursor: not-allowed;
  }

  &::-webkit-calendar-picker-indicator {
    opacity: 0;
    position: absolute;
    right: 0;
    cursor: pointer;
  }
`;

export const DateIconButton = styled.button`
  position: absolute;
  top: 50%;
  right: 12px;
  transform: translateY(-50%);
  border: 0;
  background: transparent;
  padding: 0;
  color: #667085;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;

  &:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  svg {
    display: block;
  }
`;

import type { SxProps, Theme } from "@mui/material/styles";

const BORDER = "#e5e7eb";

export const dateRangeStyles: SxProps<Theme> = {
  "& .date-range-btn": {
    height: 36,
    textTransform: "none",
    whiteSpace: "nowrap",
    fontSize: 12,
    fontWeight: 400,
    color: "#374151",
    background: "#fff",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    padding: "0 12px",
    gap: "6px",
    "&:hover": { background: "#f9fafb", borderColor: "#cbd5e1" },
    "& svg": { fontSize: 16, color: "#6b7280" },
  },
  "& .date-range-btn.empty": { color: "#9ca3af" },
};

export const dateRangePopoverStyles: SxProps<Theme> = {
  "& .MuiPopover-paper": {
    marginTop: "6px",
    borderRadius: "10px",
    border: `1px solid ${BORDER}`,
    boxShadow: "0 8px 24px rgba(15, 23, 42, 0.12)",
  },
  "& .date-range-panel": { padding: "14px", width: 280, display: "flex", flexDirection: "column", gap: "12px" },
  "& .date-range-label": { fontSize: 12, color: "#374151", marginBottom: "4px" },
  "& .MuiOutlinedInput-root": {
    background: "#f7f8fa",
    borderRadius: "8px",
    fontSize: 13,
    "& fieldset": { borderColor: BORDER },
    "&.Mui-focused fieldset": { borderColor: "#14b8a6", borderWidth: 1 },
  },
  "& .MuiOutlinedInput-input": { padding: "8px 10px" },
  "& .date-range-actions": { display: "flex", justifyContent: "flex-end", gap: "8px" },
  "& .range-btn": { textTransform: "none", fontSize: 13, fontWeight: 600, borderRadius: "6px", boxShadow: "none" },
  "& .range-clear": { color: "#6b7280", border: `1px solid ${BORDER}` },
  "& .range-apply": {
    color: "#fff",
    background: "#14b8a6",
    "&:hover": { background: "#0f9e8e", boxShadow: "none" },
    "&.Mui-disabled": { background: "#a7e3dc", color: "#fff" },
  },
};