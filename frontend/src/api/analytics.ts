import axios from 'axios'
import type { AnalyticsDashboard } from '@types/analytics'

export async function fetchAnalyticsDashboard(): Promise<AnalyticsDashboard> {
  const res = await axios.get('/api/analytics/dashboard')
  return res.data
}