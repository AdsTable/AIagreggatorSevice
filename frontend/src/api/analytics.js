import axios from 'axios'

export function fetchAnalyticsDashboard() {
  return axios.get('/api/analytics/dashboard').then((res) => res.data)
}