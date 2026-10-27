import type { SxProps, Theme } from "@mui/material/styles";

// export const customPaginationStyles: SxProps<Theme> = {
//   display: "flex",
//   alignItems: "center",
//   justifyContent: "flex-end",
//   gap: "8px",
//   padding: "12px 16px 20px",
//   borderTop: "1px solid #e5e7eb",
//   background: "#fff",

//   "& .page-btn": {
//     minWidth: 32,
//     width: 32,
//     height: 32,
//     padding: 0,
//     fontSize: 13,
//     color: "#1f2937",
//     border: "1px solid #e5e7eb",
//     borderRadius: "8px",
//     background: "#fff",
//     "&:hover": { borderColor: "#14b8a6" },
//     "&.Mui-disabled": { opacity: 0.45 },
//   },
//   "& .page-btn.active": {
//     color: "#14b8a6",
//     borderColor: "#14b8a6",
//     background: "#e6f7f5",
//   },
// };



const TEAL = "#14b8a6";
const BORDER = "#e5e7eb";

export const customPaginationStyles: SxProps<Theme> = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "8px",
  padding: "12px 16px",
  borderTop: `1px solid ${BORDER}`,
  background: "#fff",
  fontSize: 12,
  color: "#6b7280",

  "& .pagination-pages": { display: "flex", alignItems: "center", gap: "6px" },
  "& .pagination-side": { flex: 1, display: "flex", alignItems: "center", gap: "6px", whiteSpace: "nowrap" },
  "& .pagination-side.right": { justifyContent: "flex-end" },
  "& .pagination-ellipsis": { padding: "0 2px" },

  "& .page-btn": {
    minWidth: 32,
    width: 32,
    height: 32,
    padding: 0,
    fontSize: 13,
    color: "#1f2937",
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    background: "#fff",
    "&:hover": { borderColor: TEAL },
    "&.Mui-disabled": { opacity: 0.45 },
  },
  "& .page-btn.active": { color: TEAL, borderColor: TEAL, background: "#e6f7f5" },

  "& select, & input": {
    height: 28,
    boxSizing: "border-box",
    border: `1px solid ${BORDER}`,
    borderRadius: "6px",
    color: "#1f2937",
    background: "#fff",
    fontSize: 12,
  },
  "& input": { width: 44, textAlign: "center" },
  "& .goto-btn": { border: 0, padding: 0, background: "transparent", color: "#6b7280", font: "inherit", cursor: "pointer", "&:hover": { color: TEAL } },

  /* dense variant: small buttons, solid active page */
  "&.dense": { padding: "6px 9px", minHeight: 34, fontSize: 10 },
  "&.dense .page-btn": { minWidth: 23, width: 23, height: 23, fontSize: 10, borderRadius: "5px" },
  "&.dense .page-btn.active": { color: "#fff", background: TEAL },
  "&.dense select, &.dense input": { height: 24, fontSize: 10, borderRadius: "5px" },
  "&.dense input": { width: 36 },
};