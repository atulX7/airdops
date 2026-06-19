'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import React from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Play, BarChart3, Download, Eye, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ResultModal, ConfirmModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/ui/status-badge'
import { EVALUATIONS_PER_PAGE } from '@/lib/constants'
import type { QualityGatesPayload } from '@/lib/rag-quality-gates'
import { gatesFailedCount, gatesTotalCount } from '@/lib/rag-quality-gates'
import { RAGQualityGatesDetailTable } from '@/components/RAGQualityGatesDetailTable'

interface Product {
  id: string
  name: string
  current_version: number
  promoted_version?: number
}

interface EvaluationDataset {
  id: string
  name: string
  dataset_type: string
}

interface EvaluationRun {
  id: string
  product_id: string
  version: number
  status: 'pending' | 'running' | 'completed' | 'failed' | 'queued'
  metrics?: {
    aggregate?: Record<string, {
      mean: number
      min: number
      max: number
      count: number
    }>
    per_query?: Array<{
      query: string
      metrics: Record<string, any>
    }>
  }
  started_at?: string
  finished_at?: string
  created_at: string
  report_path?: string
  dag_run_id?: string | null
  dataset_name?: string | null
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

export default function EvaluationsPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string

  const [product, setProduct] = useState<Product | null>(null)
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([])
  const [runs, setRuns] = useState<EvaluationRun[]>([])
  const [pipelineRuns, setPipelineRuns] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [selectedDataset, setSelectedDataset] = useState<string>('')
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [polling, setPolling] = useState(false)
  const [downloadingReport, setDownloadingReport] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(0)
  const [totalRuns, setTotalRuns] = useState(0)
  const [expandedRunIds, setExpandedRunIds] = useState<Set<string>>(() => new Set())

  // Ref to track the polling interval
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  // Ref to track latest runs state for checking inside interval callback
  const runsRef = useRef<EvaluationRun[]>([])
  // State for current time to update duration in real-time
  const [currentTime, setCurrentTime] = useState(new Date())
  // Ref to track the duration update interval
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null)

  const [showResultModal, setShowResultModal] = useState(false)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const toggleRunGatesExpanded = (runId: string) => {
    setExpandedRunIds((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) {
        next.delete(runId)
      } else {
        next.add(runId)
      }
      return next
    })
  }

  const [resultModalData, setResultModalData] = useState<{
    type: 'success' | 'error' | 'warning' | 'info'
    title: string
    message: string
    actionButton?: {
      label: string
      onClick: () => void
      variant?: 'primary' | 'secondary'
    }
  } | null>(null)

  const loadData = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const productResponse = await apiClient.getProduct(productId)
      if (!productResponse.error && productResponse.data) {
        const productData = productResponse.data as Product
        setProduct(productData)
        // Don't auto-select version - let user choose explicitly
      }

      // Load pipeline runs to get available versions
      const pipelineRunsResponse = await apiClient.getPipelineRuns(productId, 100, 0)
      if (!pipelineRunsResponse.error && pipelineRunsResponse.data) {
        const runsData = Array.isArray(pipelineRunsResponse.data) 
          ? pipelineRunsResponse.data 
          : (pipelineRunsResponse.data as any)?.runs || []
        setPipelineRuns(runsData)
      }

      const datasetsResponse = await apiClient.listEvaluationDatasets(productId)
      if (!datasetsResponse.error && datasetsResponse.data) {
        const datasetsList = datasetsResponse.data as EvaluationDataset[]
        setDatasets(datasetsList)
        // Don't auto-select dataset - let user choose explicitly
      }

      // Load evaluation runs with pagination
      const offset = currentPage * EVALUATIONS_PER_PAGE
      const runsResponse = await apiClient.listEvaluationRuns(productId, EVALUATIONS_PER_PAGE, offset)
      if (!runsResponse.error && runsResponse.data) {
        // Handle both old format (array) and new format (object with runs, total, etc.)
        if (Array.isArray(runsResponse.data)) {
          setRuns(runsResponse.data as EvaluationRun[])
          setTotalRuns(runsResponse.data.length)
        } else {
          setRuns((runsResponse.data as any).runs || [])
          setTotalRuns((runsResponse.data as any).total || 0)
        }
      }
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [productId, currentPage]) // Add currentPage as dependency

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/')
      return
    }

    if (status === 'authenticated' && productId) {
      loadData()
    }
  }, [status, router, productId, loadData])

  // Update runsRef when runs change
  useEffect(() => {
    runsRef.current = runs
  }, [runs])

  // Update current time every second ONLY for running evaluations
  useEffect(() => {
    // Only update time for runs that are actually running and have started_at
    const hasRunningRuns = runs.some(
      (run) => (run.status === 'running' || run.status === 'queued' || run.status === 'pending')
        && run.started_at  // Only update if started_at exists
        && run.dag_run_id  // Only update if DAG was triggered
    )

    if (hasRunningRuns) {
      // Update every second for real-time duration
      durationIntervalRef.current = setInterval(() => {
        setCurrentTime(new Date())
      }, 1000)
    } else {
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current)
        durationIntervalRef.current = null
      }
    }

    return () => {
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current)
        durationIntervalRef.current = null
      }
    }
  }, [runs])

  // Check if we need to start polling when runs change
  useEffect(() => {
    // Only poll for runs that:
    // 1. Are in running/queued/pending status
    // 2. Have a dag_run_id (meaning they were successfully triggered)
    const hasRunningRuns = runs.some(
      (run) => (run.status === 'running' || run.status === 'queued' || run.status === 'pending') 
        && run.dag_run_id  // Only poll if DAG was actually triggered
    )

    // Only start polling if:
    // 1. There are running runs with DAG run IDs
    // 2. We're not already polling (interval doesn't exist)
    if (hasRunningRuns && !intervalRef.current) {
      setPolling(true)
      intervalRef.current = setInterval(() => {
        loadData(false).then(() => {
          // Check the latest state from ref after loading
          const stillHasRunning = runsRef.current.some(
            (run) => (run.status === 'running' || run.status === 'queued' || run.status === 'pending')
              && run.dag_run_id
          )
          
          if (!stillHasRunning) {
            // Stop polling if no running runs
            if (intervalRef.current) {
              clearInterval(intervalRef.current)
              intervalRef.current = null
            }
            setPolling(false)
          }
        })
      }, 10000) // Poll every 10 seconds when evaluations are running
    } else if (!hasRunningRuns && intervalRef.current) {
      // Stop polling if no running runs
      clearInterval(intervalRef.current)
      intervalRef.current = null
      setPolling(false)
    }
  }, [runs, loadData])

  // Poll for running evaluations - cleanup effect
  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [])

  const handleRunEvaluation = () => {
    if (!selectedDataset) {
      setResultModalData({
        type: 'error',
        title: 'No Dataset Selected',
        message: 'Please select a dataset to run evaluation'
      })
      setShowResultModal(true)
      return
    }

    if (selectedVersion === null) {
      setResultModalData({
        type: 'error',
        title: 'No Pipeline Version Selected',
        message: 'Please select a pipeline version to run evaluation'
      })
      setShowResultModal(true)
      return
    }

    // Show confirmation modal first
    setShowConfirmModal(true)
  }

  const confirmRunEvaluation = async () => {
    setShowConfirmModal(false)
    
    if (!selectedDataset || selectedVersion === null) {
      return
    }

    setRunning(true)
    try {
      
      const response = await apiClient.createEvaluationRun(productId, {
        dataset_id: selectedDataset,
        version: selectedVersion
      })

      if (response.error) {
        // Check for specific error messages and provide user-friendly responses
        let errorTitle = 'Evaluation Failed'
        let errorMessage = response.error
        let actionButton: { label: string; onClick: () => void; variant?: 'primary' | 'secondary' } | undefined = undefined
        
        // Check if error indicates no pipeline run
        if (response.error.includes('No data available') || 
            response.error.includes('run a pipeline first') ||
            response.error.includes('pipeline')) {
          errorTitle = 'Pipeline Required'
          errorMessage = 'No data available for evaluation. Please run a pipeline first to process your data before running evaluations.'
          actionButton = {
            label: 'Run Pipeline',
            onClick: () => {
              setShowResultModal(false)
              router.push(`/app/products/${productId}/pipeline-runs`)
            },
            variant: 'primary' as const
          }
        } else if (response.error.includes('Dataset does not belong')) {
          errorTitle = 'Invalid Dataset'
          errorMessage = 'The selected dataset does not belong to this product. Please select a different dataset.'
        }
        
        setResultModalData({
          type: 'error',
          title: errorTitle,
          message: errorMessage,
          actionButton
        })
        setShowResultModal(true)
      } else {
        // Success - immediately reload data to show the new run
        await loadData(true)
        
        setResultModalData({
          type: 'success',
          title: 'Evaluation Started',
          message: 'Evaluation run has been queued and will start shortly. You can monitor its progress below.'
        })
        setShowResultModal(true)
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Evaluation Failed',
        message: err instanceof Error ? err.message : 'An unexpected error occurred'
      })
      setShowResultModal(true)
    } finally {
      setRunning(false)
    }
  }

  const handleDownloadReport = async (runId: string) => {
    setDownloadingReport(runId)
    try {
      const result = await apiClient.downloadEvaluationReport(runId)
      
      if (!result || !result.blob) {
        throw new Error('Failed to download report')
      }

      // Determine filename and extension from response or default
      let filename: string
      let extension: string
      
      if (result.filename) {
        // Use filename from Content-Disposition header
        filename = result.filename
        extension = filename.split('.').pop() || 'csv'
      } else {
        // Determine extension from content type or default to CSV
        if (result.contentType?.includes('text/csv')) {
          extension = 'csv'
        } else if (result.contentType?.includes('application/pdf')) {
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
      setResultModalData({
        type: 'error',
        title: 'Download Failed',
        message: 'Failed to download the evaluation report. Please try again later.'
      })
      setShowResultModal(true)
    } finally {
      setDownloadingReport(null)
    }
  }

  // Memoized duration component
  const DurationCell = React.memo(({ run, currentTime }: { run: EvaluationRun, currentTime: Date }) => {
    const duration = useMemo(() => {
      // If no started_at, return N/A
      if (!run.started_at) return 'N/A'
      
      const start = new Date(run.started_at)
      
      // For completed/failed runs, use finished_at (don't update)
      if (run.status === 'completed' || run.status === 'failed') {
        if (run.finished_at) {
          const end = new Date(run.finished_at)
          const diff = end.getTime() - start.getTime()
          
          const seconds = Math.floor(diff / 1000)
          const minutes = Math.floor(seconds / 60)
          const hours = Math.floor(minutes / 60)
          
          if (hours > 0) {
            return `${hours}h ${minutes % 60}m`
          } else if (minutes > 0) {
            return `${minutes}m ${seconds % 60}s`
          } else {
            return `${seconds}s`
          }
        }
        return 'N/A'
      }
      
      // For running/queued/pending runs, use currentTime for real-time updates
      const end = currentTime
      const diff = end.getTime() - start.getTime()
      
      const seconds = Math.floor(diff / 1000)
      const minutes = Math.floor(seconds / 60)
      const hours = Math.floor(minutes / 60)
      
      if (hours > 0) {
        return `${hours}h ${minutes % 60}m`
      } else if (minutes > 0) {
        return `${minutes}m ${seconds % 60}s`
      } else {
        return `${seconds}s`
      }
    }, [run.started_at, run.finished_at, run.status, currentTime])
    
    return <div className="text-sm text-gray-500">{duration}</div>
  })
  
  DurationCell.displayName = 'DurationCell'

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6">
          <CardSkeleton />
        </div>
      </AppLayout>
    )
  }

  if (!product) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800">Product not found</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href={`/app/products/${productId}/rag-quality`} className="flex items-center text-sm text-gray-600 hover:text-gray-900 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Retrieval Evaluation
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Evaluations</span>
        </div>

        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Evaluation Runs</h1>
            <p className="mt-2 text-sm text-gray-600">
              Run evaluations on your datasets and view detailed results.
            </p>
            {pipelineRuns.filter((run: any) => run.status === 'succeeded' && run.version).length === 0 && (
              <div className="mt-3 bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                <div className="flex items-start">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3 flex-1">
                    <p className="text-sm text-yellow-800">
                      <strong>No successful pipeline run yet.</strong> You need to run a pipeline first to process your data before running evaluations.
                    </p>
                    <Link href={`/app/products/${productId}/pipeline-runs`} className="mt-2 inline-block">
                      <Button size="sm" className="bg-yellow-600 hover:bg-yellow-700 text-white">
                        Go to Pipeline Runs
                      </Button>
                    </Link>
                  </div>
                </div>
              </div>
            )}
          </div>
          {datasets.length > 0 && (
            <div className="flex items-center gap-3">
              {/* Dataset Selector */}
              <select
                aria-label="Dataset"
                value={selectedDataset || ''}
                onChange={(e) => {
                  const value = e.target.value
                  setSelectedDataset(value || '')
                }}
                className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm min-w-[150px]"
              >
                <option value="" disabled={!!selectedDataset}>
                  --Select Dataset--
                </option>
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
              {/* Pipeline Version Selector */}
              {pipelineRuns.filter((run: any) => run.status === 'succeeded' && run.version).length > 0 && (
                <select
                  aria-label="Pipeline Version"
                  value={selectedVersion || ''}
                  onChange={(e) => {
                    const value = e.target.value
                    setSelectedVersion(value ? parseInt(value) : null)
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm min-w-[180px]"
                >
                  <option value="" disabled={selectedVersion !== null}>
                    --Select Pipeline Version--
                  </option>
                  {/* Get unique successful pipeline versions */}
                  {(() => {
                    // Filter only succeeded pipeline runs and get unique versions
                    const successfulVersions = Array.from(
                      new Set(
                        pipelineRuns
                          .filter((run: any) => run.status === 'succeeded' && run.version)
                          .map((run: any) => run.version)
                      )
                    ).sort((a: number, b: number) => b - a) // Sort descending (newest first)
                    
                    // The first item in sorted array is the latest succeeded version
                    const latestVersion = successfulVersions.length > 0 ? successfulVersions[0] : null
                    
                    return successfulVersions.map((version: number) => (
                      <option key={version} value={version}>
                        Version {version} {version === latestVersion ? '(Latest)' : ''}
                        {product.promoted_version === version ? ' (Production)' : ''}
                      </option>
                    ))
                  })()}
                </select>
              )}
              <Button
                onClick={handleRunEvaluation}
                disabled={
                  running || 
                  !selectedDataset || 
                  selectedVersion === null || 
                  pipelineRuns.filter((run: any) => run.status === 'succeeded' && run.version).length === 0
                }
                className="flex items-center gap-2"
              >
                <Play className="h-4 w-4" />
                {running ? 'Triggering...' : 'Run Evaluation'}
              </Button>
            </div>
          )}
        </div>

        {/* Polling indicator */}
        {polling && (
          <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-center gap-2">
            <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
            <span className="text-sm text-blue-800">Auto-refreshing evaluation status...</span>
          </div>
        )}

        {/* Runs List */}
        {runs.length > 0 ? (
          <>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Version
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Dataset
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Pipeline Version
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Quality gates
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Started
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Duration
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {runs.map((run) => {
                      const isRunning = run.status === 'running' || run.status === 'queued' || run.status === 'pending'
                      const qg = run.quality_gates
                      const hasGateTable = Boolean(qg?.gates && Object.keys(qg.gates).length > 0)
                      const expanded = expandedRunIds.has(run.id)
                      const totalG = gatesTotalCount(qg?.gates)
                      const failedG = gatesFailedCount(qg?.gates)

                      return (
                        <React.Fragment key={run.id}>
                          <tr className="hover:bg-gray-50">
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm font-medium text-gray-900">v{run.version}</div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm text-gray-900">
                                {run.dataset_name || 'N/A'}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm text-gray-900">
                                {run.pipeline_version !== null && run.pipeline_version !== undefined 
                                  ? `v${run.pipeline_version}` 
                                  : 'N/A'}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <StatusBadge status={mapEvaluationStatus(run.status)} size="sm" />
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              {run.status === 'completed' && hasGateTable && qg ? (
                                <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-2">
                                  <span
                                    className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                                      qg.all_passed
                                        ? 'bg-green-100 text-green-800'
                                        : 'bg-red-100 text-red-800'
                                    }`}
                                  >
                                    {qg.all_passed ? 'Pass' : 'Fail'}
                                  </span>
                                  <span className="text-xs text-gray-600">
                                    {totalG - failedG}/{totalG} gates
                                  </span>
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 w-8 p-0 shrink-0"
                                    title={expanded ? 'Hide gate details' : 'Show gate details'}
                                    onClick={() => toggleRunGatesExpanded(run.id)}
                                  >
                                    {expanded ? (
                                      <ChevronDown className="h-4 w-4 text-gray-600" />
                                    ) : (
                                      <ChevronRight className="h-4 w-4 text-gray-600" />
                                    )}
                                  </Button>
                                </div>
                              ) : run.status === 'completed' ? (
                                <span className="text-sm text-gray-500">No metrics</span>
                              ) : (
                                <span className="text-sm text-gray-400">—</span>
                              )}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="text-sm text-gray-900">
                                {run.started_at
                                  ? new Date(run.started_at).toLocaleString()
                                  : 'Not started'}
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <DurationCell run={run} currentTime={currentTime} />
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="flex items-center gap-1">
                                {isRunning ? (
                                  <div className="flex items-center gap-2 text-sm text-blue-600">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    <span>Running</span>
                                  </div>
                                ) : (
                                  <>
                                    <Link href={`/app/products/${productId}/rag-quality/evaluations/${run.id}`}>
                                      <Button 
                                        variant="ghost" 
                                        size="sm" 
                                        className="h-8 w-8 p-0"
                                        title="View Details"
                                      >
                                        <Eye className="h-4 w-4" />
                                      </Button>
                                    </Link>
                                    {run.status === 'completed' && (
                                      <Button 
                                        variant="ghost" 
                                        size="sm"
                                        onClick={() => handleDownloadReport(run.id)}
                                        disabled={downloadingReport === run.id}
                                        className="h-8 w-8 p-0"
                                        title="Download Report"
                                      >
                                        {downloadingReport === run.id ? (
                                          <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : (
                                          <Download className="h-4 w-4" />
                                        )}
                                      </Button>
                                    )}
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                          {expanded && hasGateTable && qg?.gates ? (
                            <tr className="bg-gray-50/80">
                              <td colSpan={8} className="px-4 py-4 border-t border-gray-200">
                                <RAGQualityGatesDetailTable
                                  compact
                                  gates={qg.gates}
                                  title="Quality gates for this run"
                                  subtitle="Thresholds are the product’s configured RAG quality thresholds at the time of this request."
                                />
                              </td>
                            </tr>
                          ) : null}
                        </React.Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            {/* Pagination Controls */}
            {totalRuns > EVALUATIONS_PER_PAGE && (
              <div className="mt-4 flex items-center justify-between border-t border-gray-200 px-6 py-4 bg-white rounded-lg shadow-sm">
                <div className="text-sm text-gray-700">
                  Showing {currentPage * EVALUATIONS_PER_PAGE + 1} to{' '}
                  {Math.min((currentPage + 1) * EVALUATIONS_PER_PAGE, totalRuns)} of{' '}
                  {totalRuns} evaluations
                </div>
                <div className="flex space-x-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setCurrentPage(prev => Math.max(0, prev - 1))
                    }}
                    disabled={currentPage === 0 || loading}
                    className="px-3 py-1.5"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setCurrentPage(prev => prev + 1)
                    }}
                    disabled={(currentPage + 1) * EVALUATIONS_PER_PAGE >= totalRuns || loading}
                    className="px-3 py-1.5"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <BarChart3 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No evaluation runs yet</h3>
            <p className="text-gray-600 mb-6">
              {datasets.length === 0 
                ? 'Create a dataset first, then run your first evaluation.'
                : 'Run an evaluation to see results here.'}
            </p>
            {datasets.length === 0 ? (
              <Link href={`/app/products/${productId}/rag-quality/datasets`}>
                <Button className="flex items-center gap-2">
                  Create Dataset
                </Button>
              </Link>
            ) : (
              <div className="flex items-center justify-center gap-3">
                {/* Dataset Selector */}
                <select
                  aria-label="Dataset"
                  value={selectedDataset || ''}
                  onChange={(e) => {
                    const value = e.target.value
                    setSelectedDataset(value || '')
                  }}
                  className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm min-w-[150px]"
                >
                  <option value="" disabled={!!selectedDataset}>
                    --Select Dataset--
                  </option>
                  {datasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {dataset.name}
                    </option>
                  ))}
                </select>
                {/* Pipeline Version Selector */}
                {pipelineRuns.filter((run: any) => run.status === 'succeeded' && run.version).length > 0 && (
                  <select
                    aria-label="Pipeline Version"
                    value={selectedVersion || ''}
                    onChange={(e) => {
                      const value = e.target.value
                      setSelectedVersion(value ? parseInt(value) : null)
                    }}
                    className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm min-w-[180px]"
                  >
                    <option value="" disabled={selectedVersion !== null}>
                      --Select Pipeline Version--
                    </option>
                    {(() => {
                      // Filter only succeeded pipeline runs and get unique versions
                      const successfulVersions = Array.from(
                        new Set(
                          pipelineRuns
                            .filter((run: any) => run.status === 'succeeded' && run.version)
                            .map((run: any) => run.version)
                        )
                      ).sort((a: number, b: number) => b - a) // Sort descending (newest first)
                      
                      // The first item in sorted array is the latest succeeded version
                      const latestVersion = successfulVersions.length > 0 ? successfulVersions[0] : null
                      
                      return successfulVersions.map((version: number) => (
                        <option key={version} value={version}>
                          Version {version} {version === latestVersion ? '(Latest)' : ''}
                          {product.promoted_version === version ? ' (Production)' : ''}
                        </option>
                      ))
                    })()}
                  </select>
                )}
                <Button
                  onClick={handleRunEvaluation}
                  disabled={
                    !selectedDataset || 
                    selectedVersion === null || 
                    pipelineRuns.filter((run: any) => run.status === 'succeeded' && run.version).length === 0
                  }
                  className="flex items-center gap-2"
                >
                  <Play className="h-4 w-4" />
                  Run Evaluation
                </Button>
              </div>
            )}
          </div>
        )}

        {showResultModal && resultModalData && (
          <ResultModal
            isOpen={showResultModal}
            type={resultModalData.type}
            title={resultModalData.title}
            message={resultModalData.message}
            onClose={() => setShowResultModal(false)}
            actionButton={resultModalData.actionButton}
          />
        )}

        <ConfirmModal
          isOpen={showConfirmModal}
          onClose={() => setShowConfirmModal(false)}
          onConfirm={confirmRunEvaluation}
          title="Run Evaluation"
          message="Are you sure you want to run an evaluation on the selected dataset? This will evaluate your retrieval system's performance metrics including groundedness, context relevance, answer relevance, and citation coverage."
          confirmText="Run Evaluation"
          cancelText="Cancel"
          variant="info"
        />
      </div>
    </AppLayout>
  )
}
