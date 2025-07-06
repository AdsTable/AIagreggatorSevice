import React from "react";
import { AppBar, Toolbar, Typography, Container, Box, Link as MuiLink } from "@mui/material";
import { Link, Outlet } from "react-router-dom";

const MainLayout: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <Box>
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" component={Link} to="/" sx={{ color: "inherit", textDecoration: "none", flexGrow: 1 }}>
          AI Aggregator Admin
        </Typography>
        <MuiLink component={Link} to="/providers" color="inherit" sx={{ mr: 2 }}>
          Providers
        </MuiLink>
        <MuiLink component={Link} to="/analytics" color="inherit" sx={{ mr: 2 }}>
          Analytics
        </MuiLink>
        <MuiLink component={Link} to="/diagnostics" color="inherit">
          Diagnostics
        </MuiLink>
      </Toolbar>
    </AppBar>
    <Container maxWidth="xl">
      {children ?? <Outlet />}
    </Container>
  </Box>
);

export default MainLayout;