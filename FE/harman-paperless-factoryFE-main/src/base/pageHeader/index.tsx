import React from "react";
import { Box, IconButton } from "@mui/material";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import { pageHeaderStyles } from "./style";

interface Props {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  actions?: React.ReactNode;
  className?: string;
}

const PageHeader = ({ title, subtitle, onBack, actions, className }: Props) => (
  <Box className={className} sx={pageHeaderStyles}>
    {onBack && (
      <IconButton className="back-btn" aria-label="Back" onClick={onBack}>
        <ChevronLeftIcon />
      </IconButton>
    )}
    <div className="page-heading">
      <h1 className="page-title">{title}</h1>
      {subtitle && <p className="page-subtitle">{subtitle}</p>}
    </div>
    {actions && <div className="page-actions">{actions}</div>}
  </Box>
);

export default PageHeader;