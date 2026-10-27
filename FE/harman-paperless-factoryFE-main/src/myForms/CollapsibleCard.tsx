import React, { useState } from "react";
import { Collapse } from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";

interface Props {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

const CollapsibleCard: React.FC<Props> = ({ title, subtitle, defaultOpen = true, children }) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="form-card">
      <div
        className={`form-card-head ${open ? "" : "closed"}`}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
      >
        <div>
          <div className="form-card-title">{title}</div>
          {subtitle && <div className="form-card-code">{subtitle}</div>}
        </div>
        <KeyboardArrowDownIcon className={`chevron ${open ? "open" : ""}`} />
      </div>
      <Collapse in={open}>{children}</Collapse>
    </div>
  );
};

export default CollapsibleCard;