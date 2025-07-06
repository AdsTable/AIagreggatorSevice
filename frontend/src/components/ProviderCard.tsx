import React from "react";
import { Card, CardContent, Typography, Chip } from "@mui/material";

interface Provider {
  name: string;
  type: string;
  status: string;
}

const ProviderCard: React.FC<{ provider: Provider }> = ({ provider }) => (
  <Card variant="outlined" sx={{ mb: 2 }}>
    <CardContent>
      <Typography variant="h6">{provider.name}</Typography>
      <Typography variant="body2" color="text.secondary">
        Type: {provider.type}
      </Typography>
      <Chip
        label={provider.status}
        color={
          provider.status === "healthy"
            ? "success"
            : provider.status === "degraded"
            ? "warning"
            : "error"
        }
        sx={{ mt: 1 }}
      />
    </CardContent>
  </Card>
);

export default ProviderCard;