import React from "react";
import { Container, Typography } from "@mui/material";

const Diagnostics: React.FC = () => (
  <Container maxWidth="lg" sx={{ mt: 4 }}>
    <Typography variant="h4" gutterBottom>
      Diagnostics
    </Typography>
    <Typography variant="body1">System diagnostics and health checks coming soon...</Typography>
  </Container>
);

export default Diagnostics;