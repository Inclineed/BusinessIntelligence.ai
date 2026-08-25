import { InvestigationResult, ScenarioMeta, StructuredFeedbackSubmission, FeedbackResponse, FeedbackRecord } from "../types/investigation"

export const SCENARIO_CATALOG: ScenarioMeta[] = [
  {
    id: "INC_001",
    status: "live",
    title: "Payment Gateway Latency Regression",
    domain: "E-Commerce Checkout",
    type: "Single Root Cause (HIGH)",
    description: "Checkout v4.3 deploy caused connection pool exhaustion in payment gateway client.",
  },
  {
    id: "INC_002",
    status: "live",
    title: "Simultaneous Conflicting Causes",
    domain: "E-Commerce Checkout",
    type: "Ambiguous (ABSTAIN)",
    description: "Simultaneous gateway latency spike & competitor pricing campaign.",
  },
  {
    id: "INC_003",
    status: "evaluation_only",
    title: "Sparse Baseline History",
    domain: "E-Commerce Growth",
    type: "Evaluation Harness Only",
    description: "New premium conversion metric with insufficient historical baseline samples.",
  },
  {
    id: "INC_004",
    status: "live",
    title: "ETL Ingestion Pipeline Delay",
    domain: "Data Engineering",
    type: "Data-Quality Guard (ABSTAIN)",
    description: "Apparent revenue drop caused by delayed batch data warehouse ingestion.",
  },
  {
    id: "INC_005",
    status: "live",
    title: "Trailing Partial Bucket Guard",
    domain: "E-Commerce Volume",
    type: "False Anomaly Guard (ABSTAIN)",
    description: "Incomplete trailing hour volume correctly suppressed from anomaly attribution.",
  },
  {
    id: "INC_006",
    status: "live",
    title: "Compound Network & Deploy Failure",
    domain: "E-Commerce Platform",
    type: "Multi-Factor (HIGH)",
    description: "Simultaneous upstream packet loss and service client latency regression.",
  },
  {
    id: "INC_007",
    status: "live",
    title: "Gradual Worker Memory Leak",
    domain: "Microservices",
    type: "Degradation Drift (HIGH)",
    description: "Progressive 48h memory leak causing slow failure rate drift.",
  },
  {
    id: "INC_008",
    status: "live",
    title: "Enterprise SAML SSO Outage",
    domain: "B2B SaaS Security",
    type: "Cross-Domain Shift (HIGH)",
    description: "Identity provider certificate rotation failure blocking enterprise login.",
  },
]

const API_BASE = "/api"

export async function fetchScenarios(): Promise<ScenarioMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/scenarios`)
    if (res.ok) {
      const data = await res.json()
      const apiScenarios: Array<{ id: string; status?: string; label?: string }> = data.scenarios || []
      const apiIds = new Set(apiScenarios.map((s) => (typeof s === "string" ? s : s.id)))

      // Merge enriched catalog with API scenarios
      return SCENARIO_CATALOG.map((item) => {
        if (apiIds.has(item.id)) {
          return item
        }
        return item
      })
    }
  } catch (err) {
    console.warn("Could not fetch remote scenarios, using catalog:", err)
  }
  return SCENARIO_CATALOG
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


