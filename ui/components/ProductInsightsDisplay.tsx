'use client'

import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, AlertTriangle, Loader2, AlertCircle, Lightbulb, BookOpen } from 'lucide-react'
import { apiClient, ProductInsightsResponse } from '@/lib/api-client'
import { useToast } from './ui/toast'
import { Button } from './ui/button'

interface ProductInsightsDisplayProps {
  productId: string
  showTitle?: boolean
}

export function ProductInsightsDisplay({ productId, showTitle = true }: ProductInsightsDisplayProps) {
  const [insights, setInsights] = useState<ProductInsightsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { addToast } = useToast()

  useEffect(() => {
    loadInsights()
  }, [productId])

  const loadInsights = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.getProductInsights(productId)
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load insights: ${response.error}`,
        })
      } else if (response.data) {
        setInsights(response.data)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load insights'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const getPolicyStatusColor = (status: string) => {
    switch (status) {
      case 'passed':
        return 'bg-green-50 border-green-200 text-green-800'
      case 'failed':
        return 'bg-red-50 border-red-200 text-red-800'
      case 'warnings':
        return 'bg-yellow-50 border-yellow-200 text-yellow-800'
      default:
        return 'bg-gray-50 border-gray-200 text-gray-800'
    }
  }

  const getPolicyStatusIcon = (status: string) => {
    switch (status) {
      case 'passed':
        return <CheckCircle className="h-5 w-5 text-green-600" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-600" />
      case 'warnings':
        return <AlertTriangle className="h-5 w-5 text-yellow-600" />
      default:
        return <AlertCircle className="h-5 w-5 text-gray-600" />
    }
  }

  const formatMetricValue = (value: number) => {
    if (value >= 1) return value.toFixed(2)
    return (value * 100).toFixed(1) + '%'
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Product Insights</h2>}
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 text-gray-400 animate-spin mr-2" />
          <p className="text-gray-600">Loading insights...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Product Insights</h2>}
        <div className="flex items-center justify-center py-8">
          <AlertCircle className="h-6 w-6 text-red-500 mr-2" />
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  if (!insights) {
    return null
  }

  const { fingerprint, policy, optimizer } = insights

  return (
    <div className="space-y-6">
      {showTitle && <h2 className="text-lg font-semibold text-gray-900">Product Insights</h2>}

      {/* Policy Status Banner */}
      <div className={`rounded-lg border p-4 ${getPolicyStatusColor(policy.status || 'unknown')}`}>
        <div className="flex items-start gap-3">
          {getPolicyStatusIcon(policy.status || 'unknown')}
          <div className="flex-1">
            <h3 className="font-medium mb-1">
              Policy Evaluation: {policy.status ? (policy.status.charAt(0).toUpperCase() + policy.status.slice(1)) : 'Unknown'}
            </h3>
            {policy.violations && policy.violations.length > 0 && (
              <div className="mt-2">
                <p className="text-sm font-medium mb-1">Violations:</p>
                <ul className="list-disc list-inside text-sm space-y-1">
                  {(policy.violations || []).map((violation: string, idx: number) => (
                    <li key={idx}>{violation}</li>
                  ))}
                </ul>
              </div>
            )}
            {policy.warnings && policy.warnings.length > 0 && (
              <div className="mt-2">
                <p className="text-sm font-medium mb-1">Warnings:</p>
                <ul className="list-disc list-inside text-sm space-y-1">
                  {(policy.warnings || []).map((warning: string, idx: number) => (
                    <li key={idx}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Readiness Fingerprint */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-md font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <BookOpen className="h-5 w-5" />
          Readiness Fingerprint
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Object.entries(fingerprint)
            .filter(([key]) => key !== 'AI_Trust_Score')
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([key, value]) => {
              const numValue = typeof value === 'number' ? value : 0
              return (
                <div key={key} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-gray-700">{key.replace(/_/g, ' ')}</span>
                    <span className="text-sm font-semibold text-gray-900">{formatMetricValue(numValue)}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full ${
                        numValue >= 0.8 ? 'bg-green-500' : numValue >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${Math.min(numValue * 100, 100)}%` }}
                    />
                  </div>
                </div>
              )
            })}
        </div>
      </div>

      {/* Optimizer Suggestions */}
      {optimizer && (optimizer.suggestions || optimizer.playbook_recommendations) && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Lightbulb className="h-5 w-5 text-yellow-600" />
            Optimization Suggestions
          </h3>
          {optimizer.suggestions && optimizer.suggestions.length > 0 && (
            <div className="mb-4">
              <p className="text-sm font-medium text-gray-700 mb-2">Recommendations:</p>
              <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                {(optimizer.suggestions || []).map((suggestion: string, idx: number) => (
                  <li key={idx}>{suggestion}</li>
                ))}
              </ul>
            </div>
          )}
          {optimizer.playbook_recommendations && optimizer.playbook_recommendations.length > 0 && (
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Playbook Recommendations:</p>
              <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                {(optimizer.playbook_recommendations || []).map((rec: string, idx: number) => (
                  <li key={idx}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}




