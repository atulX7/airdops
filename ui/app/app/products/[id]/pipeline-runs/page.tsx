'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import React from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Play, Clock, CheckCircle, XCircle, AlertTriangle, Loader2, X, Eye, Square, Settings, Package } from 'lucide-react'
import { Button } from '@/components/ui/button'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient, PipelineRun } from '@/lib/api-client'
import { useToast } from '@/components/ui/toast'
import PipelineDetailsModal from '@/components/PipelineDetailsModal'
import ChunkingConfigModal from '@/components/ChunkingConfigModal'
import ArtifactsModal from '@/components/ArtifactsModal'
import { RUNS_PER_PAGE } from '@/lib/constants'

// Map technical gate names to user-friendly display names
const getFriendlyGateName = (gateName: string): string => {
  const gateNameMap: Record<string, string> = {
    'groundedness_min': 'Groundedness',
    'citation_coverage_min': 'Citation Coverage',
    'refusal_correctness_min': 'Refusal Correctness',
    'context_relevance_min': 'Context Relevance',
    'answer_relevance_min': 'Answer Relevance',
    'hallucination_rate_max': 'Hallucination Rate',
    'hallucination_rate': 'Hallucination Rate',
    'acl_leakage_max': 'ACL Leakage',
    'acl_leakage': 'ACL Leakage',
  }
  
  // Remove common suffixes and get friendly name
  const baseName = gateName.replace(/_min$|_max$/, '')
  return gateNameMap[gateName] || gateNameMap[baseName] || gateName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

// Format failed gates list for display
const formatFailedGates = (gates: string[]): string[] => {
  // Remove duplicates and sort
  const uniqueGates = Array.from(new Set(gates))
  return uniqueGates.map(gate => getFriendlyGateName(gate)).sort()
}

export default function PipelineRunsPage() {
  const params = useParams()
  const router = useRouter()
  const productId = params.id as string
  const { addToast } = useToast()

  const [pipelineRuns, setPipelineRuns] = useState<PipelineRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [polling, setPolling] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [pipelineConflict, setPipelineConflict] = useState<any>(null)
  const [currentPage, setCurrentPage] = useState(0)
  const [totalRuns, setTotalRuns] = useState(0)
  const [product, setProduct] = useState<any>(null)
  const [promotingVersion, setPromotingVersion] = useState<number | null>(null)
  const [selectedRunForDetails, setSelectedRunForDetails] = useState<PipelineRun | null>(null)
  const [selectedChunkingConfig, setSelectedChunkingConfig] = useState<any | null>(null)
  const [loadingChunkingConfig, setLoadingChunkingConfig] = useState(false)
  const [selectedArtifacts, setSelectedArtifacts] = useState<any[]>([])
  const [loadingArtifacts, setLoadingArtifacts] = useState(false)
  const [artifactsRunVersion, setArtifactsRunVersion] = useState<number | null>(null)
  const [showPromoteConfirm, setShowPromoteConfirm] = useState(false)
  const [pendingPromoteVersion, setPendingPromoteVersion] = useState<number | null>(null)
  const [qualityGatesStatus, setQualityGatesStatus] = useState<{ blocking: boolean; failedGates?: string[] } | null>(null)
  const [showPipelineModal, setShowPipelineModal] = useState(false)
  
  // Ref to track the polling interval
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  // Ref to track latest pipelineRuns state for checking inside interval callback
  const pipelineRunsRef = useRef<PipelineRun[]>([])
  // State for current time to update duration in real-time
  const [currentTime, setCurrentTime] = useState(new Date())
  // Ref to track the duration update interval
  const durationIntervalRef = useRef<NodeJS.Timeout | null>(null)

  const loadProduct = useCallback(async () => {
    try {
      const response = await apiClient.getProduct(productId)
      if (response.error) {
        console.error('Failed to load product:', response.error)
      } else if (response.data) {
        setProduct(response.data)
      }
    } catch (err) {
      console.error('Failed to load product:', err)
    }
  }, [productId])

  const loadPipelineRuns = useCallback(async (page: number, showLoading = true) => {
    if (showLoading) setLoading(true)
    setError(null)
    
    try {
      const offset = page * RUNS_PER_PAGE
      const response = await apiClient.getPipelineRuns(productId, RUNS_PER_PAGE, offset)
      
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load pipeline runs: ${response.error}`,
        })
      } else if (response.data) {
        // Handle both old format (array) and new format (object with runs, total, etc.)
        if (Array.isArray(response.data)) {
          setPipelineRuns(response.data)
          setTotalRuns(response.data.length)
        } else {
          setPipelineRuns(response.data.runs || [])
          setTotalRuns(response.data.total || 0)
        }
        setCurrentPage(page)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load pipeline runs'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }, [productId, addToast])

  useEffect(() => {
    loadProduct()
    loadPipelineRuns(0, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId]) // Only reload when productId changes

  // Update pipelineRunsRef whenever pipelineRuns changes
  useEffect(() => {
    pipelineRunsRef.current = pipelineRuns
  }, [pipelineRuns])

  // Update current time every second ONLY for running pipelines
  useEffect(() => {
    const hasRunningRuns = pipelineRuns.some(
      (run) => run.status === 'running' || run.status === 'queued'
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
  }, [pipelineRuns])

  // Check if we need to start polling when pipelineRuns changes
  // This only starts polling if there are running runs and we're not already polling
  useEffect(() => {
    const hasRunningRuns = pipelineRuns.some(
      (run) => run.status === 'running' || run.status === 'queued'
    )

    // Only start polling if:
    // 1. There are running runs
    // 2. We're not already polling (interval doesn't exist)
    if (hasRunningRuns && !intervalRef.current) {
      setPolling(true)
      intervalRef.current = setInterval(() => {
        loadPipelineRuns(currentPage, false).then(() => {
          // Check the latest state from ref after loading
          const stillHasRunning = pipelineRunsRef.current.some(
            (run) => run.status === 'running' || run.status === 'queued'
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
      }, 10000) // Poll every 10 seconds when pipelines are running
    }
    // Only re-check when pipelineRuns changes, but don't recreate interval unnecessarily
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineRuns, currentPage, loadPipelineRuns])

  // Poll for running pipelines - cleanup effect
  useEffect(() => {
    // This effect handles cleanup when dependencies change
    // The actual polling start is handled by the effect above
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      setPolling(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadPipelineRuns, currentPage])

  const handleTriggerPipeline = async (forceRun: boolean = false) => {
    setTriggering(true)
    setPipelineConflict(null)
    try {
      const response = await apiClient.triggerPipeline(productId, undefined, forceRun)
      
      if (response.error) {
        // Check if it's a conflict error (409)
        if (response.status === 409) {
          // Handle both structured errorData and plain error messages
          const conflictData = response.errorData && typeof response.errorData === 'object' 
            ? response.errorData 
            : { message: response.error || 'A pipeline run is already in progress' }
          setPipelineConflict(conflictData)
          return
        }
        
        addToast({
          type: 'error',
          message: typeof response.error === 'string' ? response.error : 'Failed to trigger pipeline',
        })
      } else if (response.data) {
        addToast({
          type: 'success',
          message: `Pipeline run triggered successfully. Version: ${response.data.version}`,
        })
        // Immediately refresh runs to detect the new pipeline and start polling
        await loadPipelineRuns(currentPage, false)
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to trigger pipeline',
      })
    } finally {
      setTriggering(false)
    }
  }

  const handleCancelRun = async (runId: string) => {
    try {
      const response = await apiClient.cancelPipelineRun(runId)
      if (response.error) {
        addToast({
          type: 'error',
          message: `Failed to cancel run: ${response.error}`,
        })
      } else {
        addToast({
          type: 'success',
          message: 'Pipeline run cancelled successfully',
        })
        loadPipelineRuns(currentPage, false)
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to cancel run',
      })
    }
  }

  const handlePromoteVersion = async (version: number, forceOverride: boolean = false) => {
    if (!product) return
    
    setPromotingVersion(version)
    try {
      const response = await apiClient.promoteVersion(product.id, version, forceOverride)
      
      if (response.error) {
        // Check if error is about quality gates
        if (typeof response.error === 'string' && response.error.includes('Quality gates failed')) {
          // Extract failed gates from error message
          const failedGatesMatch = response.error.match(/Failed gates: ([^.]+)/)
          const failedGates = failedGatesMatch ? failedGatesMatch[1].split(', ') : []
          setQualityGatesStatus({ blocking: true, failedGates })
          setPendingPromoteVersion(version)
          setShowPromoteConfirm(true)
          setPromotingVersion(null)
          return
        }
        
        addToast({
          type: 'error',
          message: typeof response.error === 'string' ? response.error : 'Failed to promote version',
        })
      } else {
        addToast({
          type: 'success',
          message: `Version ${version} has been promoted to production successfully${forceOverride ? ' (quality gates overridden)' : ''}`,
        })
        
        // Refresh product data to get updated promoted_version
        await loadProduct()
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to promote version',
      })
    } finally {
      setPromotingVersion(null)
    }
  }

  const handleConfirmPromote = async () => {
    if (pendingPromoteVersion) {
      await handlePromoteVersion(pendingPromoteVersion, true)
      setShowPromoteConfirm(false)
      setPendingPromoteVersion(null)
      setQualityGatesStatus(null)
    }
  }

  const getStatusIcon = (status: PipelineRun['status']) => {
    switch (status) {
      case 'queued':
        return <Clock className="h-4 w-4 text-gray-500" />
      case 'running':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case 'succeeded':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'ready_with_warnings':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />
      case 'failed_policy':
        return <XCircle className="h-4 w-4 text-orange-500" />
      default:
        return <Clock className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusColor = (status: PipelineRun['status']) => {
    switch (status) {
      case 'queued':
        return 'bg-gray-100 text-gray-800'
      case 'running':
        return 'bg-blue-100 text-blue-800'
      case 'succeeded':
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'ready_with_warnings':
        return 'bg-yellow-100 text-yellow-800'
      case 'failed_policy':
        return 'bg-orange-100 text-orange-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  // Memoized duration cell component to prevent unnecessary re-renders
  const DurationCell = React.memo(({ run, currentTime }: { run: PipelineRun, currentTime: Date }) => {
    const duration = useMemo(() => {
      if (!run.started_at) return 'N/A'
      
      const start = new Date(run.started_at)
      const end = run.finished_at 
        ? new Date(run.finished_at) 
        : (run.status === 'running' || run.status === 'queued') 
          ? currentTime 
          : new Date()
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
    
    return <div className="text-sm text-gray-900">{duration}</div>
  })
  
  DurationCell.displayName = 'DurationCell'

  // Keep formatDuration for backward compatibility (if used elsewhere)
  const formatDuration = (startedAt?: string, finishedAt?: string) => {
    if (!startedAt) return 'N/A'
    
    const start = new Date(startedAt)
    const end = finishedAt ? new Date(finishedAt) : new Date()
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

  const getAirdStagesInfo = (metrics: PipelineRun['metrics']) => {
    const stages = metrics?.aird_stages || {}
    const completed = metrics?.aird_stages_completed || []
    
    if (Object.keys(stages).length === 0 && completed.length === 0) {
      return null
    }
    
    return {
      total: Object.keys(stages).length,
      completed: completed.length,
      stages: Object.keys(stages),
    }
  }

  const getChunkingConfigForRun = (run: PipelineRun) => {
    // For successful runs, always return config (even if empty) to show the button
    if (run.status === 'succeeded') {
      // First check if it's in run.metrics (from backend, stored during execution)
      if (run.metrics?.chunking_config?.resolved_settings) {
        return run.metrics.chunking_config.resolved_settings
      }
      // Fallback to product chunking_config (for backward compatibility)
      if (product?.chunking_config?.resolved_settings) {
        return product.chunking_config.resolved_settings
      }
      // Return empty object to indicate config should be shown but is not available
      return {}
    }
    return null
  }

  const formatChunkingConfigSummary = (config: any) => {
    if (!config) return null
    const parts = []
    if (config.chunk_size) parts.push(`Size: ${config.chunk_size}`)
    if (config.chunk_overlap !== undefined) parts.push(`Overlap: ${config.chunk_overlap}`)
    if (config.chunking_strategy) parts.push(`Strategy: ${config.chunking_strategy.replace(/_/g, ' ')}`)
    if (config.content_type) parts.push(`Content: ${config.content_type.replace(/_/g, ' ')}`)
    if (config.source_quality) parts.push(`Source: ${config.source_quality.replace(/_/g, ' ')}`)
    return parts.length > 0 ? parts.join(', ') : 'Available'
  }

  const handleViewDetails = (run: PipelineRun) => {
    setSelectedRunForDetails(run)
  }

  const handleCloseDetails = () => {
    setSelectedRunForDetails(null)
  }

  const handlePipelineCancelled = () => {
    loadPipelineRuns(currentPage, false)
  }

  const handleViewChunkingConfig = async (run: PipelineRun) => {
    setLoadingChunkingConfig(true)
    setSelectedChunkingConfig(null)
    
    try {
      // First check if we already have it in run.metrics or product
      const existingConfig = getChunkingConfigForRun(run)
      if (existingConfig && Object.keys(existingConfig).length > 0) {
        setSelectedChunkingConfig(existingConfig)
        setLoadingChunkingConfig(false)
        return
      }

      // If not, fetch from API
      const response = await apiClient.getPipelineChunkingConfig(run.id!)
      if (response.error || !response.data?.resolved_settings) {
        setSelectedChunkingConfig({}) // Show empty config message
      } else {
        setSelectedChunkingConfig(response.data.resolved_settings)
      }
    } catch (err) {
      console.error('Failed to fetch chunking config:', err)
      addToast({
        type: 'error',
        message: 'Failed to fetch chunking configuration',
      })
      setSelectedChunkingConfig({}) // Show empty config message
    } finally {
      setLoadingChunkingConfig(false)
    }
  }

  const handleViewArtifacts = async (run: PipelineRun) => {
    setLoadingArtifacts(true)
    setSelectedArtifacts([])
    setArtifactsRunVersion(run.version)
    
    try {
      // Pass pipeline_run_id for more reliable querying - this ensures we get artifacts
      // for this specific run even if version hasn't been fully propagated yet
      const response = await apiClient.getPipelineArtifacts(productId, run.version, run.id)
      if (response.error) {
        addToast({
          type: 'error',
          message: 'Failed to fetch artifacts',
        })
        setSelectedArtifacts([])
      } else {
        setSelectedArtifacts(response.data.artifacts || [])
      }
    } catch (err) {
      console.error('Failed to fetch artifacts:', err)
      addToast({
        type: 'error',
        message: 'Failed to fetch artifacts',
      })
      setSelectedArtifacts([])
    } finally {
      setLoadingArtifacts(false)
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }

  return (
    <AppLayout>
      <div className="w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-6">
          <Link
            href={`/app/products/${productId}`}
            className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900 mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Product
          </Link>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Pipeline Runs</h1>
              <p className="mt-2 text-sm text-gray-600">
                Monitor and manage data processing pipeline execution runs
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                onClick={() => setShowPipelineModal(true)}
                disabled={triggering}
                className="flex items-center gap-2"
              >
                <Play className="h-4 w-4" />
                {triggering ? 'Triggering...' : 'Run Pipeline'}
              </Button>
            </div>
          </div>
        </div>

        {/* Pipeline Conflict Modal */}
        {pipelineConflict && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
              <div className="flex items-center mb-4">
                <AlertTriangle className="h-6 w-6 text-orange-600 mr-3" />
                <h3 className="text-lg font-semibold text-gray-900">Pipeline Already Running</h3>
              </div>
              <div className="mb-6">
                <p className="text-sm text-gray-700 mb-2">
                  {pipelineConflict.message || 'A pipeline run is already in progress for this product and version.'}
                </p>
                {pipelineConflict.existing_status && (
                  <p className="text-sm text-gray-600">
                    Current status: <strong>{pipelineConflict.existing_status}</strong>
                  </p>
                )}
                <p className="text-sm text-gray-600 mt-3">
                  {pipelineConflict.suggestion || 'You can force run to cancel the existing run and start a new one, or wait for the current run to complete.'}
                </p>
              </div>
              <div className="flex justify-end space-x-3">
                <Button
                  variant="outline"
                  onClick={() => setPipelineConflict(null)}
                  disabled={triggering}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => handleTriggerPipeline(true)}
                  disabled={triggering}
                  className="bg-orange-600 hover:bg-orange-700 text-white"
                >
                  {triggering ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Starting...
                    </>
                  ) : (
                    'Force Run (Override)'
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-center">
              <XCircle className="h-5 w-5 text-red-600 mr-2" />
              <p className="text-sm text-red-800">{error}</p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && pipelineRuns.length === 0 ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <Loader2 className="h-8 w-8 text-gray-400 animate-spin mx-auto mb-4" />
            <p className="text-gray-600">Loading pipeline runs...</p>
          </div>
        ) : pipelineRuns.length === 0 ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <Clock className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No pipeline runs yet</h3>
            <p className="text-gray-600 mb-6">
              Trigger a data processing pipeline run to start processing your data product.
            </p>
            <Button onClick={() => setShowPipelineModal(true)} disabled={triggering}>
              <Play className="h-4 w-4 mr-2" />
              {triggering ? 'Triggering...' : 'Run First Pipeline'}
            </Button>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Version
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Started
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Duration
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      AIRD Stages
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Chunking Config
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Artifacts
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {pipelineRuns.map((run) => {
                    const chunkingConfig = getChunkingConfigForRun(run)
                    const configSummary = formatChunkingConfigSummary(chunkingConfig)
                    return (
                      <tr key={run.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center space-x-2">
                            <span className="text-sm font-medium text-gray-900">v{run.version}</span>
                            {product?.promoted_version === run.version && (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gradient-to-r from-purple-500 to-pink-600 text-white shadow-sm">
                                🚀 PROD
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            {getStatusIcon(run.status || 'unknown')}
                            <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(run.status || 'unknown')}`}>
                              {(run.status || 'unknown').replace(/_/g, ' ')}
                            </span>
                          </div>
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
                        <td className="px-6 py-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleViewDetails(run)}
                            className="flex items-center gap-1"
                          >
                            <Eye className="h-4 w-4" />
                            View Stages
                          </Button>
                        </td>
                        <td className="px-6 py-4">
                          {chunkingConfig !== null ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleViewChunkingConfig(run)}
                              disabled={loadingChunkingConfig}
                              className="flex items-center gap-1"
                            >
                              {loadingChunkingConfig ? (
                                <>
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                  Loading...
                                </>
                              ) : (
                                <>
                                  <Settings className="h-4 w-4" />
                                  View Config
                                </>
                              )}
                            </Button>
                          ) : (
                            <span className="text-sm text-gray-400">No config</span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          {run.status === 'succeeded' ? (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleViewArtifacts(run)}
                                disabled={loadingArtifacts}
                                className="flex items-center gap-1"
                              >
                                {loadingArtifacts ? (
                                  <>
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    Loading...
                                  </>
                                ) : (
                                  <>
                                    <Package className="h-4 w-4" />
                                    View Artifacts
                                  </>
                                )}
                              </Button>
                            </>
                          ) : (
                            <span className="text-sm text-gray-400">—</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            {(run.status === 'running' || run.status === 'queued') && run.id && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleCancelRun(run.id!)}
                                className="text-red-600 hover:text-red-700 hover:bg-red-50"
                              >
                                <Square className="h-4 w-4 mr-1 fill-current" />
                                Stop
                              </Button>
                            )}
                            {run.status === 'succeeded' && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handlePromoteVersion(run.version)}
                                disabled={promotingVersion === run.version || product?.promoted_version === run.version}
                                className={
                                  product?.promoted_version === run.version
                                    ? 'bg-green-100 text-green-800 hover:bg-green-100 cursor-default'
                                    : promotingVersion === run.version
                                    ? 'bg-gray-100 text-gray-500 cursor-not-allowed'
                                    : 'bg-blue-100 text-blue-800 hover:bg-blue-200'
                                }
                              >
                                {product?.promoted_version === run.version
                                  ? '✓ Promoted'
                                  : promotingVersion === run.version
                                  ? 'Promoting...'
                                  : 'Promote to Prod'}
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {/* Pagination Controls */}
            {totalRuns > RUNS_PER_PAGE && (
              <div className="mt-4 flex items-center justify-between border-t border-gray-200 px-6 py-4 bg-white">
                <div className="text-sm text-gray-700">
                  Showing {currentPage * RUNS_PER_PAGE + 1} to{' '}
                  {Math.min((currentPage + 1) * RUNS_PER_PAGE, totalRuns)} of{' '}
                  {totalRuns} runs
                </div>
                <div className="flex space-x-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => loadPipelineRuns(currentPage - 1)}
                    disabled={currentPage === 0 || loading}
                    className="px-3 py-1.5"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => loadPipelineRuns(currentPage + 1)}
                    disabled={(currentPage + 1) * RUNS_PER_PAGE >= totalRuns || loading}
                    className="px-3 py-1.5"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Polling Indicator */}
        {polling && (
          <div className="mt-4 text-center">
            <p className="text-sm text-gray-500 flex items-center justify-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Auto-refreshing pipeline status...
            </p>
          </div>
        )}

        {/* Quality Gates Confirmation Modal */}
        {showPromoteConfirm && pendingPromoteVersion && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
              <div className="flex items-start gap-4">
                <AlertTriangle className="h-6 w-6 text-yellow-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">
                    Quality Gates Failed
                  </h3>
                  <p className="text-sm text-gray-600 mb-4">
                    Version {pendingPromoteVersion} has failed quality gates and is blocking promotion to production.
                  </p>
                  {qualityGatesStatus?.failedGates && qualityGatesStatus.failedGates.length > 0 && (
                    <div className="mb-4">
                      <p className="text-sm font-medium text-gray-700 mb-2">Failed Quality Gates:</p>
                      <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                        {formatFailedGates(qualityGatesStatus.failedGates).map((gate, idx) => (
                          <li key={idx}>{gate}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-sm text-gray-600 mb-4">
                    Are you sure you want to promote this version anyway? This action will override the quality gates.
                  </p>
                  <div className="flex gap-3 justify-end">
                    <Button
                      variant="outline"
                      onClick={() => {
                        setShowPromoteConfirm(false)
                        setPendingPromoteVersion(null)
                        setQualityGatesStatus(null)
                      }}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="default"
                      onClick={handleConfirmPromote}
                      className="bg-yellow-600 hover:bg-yellow-700 text-white"
                    >
                      Promote Anyway
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Pipeline Details Modal */}
        {selectedRunForDetails && (
          <PipelineDetailsModal
            isOpen={!!selectedRunForDetails}
            onClose={handleCloseDetails}
            runId={selectedRunForDetails.id!}
            runVersion={selectedRunForDetails.version}
            runStatus={selectedRunForDetails.status || 'unknown'}
            initialMetrics={selectedRunForDetails.metrics}
            onPipelineCancelled={handlePipelineCancelled}
          />
        )}

        {/* Chunking Config Modal */}
        <ChunkingConfigModal
          isOpen={!!selectedChunkingConfig}
          onClose={() => setSelectedChunkingConfig(null)}
          config={selectedChunkingConfig}
        />

        {/* Artifacts Modal */}
        <ArtifactsModal
          isOpen={artifactsRunVersion !== null}
          onClose={() => {
            setSelectedArtifacts([])
            setArtifactsRunVersion(null)
          }}
          artifacts={selectedArtifacts}
          loading={loadingArtifacts}
        />

        {/* Pipeline Modal */}
        {showPipelineModal && (
          <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
            <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
              <div className="mt-3">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Run Pipeline</h3>
                <p className="text-sm text-gray-600 mb-4">
                  Run the complete data processing pipeline for this product. This will:
                </p>
                <ul className="text-sm text-gray-600 mb-6 space-y-1">
                  <li>• Automatically ingest data from all data sources</li>
                  <li>• Clean and preprocess the data</li>
                  <li>• Score chunks with AI-Ready metrics (coherence, noise detection, boundary quality)</li>
                  <li>• Generate readiness fingerprint</li>
                  <li>• Evaluate policy compliance</li>
                  <li>• Chunk documents for processing</li>
                  <li>• Generate embeddings</li>
                  <li>• Index to vector database for search</li>
                  <li>• Validate and finalize</li>
                </ul>
                <div className="flex justify-end space-x-3">
                  <Button
                    variant="outline"
                    onClick={() => setShowPipelineModal(false)}
                    disabled={triggering}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={() => {
                      setShowPipelineModal(false)
                      handleTriggerPipeline(false)
                    }}
                    disabled={triggering}
                    className="bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    {triggering ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                        Starting...
                      </>
                    ) : (
                      'Run Pipeline'
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}




