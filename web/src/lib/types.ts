export type Project = {
  id: string
  owner_id: string
  name: string
  description: string | null
  project_type: string | null
  location: string | null
  status: string
  created_at: string
}

export type AnalysisIssue = {
  type: string
  severity: 'low' | 'medium' | 'high'
  description: string
}

export type AnalysisResult = {
  score: number
  summary?: string
  errors?: AnalysisIssue[]
  suggestions?: string[]
}

export type AiAnalysis = {
  id: string
  document_id: string
  model_version: string | null
  score: number | null
  status: 'pending' | 'done' | 'failed'
  error_message: string | null
  result: AnalysisResult | null
  created_at: string
}

export type PlanDocument = {
  id: string
  project_id: string
  name: string
  file_type: string | null
  storage_path: string
  created_at: string
  ai_analyses: AiAnalysis[]
}
