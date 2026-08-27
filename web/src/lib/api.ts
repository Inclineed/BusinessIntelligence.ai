import { InvestigationResult, ScenarioMeta, StructuredFeedbackSubmission, FeedbackResponse, FeedbackRecord } from "../types/investigation"

const API_BASE = "/api"

export async function fetchScenarios(): Promise<ScenarioMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/scenarios`)
    if (res.ok) {
      const data = await res.json()
      const apiScenarios: Array<{ id: string; status?: string; label?: string; domain?: string; type?: string; description?: string }> = data.scenarios || []
      
      return apiScenarios.map((s) => ({
        id: s.id,
        status: (s.status as "live" | "evaluation_only") || "live",
        title: s.label || s.id,
        domain: s.domain || "Unknown Domain",
        type: s.type || "Anomaly",
        description: s.description || s.label || "",
      }))
    }
  } catch (err) {
    console.warn("Could not fetch remote scenarios:", err)
  }
  return []
}

export interface ApiInvestigationError extends Error {
  statusCode?: number
  details?: string
}

export async function runInvestigation(
  scenarioId: string,
  persona: string,
  region?: string
): Promise<InvestigationResult> {
  const payload: Record<string, string> = {
    scenario_id: scenarioId,
    persona: persona.toLowerCase(),
  }
  if (region && region !== "all") {
    payload.region = region
  }

  let res: Response
  try {
    res = await fetch(`${API_BASE}/investigate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    })
  } catch (netErr: any) {
    const err: ApiInvestigationError = new Error(`Network Error: ${netErr.message || "Failed to reach backend server on :8080"}`)
    err.statusCode = 0
    err.details = "Check that the FastAPI server is running on http://localhost:8080 and that the Vite proxy is forwarding requests."
    throw err
  }

  // Handle server-side 403 access denied (Entitlement enforcement)
  if (res.status === 403) {
    try {
      const errorData = await res.json()
      return {
        scenario_id: scenarioId,
        persona: persona as any,
        signals: [],
        contributions: [],
        evidence: [],
        hypotheses: [],
        scored: [],
        decision: { 
          abstained: true,
          abstention_reason: errorData.reason || "Access Denied: Persona unauthorized under pre-retrieval entitlement boundary.",
          recommended_action: "Request additional security permissions or select an authorized persona scope.",
        },
        access_denied: true,
        excluded_sources: errorData.excluded_sources || errorData.denied_sources || [],
        reason: errorData.reason || "Persona unauthorized under pre-retrieval entitlement boundary.",
      }
    } catch {
      return {
        scenario_id: scenarioId,
        persona: persona as any,
        signals: [],
        contributions: [],
        evidence: [],
        hypotheses: [],
        scored: [],
        decision: { 
          abstained: true,
          abstention_reason: "Access Denied: Entitlement scope is empty for this persona.",
          recommended_action: "Switch to an authorized persona such as Analyst.",
        },
        access_denied: true,
      }
    }
  }

  if (!res.ok) {
    let detail = ""
    try {
      const errJson = await res.json()
      detail = errJson.detail || errJson.message || JSON.stringify(errJson)
    } catch {
      detail = await res.text().catch(() => "")
    }

    const err: ApiInvestigationError = new Error(`Server returned HTTP ${res.status}: ${detail || res.statusText}`)
    err.statusCode = res.status
    err.details = detail || `FastAPI endpoint returned HTTP ${res.status}`
    throw err
  }

  try {
    const data = await res.json()
    return data as InvestigationResult
  } catch (parseErr: any) {
    const err: ApiInvestigationError = new Error(`Malformed JSON response from backend: ${parseErr.message}`)
    err.statusCode = 200
    err.details = "The backend returned 200 OK but the response body could not be parsed as valid JSON."
    throw err
  }
}

export async function submitFeedback(
  investigationId: string,
  content: string
): Promise<FeedbackResponse> {
  // Legacy wrapper — maps old (investigationId, content) to structured payload
  return submitStructuredFeedback({
    investigation_id: investigationId,
    scenario_id: "",  // Will be resolved server-side from investigation_id
    verdict: "CORRECT",
    analyst_notes: content,
  })
}

export async function submitStructuredFeedback(
  submission: StructuredFeedbackSubmission
): Promise<FeedbackResponse> {
  const res = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(submission),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Network error" }))
    return { success: false, error: err.error || err.detail || `HTTP ${res.status}` }
  }

  return await res.json()
}

export async function getFeedbackForScenario(
  scenarioId: string
): Promise<{ scenario_id: string; count: number; records: FeedbackRecord[] }> {
  const res = await fetch(`${API_BASE}/feedback/${scenarioId}`)

  if (!res.ok) {
    return { scenario_id: scenarioId, count: 0, records: [] }
  }

  return await res.json()
}

export async function getSystemHealth(): Promise<import("../types/investigation").SystemHealthData> {
  const res = await fetch(`${API_BASE}/evaluation/health`)
  if (!res.ok) {
    throw new Error(`Health check failed (HTTP ${res.status})`)
  }
  return await res.json()
}

export async function getFeedbackMetrics(): Promise<any> {
  const res = await fetch(`${API_BASE}/feedback/metrics`)
  if (!res.ok) {
    throw new Error(`Feedback metrics request failed (HTTP ${res.status})`)
  }
  return await res.json()
}

export async function getKpiContract(): Promise<any> {
  const res = await fetch(`${API_BASE}/kpi-contract`)
  if (!res.ok) {
    throw new Error(`KPI contract request failed (HTTP ${res.status})`)
  }
  return await res.json()
}


