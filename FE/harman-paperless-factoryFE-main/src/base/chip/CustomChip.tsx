import { Box } from "@mui/material";
import { customChipStyles } from "./style";

export type ChipVariant = "blue" | "purple" | "green" | "orange" | "gray";

interface Props {
  label: string;
  variant?: ChipVariant;
  className?: string;
}

const CustomChip = ({ label, variant = "gray", className }: Props) => (
  <Box
    component="span"
    className={`chip-${variant} ${className ?? ""}`}
    sx={customChipStyles}
  >
    {label}
  </Box>
);

export default CustomChip;
