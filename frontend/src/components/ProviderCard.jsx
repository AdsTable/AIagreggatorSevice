import React from 'react'
import { Card, CardContent, Typography, Chip } from '@mui/material'

export default function ProviderCard({ provider }) {
  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="h6">{provider.name}</Typography>
        <Typography variant="body2" color="text.secondary">
          Type: {provider.type}
        </Typography>
        <Chip
          label={provider.status}
          color={
            provider.status === 'healthy'
              ? 'success'
              : provider.status === 'degraded'
              ? 'warning'
              : 'error'
          }
          sx={{ mt: 1 }}
        />
      </CardContent>
    </Card>
  )
}