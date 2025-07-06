import React, { useEffect, useState } from 'react'
import { Container, Typography, Grid, Paper, CircularProgress } from '@mui/material'
import { fetchAnalyticsDashboard } from '@api/analytics'
import type { AnalyticsDashboard } from '@types/analytics'

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<AnalyticsDashboard | null>(null)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    setLoading(true)
    fetchAnalyticsDashboard()
      .then(setData)
      .catch((err) => setError(err.message || 'API error'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <Container maxWidth="lg" sx={{ mt: 4 }}>
      <Typography variant="h4" gutterBottom>
        Dashboard
      </Typography>
      {loading && (
        <Grid container justifyContent="center">
          <CircularProgress />
        </Grid>
      )}
      {error && (
        <Paper sx={{ p: 2, mt: 2, background: '#ffeaea', color: '#c00' }}>
          Error: {error}
        </Paper>
      )}
      {data && (
        <Grid container spacing={3} sx={{ mt: 1 }}>
          <Grid item xs={12} md={3}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="subtitle2">Status</Typography>
              <Typography variant="h6">{data.status}</Typography>
            </Paper>
          </Grid>
          <Grid item xs={12} md={9}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="subtitle2">Summary</Typography>
              <pre style={{ fontSize: 14, margin: 0 }}>
                {JSON.stringify(data.summary, null, 2)}
              </pre>
            </Paper>
          </Grid>
        </Grid>
      )}
    </Container>
  )
}

export default Dashboard