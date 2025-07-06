export interface AnalyticsSummary {
  total_events: number
  unique_sessions: number
  unique_users: number
  error_count: number
}

export interface AnalyticsDashboard {
  status: string
  summary: AnalyticsSummary
  charts?: Record<string, unknown>
}