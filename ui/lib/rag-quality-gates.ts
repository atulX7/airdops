/**
 * Shared labels and formatters for RAG quality gate API payloads (GateEvaluator shape).
 */

export interface QualityGateEntry {
  threshold: number
  actual: number | null
  passed: boolean
  evaluated?: boolean
  error?: string
}

export interface QualityGatesPayload {
  all_passed: boolean
  blocking: boolean
  evaluated?: boolean
  message?: string
  gates: Record<string, QualityGateEntry>
}

export const GATE_DISPLAY_LABELS: Record<string, string> = {
  groundedness_min: 'Groundedness',
  citation_coverage_min: 'Citation coverage',
  refusal_correctness_min: 'Refusal correctness',
  context_relevance_min: 'Context relevance',
  answer_relevance_min: 'Answer relevance',
  answer_correctness_min: 'Answer correctness',
  hallucination_rate_max: 'Hallucination rate',
  acl_leakage_max: 'ACL leakage',
  // Legacy keys if older API responses are cached
  hallucination_rate: 'Hallucination rate',
  acl_leakage: 'ACL leakage',
}

export function gateDisplayLabel(key: string): string {
  return GATE_DISPLAY_LABELS[key] ?? key.replace(/_/g, ' ')
}

export function isMaxStyleGate(gateKey: string): boolean {
  return gateKey.endsWith('_max') || gateKey === 'hallucination_rate' || gateKey === 'acl_leakage'
}

export function gateRequirementText(gateKey: string, threshold: number): string {
  if (isMaxStyleGate(gateKey)) {
    return `≤ ${threshold.toFixed(3)} (maximum)`
  }
  return `≥ ${threshold.toFixed(3)} (minimum)`
}

export function formatGateActual(actual: number | null | undefined): string {
  if (actual === null || actual === undefined) {
    return '—'
  }
  if (typeof actual !== 'number' || Number.isNaN(actual)) {
    return String(actual)
  }
  return actual.toFixed(3)
}

export function gateFailureDetail(gateKey: string, entry: QualityGateEntry): string {
  if (entry.error) {
    return entry.error
  }
  if (entry.passed) {
    return '—'
  }
  if (entry.actual === null || entry.actual === undefined) {
    return 'No measurement available for this gate.'
  }
  if (isMaxStyleGate(gateKey)) {
    return `Observed value exceeds the allowed maximum (${entry.actual.toFixed(3)} > ${entry.threshold.toFixed(3)}).`
  }
  return `Observed value is below the required minimum (${entry.actual.toFixed(3)} < ${entry.threshold.toFixed(3)}).`
}

export function sortGateEntries(
  entries: [string, QualityGateEntry][]
): [string, QualityGateEntry][] {
  return [...entries].sort((a, b) => {
    if (a[1].passed !== b[1].passed) {
      return a[1].passed ? 1 : -1
    }
    return gateDisplayLabel(a[0]).localeCompare(gateDisplayLabel(b[0]))
  })
}

export function gatesFailedCount(gates: Record<string, QualityGateEntry> | undefined): number {
  if (!gates) return 0
  return Object.values(gates).filter((g) => !g.passed).length
}

export function gatesTotalCount(gates: Record<string, QualityGateEntry> | undefined): number {
  if (!gates) return 0
  return Object.keys(gates).length
}
