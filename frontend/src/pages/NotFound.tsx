import React from "react";
import { Box, Typography } from "@mui/material";
import { Link } from "react-router-dom";

const NotFound: React.FC = () => (
  <Box sx={{ mt: 8, textAlign: "center" }}>
    <Typography variant="h3" color="error">
      404
    </Typography>
    <Typography variant="h5" gutterBottom>
      Page Not Found
    </Typography>
    <Typography variant="body1">
      <Link to="/">Go to Dashboard</Link>
    </Typography>
  </Box>
);

export default NotFound;