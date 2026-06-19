'use client'

import { cn } from '@/lib/utils'
import {
  type QualityGateEntry,
  gateDisplayLabel,
  gateFailureDetail,
  gateRequirementText,
  formatGateActual,
  sortGateEntries,
} from '@/lib/rag-quality-gates'

type Props = {
  gates: Record<string, QualityGateEntry>
  title?: string
  subtitle?: string
  /** When true, use compact padding (e.g. inside expanded table row) */
  compact?: boolean
  className?: string
}

export function RAGQualityGatesDetailTable({
  gates,
  title = 'Gate details (threshold vs actual)',
  subtitle = 'Based on this evaluation’s metrics and your product’s configured thresholds.',
  compact = false,
  className,
}: Props) {
  const entries = sortGateEntries(Object.entries(gates))
  if (entries.length === 0) {
    return null
  }

  const th = compact ? 'px-3 py-2' : 'px-4 py-3'
  const td = compact ? 'px-3 py-2' : 'px-4 py-3'

  return (
    <div className={cn('rounded-lg border border-gray-200 bg-white overflow-hidden', className)}>
      <div className={`border-b border-gray-100 bg-gray-50 ${compact ? 'px-3 py-2' : 'px-4 py-3'}`}>
        <h4 className={`font-semibold text-gray-900 ${compact ? 'text-xs' : 'text-sm'}`}>{title}</h4>
        {subtitle ? (
          <p className={`text-gray-600 mt-0.5 ${compact ? 'text-[11px]' : 'text-xs'}`}>{subtitle}</p>
        ) : null}
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              <th className={th}>Quality gate</th>
              <th className={th}>Requirement</th>
              <th className={th}>Actual</th>
              <th className={th}>Status</th>
              <th className={`${th} min-w-[180px]`}>Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {entries.map(([key, entry]) => (
              <tr key={key} className={entry.passed ? 'bg-white' : 'bg-red-50/60'}>
                <td className={`${td} font-medium text-gray-900`}>{gateDisplayLabel(key)}</td>
                <td className={`${td} text-gray-700 tabular-nums`}>{gateRequirementText(key, entry.threshold)}</td>
                <td className={`${td} text-gray-800 tabular-nums`}>{formatGateActual(entry.actual)}</td>
                <td className={td}>
                  {entry.passed ? (
                    <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                      Passed
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                      Failed
                    </span>
                  )}
                </td>
                <td className={`${td} text-gray-600 text-xs leading-relaxed`}>{gateFailureDetail(key, entry)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
