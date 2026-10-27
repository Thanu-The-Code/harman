import { Box, Typography } from "@mui/material";
import type { StatCardData } from "./types";
import Sparkline from "./Sparkline";

export default function StatCard({
  title,
  value,
  caption,
  trend,
  color,
  spark,
  size = "small",
}: StatCardData) {
  const isLarge = size === "large";

  return (
    <Box
      sx={{
        position: "relative",
        overflow: "hidden",
        minWidth: 0,
        height: 72,
        px: 1.25,
        py: 1,
        bgcolor: "#fff",
        border: "1px solid #e2e8f0",
        borderRadius: "5px",
        boxShadow: "0 1px 2px rgba(15, 23, 42, 0.04)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      <Typography
        sx={{
          fontSize: 10,
          fontWeight: 500,
          color: "#111827",
          lineHeight: 1.2,
        }}
      >
        {title}
      </Typography>

      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Typography
          sx={{
            fontSize: isLarge ? 23 : 19,
            fontWeight: 700,
            color: "#111827",
            lineHeight: 1.1,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {typeof value === "number" ? value.toLocaleString("en-US") : value}
        </Typography>

        <Typography
          sx={{
            fontSize: 9,
            fontWeight: 500,
            color: trend.startsWith("-") ? "#ef4444" : "#10b981",
            whiteSpace: "nowrap",
          }}
        >
          {trend.startsWith("+") ? "↗ " : ""}
          {trend}
        </Typography>
      </Box>

      <Typography
        sx={{
          fontSize: 8,
          color: isLarge ? "#374151" : "#9ca3af",
          lineHeight: 1.2,
          position: "relative",
          zIndex: 1,
        }}
      >
        {caption}
      </Typography>

      {!isLarge && spark.length > 0 && (
        <Box
          sx={{
            position: "absolute",
            right: 0,
            bottom: 0,
            width: "28%",
            height: 37,
            opacity: 0.95,
            pointerEvents: "none",
          }}
        >
          <Sparkline data={spark} color={color} />
        </Box>
      )}
    </Box>
  );
}
