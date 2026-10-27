import { Box, Button, Typography } from "@mui/material";
import { Link, useLocation } from "react-router-dom";

/** A link to a screen that does not exist: say so, instead of a blank page. */
const NotFound = () => {
  const { pathname } = useLocation();
  return (
    <Box role="alert" sx={{ minHeight: 320, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 1, textAlign: "center", p: 3 }}>
      <Typography sx={{ fontSize: 18, fontWeight: 600, color: "#111827" }}>This page does not exist</Typography>
      <Typography sx={{ fontSize: 13, color: "#6b7280" }}>
        Nothing is at <code>{pathname}</code>. The link may be out of date.
      </Typography>
      <Button component={Link} to="/" size="small" variant="contained" sx={{ mt: 1, textTransform: "none", bgcolor: "#14b8a6" }}>
        Go to the dashboard
      </Button>
    </Box>
  );
};

export default NotFound;
