import React from "react";
import { Box } from "@mui/material";
import { infoCardStyles } from "./style";

interface Props {
  title: string;
  children: React.ReactNode;
  flush?: boolean; // remove body padding (for tables / previews)
  className?: string;
}

const InfoCard = ({ title, children, flush = false, className }: Props) => (
  <Box className={className} sx={infoCardStyles}>
    <div className="info-card-head">{title}</div>
    <div className={`info-card-body ${flush ? "flush" : ""}`}>{children}</div>
  </Box>
);

export default InfoCard;