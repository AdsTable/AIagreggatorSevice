import React from "react";
import { Container, Typography, Box, TextField, Button } from "@mui/material";

const Login: React.FC = () => (
  <Container maxWidth="sm" sx={{ mt: 8 }}>
    <Typography variant="h4" gutterBottom>
      Login
    </Typography>
    <Box component="form" sx={{ mt: 2 }}>
      <TextField label="Username" fullWidth sx={{ mb: 2 }} />
      <TextField label="Password" type="password" fullWidth sx={{ mb: 2 }} />
      <Button variant="contained" color="primary" fullWidth>
        Sign in
      </Button>
    </Box>
  </Container>
);

export default Login;