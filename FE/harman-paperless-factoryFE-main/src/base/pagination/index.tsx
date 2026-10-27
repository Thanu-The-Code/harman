import { useState } from "react";
import { Box, IconButton } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { customPaginationStyles } from "./style";

/** 1 2 3 … 16  /  1 … 7 8 9 … 16  /  1 … 14 15 16 */
const getPageItems = (page: number, total: number): (number | "ellipsis")[] => {
  if (total <= 5) return Array.from({ length: total }, (_, i) => i + 1);
  const set = new Set([1, total, page - 1, page, page + 1]);
  if (page <= 2) [2, 3].forEach((n) => set.add(n));
  if (page >= total - 1) [total - 2, total - 1].forEach((n) => set.add(n));
  const sorted = [...set].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b);
  const items: (number | "ellipsis")[] = [];
  sorted.forEach((n, i) => {
    if (i > 0 && n - sorted[i - 1] > 1) items.push("ellipsis");
    items.push(n);
  });
  return items;
};

interface Props {
  page: number; // 1-based
  totalPages: number;
  onChange: (page: number) => void;
  /* optional extras */
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
  showGoTo?: boolean;
  dense?: boolean;
  className?: string;
}

const CustomPagination = ({
  page, totalPages, onChange,
  pageSize, pageSizeOptions, onPageSizeChange,
  showGoTo = false, dense = false, className,
}: Props) => {
  const [goTo, setGoTo] = useState("");
  const total = Math.max(totalPages, 1);
  const hasSides = Boolean(pageSizeOptions) || showGoTo;

  const submitGoTo = () => {
    const n = Number(goTo);
    if (n >= 1 && n <= total) onChange(n);
  };

  return (
    <Box className={`custom-pagination ${dense ? "dense" : ""} ${className ?? ""}`} sx={customPaginationStyles}>
      {hasSides && (
        <div className="pagination-side left">
          {pageSizeOptions && (
            <>
              <span>Showing per page</span>
              <select aria-label="Rows per page" value={pageSize} onChange={(e) => onPageSizeChange?.(Number(e.target.value))}>
                {pageSizeOptions.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </>
          )}
        </div>
      )}

      <div className="pagination-pages">
        <IconButton className="page-btn" aria-label="Previous page" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          <ChevronLeftIcon fontSize="small" />
        </IconButton>
        {getPageItems(page, total).map((item, i) =>
          item === "ellipsis" ? (
            <span key={`e${i}`} className="pagination-ellipsis" aria-hidden="true">…</span>
          ) : (
            <IconButton
              key={item}
              className={`page-btn ${item === page ? "active" : ""}`}
              aria-label={`Page ${item}`}
              aria-current={item === page ? "page" : undefined}
              onClick={() => onChange(item)}
            >
              {item}
            </IconButton>
          ),
        )}
        <IconButton className="page-btn" aria-label="Next page" disabled={page >= total} onClick={() => onChange(page + 1)}>
          <ChevronRightIcon fontSize="small" />
        </IconButton>
      </div>

      {hasSides && (
        <div className="pagination-side right">
          {showGoTo && (
            <>
              <span>Go to page</span>
              <input
                aria-label="Go to page"
                type="number"
                min={1}
                max={total}
                value={goTo}
                onChange={(e) => setGoTo(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitGoTo()}
              />
              <button type="button" className="goto-btn" onClick={submitGoTo}>Go</button>
            </>
          )}
        </div>
      )}
    </Box>
  );
};

export default CustomPagination;