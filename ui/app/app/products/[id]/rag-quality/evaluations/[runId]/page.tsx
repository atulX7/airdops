'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Download, CheckCircle2, XCircle, BarChart3, Loader2, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/ui/status-badge'
import { DEFAULT_ITEMS_PER_PAGE } from '@/lib/constants'
import type { QualityGatesPayload } from '@/lib/rag-quality-gates'
import { RAGQualityGatesDetailTable } from '@/components/RAGQualityGatesDetailTable'

interface EvaluationRun {
  id: string
  product_id: string
  version: number
  status: string
  metrics?: {
    aggregate?: Record<string, {
      mean: number
      min: number
      max: number
      count: number
    }>
    per_query?: Array<{
      item_id: string
      query: string
      metrics: Record<string, {
        score: number
        passed: boolean
        details?: any
      }>
      error?: string
      retrieved_chunks_count?: number
      answer_method?: string
    }>
  }
  started_at?: string
  finished_at?: string
  created_at: string
  report_path?: string
  dataset_id?: string | null
  dataset_name?: string | null
  /** When golden_qa or adversarial, retrieval_* metrics are hidden in the UI. */
  dataset_type?: string | null
  pipeline_version?: number | null
  quality_gates?: QualityGatesPayload | null
}

// Map evaluation status to StatusBadge status type
const mapEvaluationStatus = (status: string): 'queued' | 'running' | 'succeeded' | 'failed' => {
  switch (status) {
    case 'pending':
    case 'queued':
      return 'queued'
    case 'running':
      return 'running'
    case 'completed':
      return 'succeeded'
    case 'failed':
      return 'failed'
    default:
      return 'queued'
  }
}

export default function EvaluationRunDetailPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  const runId = params.runId as string

  const [run, setRun] = useState<EvaluationRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloadingReport, setDownloadingReport] = useState(false)
  const [polling, setPolling] = useState(false)
  const [perQuery, setPerQuery] = useState<Array<{
    item_id: string
    query: string
    metrics: Record<string, {
      score: number
      passed: boolean
      details?: any
    }>
    error?: string
    retrieved_chunks_count?: number
    answer_method?: string
  }>>([])
  const [currentPage, setCurrentPage] = useState(0)
  const [totalQueries, setTotalQueries] = useState(0)
  const [loadingQueries, setLoadingQueries] = useState(false)
  
  // Ref to track the polling interval
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  const loadQueries = useCallback(async (page: number = 0) => {
    setLoadingQueries(true)
    try {
      const offset = page * DEFAULT_ITEMS_PER_PAGE
      const response = await apiClient.getEvaluationRunQueries(runId, DEFAULT_ITEMS_PER_PAGE, offset)
      if (!response.error && response.data) {
        setPerQuery(response.data.queries || [])
        setTotalQueries(response.data.total || 0)
        setCurrentPage(page)
      }
    } catch (err) {
      console.error('Failed to load evaluation queries:', err)
    } finally {
      setLoadingQueries(false)
    }
  }, [runId])

  const loadData = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const response = await apiClient.getEvaluationRun(runId)
      if (!response.error && response.data) {
        setRun(response.data as EvaluationRun)
        // Load paginated queries if evaluation is completed
        const evalRun = response.data as EvaluationRun
        if (evalRun.status === 'completed') {
          loadQueries(0)
        }
      }
    } catch (err) {
      console.error('Failed to load evaluation run:', err)
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [runId, loadQueries])

  useEffect(() => {
    if (status === 'authenticated' && runId) {
      loadData()
    }
  }, [status, runId, loadData])

  // Auto-refresh if evaluation is running
  useEffect(() => {
    const isRunning = run?.status === 'running' || run?.status === 'queued' || run?.status === 'pending'
    const isCompleted = run?.status === 'completed'
    
    if (isRunning && !intervalRef.current) {
      setPolling(true)
      intervalRef.current = setInterval(() => {
        loadData(false)
      }, 10000) // Poll every 10 seconds
    } else if (!isRunning && intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
      setPolling(false)
    }

    // Load queries when evaluation completes
    if (isCompleted && totalQueries === 0 && !loadingQueries) {
      loadQueries(0)
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [run?.status, totalQueries, loadingQueries, loadQueries, loadData])

  const handleDownloadReport = async () => {
    setDownloadingReport(true)
    try {
      const result = await apiClient.downloadEvaluationReport(runId)
      
      if (!result || !result.blob) {
        throw new Error('Failed to download report')
      }

      // Determine filename and extension from response, report_path, or default
      let filename: string
      let extension: string
      
      if (result.filename) {
        // Use filename from Content-Disposition header
        filename = result.filename
        extension = filename.split('.').pop() || 'csv'
      } else {
        // Determine extension from content type or report_path
        if (result.contentType?.includes('text/csv')) {
          extension = 'csv'
        } else if (result.contentType?.includes('application/pdf')) {
          extension = 'pdf'
        } else if (run?.report_path?.endsWith('.csv')) {
          extension = 'csv'
        } else if (run?.report_path?.endsWith('.pdf')) {
          extension = 'pdf'
        } else {
          extension = 'csv' // Default to CSV as that's what's generated
        }
        filename = `evaluation-report-${runId}.${extension}`
      }

      const url = window.URL.createObjectURL(result.blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Failed to download report:', err)
      alert('Failed to download the evaluation report. Please try again later.')
    } finally {
      setDownloadingReport(false)
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Breadcrumb Navigation */}
          <div className="flex items-center mb-6">
            <Link href={`/app/products/${productId}/rag-quality/evaluations`} className="flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Evaluations
            </Link>
            <span className="mx-2 text-gray-400">/</span>
            <span className="text-sm font-medium text-gray-900">Run Details</span>
          </div>

          {/* Page Header */}
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-gray-900">Evaluation Run Details</h1>
          </div>

          <CardSkeleton />
        </div>
      </AppLayout>
    )
  }

  if (!run) {
    return (
      <AppLayout>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {/* Breadcrumb Navigation */}
          <div className="flex items-center mb-6">
            <Link href={`/app/products/${productId}/rag-quality/evaluations`} className="flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Evaluations
            </Link>
            <span className="mx-2 text-gray-400">/</span>
            <span className="text-sm font-medium text-gray-900">Run Details</span>
          </div>

          {/* Page Header */}
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-gray-900">Evaluation Run Details</h1>
          </div>

          {/* Error Message */}
          <div className="bg-red-50 border border-red-200 rounded-lg p-6">
            <div className="flex items-start">
              <XCircle className="h-5 w-5 text-red-600 mr-3 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="text-lg font-semibold text-red-900 mb-2">Evaluation Run Not Found</h3>
                <p className="text-red-800 mb-4">
                  The evaluation run you're looking for doesn't exist or may have been deleted.
                </p>
                <Link href={`/app/products/${productId}/rag-quality/evaluations`}>
                  <Button variant="outline" className="flex items-center gap-2">
                    <ArrowLeft className="h-4 w-4" />
                    Back to Evaluations
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }

  const aggregate = run.metrics?.aggregate || {}
  const hideRetrievalMetrics =
    run.dataset_type === 'golden_qa' || run.dataset_type === 'adversarial'
  const aggregateEntries = Object.entries(aggregate).filter(([name]) => {
    if (!hideRetrievalMetrics) return true
    return !name.startsWith('retrieval_')
  })
  const isRunning = run.status === 'running' || run.status === 'queued' || run.status === 'pending'
  const isCompleted = run.status === 'completed'

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href={`/app/products/${productId}/rag-quality/evaluations`} className="flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Evaluations
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Run Details</span>
        </div>

        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Evaluation Run Details</h1>
            <p className="mt-2 text-sm text-gray-600">
              Version {run.version} • {new Date(run.created_at).toLocaleString()}
            </p>
            {(run.dataset_name || run.pipeline_version !== null || run.dataset_type) && (
              <div className="mt-2 flex items-center gap-4 text-sm text-gray-600 flex-wrap">
                {run.dataset_name && (
                  <span className="flex items-center gap-1">
                    <span className="font-medium">Dataset:</span>
                    <span>{run.dataset_name}</span>
                  </span>
                )}
                {run.dataset_type && (
                  <span className="flex items-center gap-1">
                    <span className="font-medium">Type:</span>
                    <span className="capitalize">{run.dataset_type.replace(/_/g, ' ')}</span>
                  </span>
                )}
                {run.pipeline_version !== null && run.pipeline_version !== undefined && (
                  <span className="flex items-center gap-1">
                    <span className="font-medium">Pipeline Version:</span>
                    <span>v{run.pipeline_version}</span>
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={mapEvaluationStatus(run.status)} />
            {isCompleted && run.report_path && (
              <Button 
                variant="outline"
                onClick={handleDownloadReport}
                disabled={downloadingReport}
                className="flex items-center gap-2"
              >
                {downloadingReport ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Downloading...
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4" />
                    Download Report
                  </>
                )}
              </Button>
            )}
          </div>
        </div>

        {/* Polling indicator */}
        {polling && (
          <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-center gap-2">
            <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
            <span className="text-sm text-blue-800">Auto-refreshing evaluation status...</span>
          </div>
        )}

        {/* Running State - Progress Indicator */}
        {isRunning && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 mb-6">
            <div className="text-center">
              <div className="flex justify-center mb-4">
                <div className="relative">
                  <Activity className="h-16 w-16 text-blue-600 animate-pulse" />
                  <Loader2 className="h-8 w-8 text-blue-600 animate-spin absolute top-4 left-4" />
                </div>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Evaluation in Progress</h3>
              <p className="text-gray-600 mb-4">
                The evaluation is currently running. Results will be available when it completes.
              </p>
              {run.started_at && (
                <p className="text-sm text-gray-500">
                  Started: {new Date(run.started_at).toLocaleString()}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Quality gates (threshold vs actual for this run) */}
        {isCompleted &&
          run.quality_gates?.gates &&
          Object.keys(run.quality_gates.gates).length > 0 && (
            <div className="mb-6">
              <RAGQualityGatesDetailTable
                className="shadow-sm"
                gates={run.quality_gates.gates}
                title={
                  run.quality_gates.all_passed
                    ? 'Quality gates: all passed'
                    : 'Quality gates: failures blocking promotion'
                }
                subtitle="Compared against your product’s configured RAG quality thresholds."
              />
            </div>
          )}

        {/* Aggregate Metrics */}
        {isCompleted && aggregate && Object.keys(aggregate).length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Aggregate Metrics</h2>
            {hideRetrievalMetrics && (
              <p className="text-sm text-gray-600 mb-4">
                Retrieval ranking metrics (MRR, NDCG, recall@K, etc.) are omitted for Q&amp;A and adversarial
                datasets. Create a <span className="font-medium">golden retrieval</span> dataset to evaluate those.
              </p>
            )}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
              {aggregateEntries.map(([metricName, data]) => {
                // Sort metrics: standard metrics first, then retrieval metrics
                const isStandardMetric = ['groundedness', 'context_relevance', 'answer_relevance', 'answer_correctness', 'citation_coverage', 'refusal_correctness'].includes(metricName)
                const isRetrievalMetric = metricName.startsWith('retrieval_')
                
                return (
                  <div 
                    key={metricName} 
                    className={`border border-gray-200 rounded-lg p-4 ${
                      isStandardMetric ? 'bg-blue-50 border-blue-300' : 
                      isRetrievalMetric ? 'bg-purple-50 border-purple-300' : 
                      'bg-gray-50'
                    }`}
                  >
                    <p className="text-xs font-medium text-gray-700 mb-1 capitalize">
                      {metricName.replace(/_/g, ' ')}
                    </p>
                    <p className="text-2xl font-bold text-gray-900">
                      {(data.mean * 100).toFixed(1)}%
                    </p>
                    <p className="text-xs text-gray-600 mt-1">
                      Min: {(data.min * 100).toFixed(1)}% • Max: {(data.max * 100).toFixed(1)}%
                    </p>
                    <p className="text-xs text-gray-500">Count: {data.count}</p>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Per-Query Results */}
        {isCompleted && totalQueries > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Per-Query Results ({totalQueries})
              </h2>
            </div>
            {loadingQueries ? (
              <div className="p-8 text-center">
                <Loader2 className="h-6 w-6 animate-spin mx-auto text-gray-400" />
                <p className="text-sm text-gray-500 mt-2">Loading queries...</p>
              </div>
            ) : (
              <>
                <div className="divide-y divide-gray-200">
                  {perQuery.map((result, index) => (
                <div key={result.item_id || index} className="p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <p className="text-sm font-medium text-gray-900 mb-2">{result.query}</p>
                      {result.error ? (
                        <div className="bg-red-50 border border-red-200 rounded p-3">
                          <p className="text-sm font-medium text-red-900 mb-1">Error</p>
                          <p className="text-sm text-red-700">{result.error}</p>
                        </div>
                      ) : (
                        <div>
                          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 mb-3">
                            {Object.entries(result.metrics || {}).filter(([name]) => {
                              if (!hideRetrievalMetrics) return true
                              return !name.startsWith('retrieval_')
                            }).map(([metricName, metricData]) => {
                              // Handle both dict format (with score, passed) and direct score value
                              const score = typeof metricData === 'object' && metricData !== null 
                                ? (metricData.score ?? metricData) 
                                : metricData
                              const passed = typeof metricData === 'object' && metricData !== null 
                                ? (metricData.passed ?? false)
                                : undefined
                              const displayScore = typeof score === 'number' ? score : 0
                              
                              return (
                                <div key={metricName} className="flex items-start border border-gray-200 rounded p-2 bg-gray-50">
                                  {passed !== undefined && (
                                    <div className="mr-2 mt-0.5">
                                      {passed ? (
                                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                                      ) : (
                                        <XCircle className="h-4 w-4 text-red-600" />
                                      )}
                                    </div>
                                  )}
                                  <div className="flex-1 min-w-0">
                                    <p className="text-xs text-gray-500 capitalize truncate" title={metricName.replace(/_/g, ' ')}>
                                      {metricName.replace(/_/g, ' ')}
                                    </p>
                                    <p className="text-sm font-medium text-gray-900">
                                      {(displayScore * 100).toFixed(1)}%
                                    </p>
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                          {result.retrieved_chunks_count !== undefined && (
                            <div className="text-xs text-gray-500 mt-2">
                              Retrieved {result.retrieved_chunks_count} chunk{result.retrieved_chunks_count !== 1 ? 's' : ''} • 
                              Answer method: {result.answer_method || 'N/A'}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                  ))}
                </div>
                {/* Pagination Controls */}
                {totalQueries > DEFAULT_ITEMS_PER_PAGE && (
                  <div className="mt-4 flex items-center justify-between border-t border-gray-200 px-6 py-4 bg-white">
                    <div className="text-sm text-gray-700">
                      Showing {currentPage * DEFAULT_ITEMS_PER_PAGE + 1} to{' '}
                      {Math.min((currentPage + 1) * DEFAULT_ITEMS_PER_PAGE, totalQueries)} of{' '}
                      {totalQueries} queries
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadQueries(currentPage - 1)}
                        disabled={currentPage === 0 || loadingQueries}
                        className="px-3 py-1.5"
                      >
                        Previous
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadQueries(currentPage + 1)}
                        disabled={(currentPage + 1) * DEFAULT_ITEMS_PER_PAGE >= totalQueries || loadingQueries}
                        className="px-3 py-1.5"
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Empty State for non-completed runs */}
        {!isRunning && !isCompleted && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <BarChart3 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              {run.status === 'failed' ? 'Evaluation Failed' : 'Evaluation Pending'}
            </h3>
            <p className="text-gray-600">
              {run.status === 'failed'
                ? 'The evaluation encountered an error. Please check the logs or try running again.'
                : 'The evaluation has not started yet.'}
            </p>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
