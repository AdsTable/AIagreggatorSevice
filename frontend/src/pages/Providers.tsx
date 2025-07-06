import React, { useEffect, useState } from "react";
import { Container, Typography, Grid, CircularProgress } from "@mui/material";
import ProviderCard from "@components/ProviderCard";

interface Provider {
  name: string;
  type: string;
  status: string;
}

const Providers: React.FC = () => {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/providers")
      .then((r) => r.json())
      .then((data) => setProviders(data.providers ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Container maxWidth="md" sx={{ mt: 4 }}>
      <Typography variant="h4" gutterBottom>
        Providers
      </Typography>
      {loading ? (
        <CircularProgress />
      ) : (
        <Grid container spacing={2}>
          {providers.map((provider) => (
            <Grid item xs={12} md={6} key={provider.name}>
              <ProviderCard provider={provider} />
            </Grid>
          ))}
        </Grid>
      )}
    </Container>
  );
};

export default Providers;