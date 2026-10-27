import React from "react";
import { Box, Typography } from "@mui/material";
import { StatsSummaryWrapper } from "./style";

export type StatsSummaryItem = {
  label?: string;
  value?: React.ReactNode;
  icon?: string; // illustration shown on the right of the number
  onClick?: () => void;
};

type StatsSummaryProps = {
  items?: StatsSummaryItem[];
  className?: string;
};

const StatsSummary = ({ items = [], className = "" }: StatsSummaryProps) => {
  return (
    <StatsSummaryWrapper className={className}>
      <Box className="stats-summary-track">
        {items.map((item, index) => (
          <Box
            key={item.label || index}
            className={`stats-summary-card ${item.onClick ? "is-clickable" : ""}`}
            onClick={item.onClick}
            role={item.onClick ? "button" : undefined}
            tabIndex={item.onClick ? 0 : undefined}
          >
            <Box className="stats-summary-top">
              <Typography className="stats-summary-value">
                {item.value}
              </Typography>
              {item.icon && (
                <img
                  src={item.icon}
                  alt="image"
                  className="stats-summary-icon"
                />
              )}
            </Box>
            <Typography className="stats-summary-label">
              {item.label}
            </Typography>
          </Box>
        ))}
      </Box>
    </StatsSummaryWrapper>
  );
};

export default StatsSummary;
