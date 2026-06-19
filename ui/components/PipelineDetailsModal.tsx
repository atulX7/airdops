'use client'

import { useState, useEffect } from 'react'
import { X, CheckCircle, XCircle, Clock, Loader2, ChevronDown, ChevronUp, FileText, AlertTriangle, MinusCircle } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import { useToast } from '@/components/ui/toast'

// Pipeline task execution order (matches Airflow DAG dependencies)
const PIPELINE_TASK_ORDER = [
  'preprocess',
  'scoring',
  'fingerprint',
  'validation',
  'policy',
  'reporting',
  'indexing',
  'validate_data_quality',
  'finalize',
]

interface PipelineDetailsModalProps {
  isOpen: boolean
  onClose: () => void
  runId: string
  runVersion: number
  runStatus: string
  initialMetrics?: any
  onPipelineCancelled?: () => void
}

interface TaskLog {
  content?: string
  status?: string
  error?: string
}

export default function PipelineDetailsModal({
  isOpen,
  onClose,
  runId,
  runVersion,
  runStatus,
  initialMetrics,
  onPipelineCancelled,
}: PipelineDetailsModalProps) {
  const [logs, setLogs] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [expandedStages, setExpandedStages] = useState<Set<string>>(new Set())
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set())
  const { addToast } = useToast()

  useEffect(() => {
    if (isOpen && runId) {
      loadLogs()
    }
  }, [isOpen, runId])

  const loadLogs = async () => {
    setLoading(true)
    try {
      const response = await apiClient.getPipelineRunLogs(runId)
      if (response.error) {
        addToast({
          type: 'error',
          message: `Failed to load logs: ${response.error}`,
        })
      } else {
        setLogs(response.data)
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to load pipeline logs',
      })
    } finally {
      setLoading(false)
    }
  }

  const toggleStage = (stageName: string) => {
    const newExpanded = new Set(expandedStages)
    if (newExpanded.has(stageName)) {
      newExpanded.delete(stageName)
    } else {
      newExpanded.add(stageName)
    }
    setExpandedStages(newExpanded)
  }

  const toggleTask = (taskId: string) => {
    const newExpanded = new Set(expandedTasks)
    if (newExpanded.has(taskId)) {
      newExpanded.delete(taskId)
    } else {
      newExpanded.add(taskId)
    }
    setExpandedTasks(newExpanded)
  }

  const getStageStatusIcon = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'succeeded':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'running':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case 'skipped':
        return <MinusCircle className="h-4 w-4 text-yellow-500" />
      default:
        return <Clock className="h-4 w-4 text-gray-500" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'success':
      case 'succeeded':
        return 'bg-green-100 text-green-800'
      case 'failed':
        return 'bg-red-100 text-red-800'
      case 'running':
        return 'bg-blue-100 text-blue-800'
      case 'skipped':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  // Helper function to map task_id to stage_name
  const getStageFromTaskId = (taskId: string): string | null => {
    // Map task IDs to stage names
    const taskToStageMap: Record<string, string> = {
      'task_preprocess': 'preprocess',
      'task_scoring': 'scoring',
      'task_fingerprint': 'fingerprint',
      'task_validation': 'validation',
      'task_policy': 'policy',
      'task_reporting': 'reporting',
      'task_indexing': 'indexing',
      'task_validate_data_quality': 'validate_data_quality',
      'task_finalize': 'finalize',
    }
    
    // Check direct mapping
    if (taskToStageMap[taskId]) {
      return taskToStageMap[taskId]
    }
    
    // Fallback: try to extract stage name from task_id
    // e.g., "task_preprocess" -> "preprocess"
    const match = taskId.match(/^task_(.+)$/)
    return match ? match[1] : null
  }

  // Helper function to format skip reasons in a human-readable way
  const formatSkipReason = (reason: string): string => {
    const reasonMap: Record<string, string> = {
      'matplotlib_not_available': 'Matplotlib library is not installed. PDF report generation requires matplotlib to be installed.',
      'no_metrics': 'No metrics available. The reporting stage requires metrics from previous stages.',
      'no_processed_files': 'No processed files available. The indexing stage requires files from the preprocessing stage.',
    }
    
    // Return mapped reason or format the technical reason
    if (reasonMap[reason]) {
      return reasonMap[reason]
    }
    
    // Fallback: convert snake_case to Title Case
    return reason
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  }

  // Helper function to sort tasks by execution order
  const sortTasksByOrder = (tasks: [string, any][]): [string, any][] => {
    return tasks.sort(([taskA], [taskB]) => {
      const indexA = PIPELINE_TASK_ORDER.indexOf(taskA)
      const indexB = PIPELINE_TASK_ORDER.indexOf(taskB)
      // If task not in order list, put it at the end
      if (indexA === -1 && indexB === -1) return 0
      if (indexA === -1) return 1
      if (indexB === -1) return -1
      return indexA - indexB
    })
  }

  // Helper function to format duration
  const formatDuration = (startedAt: string | null, finishedAt: string | null): string | null => {
    if (!startedAt || !finishedAt) return null
    try {
      const start = new Date(startedAt)
      const end = new Date(finishedAt)
      const diffMs = end.getTime() - start.getTime()
      const diffSec = Math.floor(diffMs / 1000)
      const diffMin = Math.floor(diffSec / 60)
      const diffHour = Math.floor(diffMin / 60)
      
      if (diffHour > 0) {
        return `${diffHour}h ${diffMin % 60}m ${diffSec % 60}s`
      } else if (diffMin > 0) {
        return `${diffMin}m ${diffSec % 60}s`
      } else {
        return `${diffSec}s`
      }
    } catch {
      return null
    }
  }

  // Helper function to format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  // Helper function to format metrics in a human-readable way
  const formatStageMetrics = (stageName: string, metrics: any): Array<{ label: string; value: string; icon?: string }> => {
    if (!metrics || typeof metrics !== 'object') return []
    
    const formatted: Array<{ label: string; value: string; icon?: string }> = []
    
    // Common metrics across stages
    if (metrics.files_processed !== undefined) {
      formatted.push({ label: 'Files Processed', value: metrics.files_processed.toString(), icon: '📁' })
    }
    if (metrics.processed_file_list && Array.isArray(metrics.processed_file_list)) {
      formatted.push({ label: 'Files Processed', value: metrics.processed_file_list.length.toString(), icon: '📁' })
    }
    
    // Stage-specific metrics
    switch (stageName) {
      case 'preprocess':
        if (metrics.chunks_created !== undefined) {
          formatted.push({ label: 'Chunks Created', value: metrics.chunks_created.toLocaleString(), icon: '📝' })
        }
        if (metrics.sections !== undefined) {
          formatted.push({ label: 'Sections', value: metrics.sections.toString(), icon: '📑' })
        }
        if (metrics.mid_sentence_boundary_rate !== undefined) {
          formatted.push({ label: 'Boundary Quality', value: `${(metrics.mid_sentence_boundary_rate * 100).toFixed(1)}%`, icon: '✓' })
        }
        break
      
      case 'scoring':
        if (metrics.total_chunks !== undefined) {
          formatted.push({ label: 'Chunks Scored', value: metrics.total_chunks.toLocaleString(), icon: '📊' })
        }
        if (metrics.scored_files !== undefined) {
          formatted.push({ label: 'Files Scored', value: metrics.scored_files.toString(), icon: '📁' })
        }
        if (metrics.failed_files !== undefined && metrics.failed_files.length > 0) {
          formatted.push({ label: 'Failed Files', value: metrics.failed_files.length.toString(), icon: '⚠️' })
        }
        break
      
      case 'fingerprint':
        if (metrics.entries_processed !== undefined) {
          formatted.push({ label: 'Entries Processed', value: metrics.entries_processed.toLocaleString(), icon: '🔍' })
        }
        break
      
      case 'validation':
        if (metrics.entries_processed !== undefined) {
          formatted.push({ label: 'Entries Validated', value: metrics.entries_processed.toLocaleString(), icon: '✅' })
        }
        if (metrics.violations_count !== undefined) {
          formatted.push({ label: 'Violations Found', value: metrics.violations_count.toString(), icon: '⚠️' })
        }
        break
      
      case 'policy':
        if (metrics.entries_processed !== undefined) {
          formatted.push({ label: 'Entries Evaluated', value: metrics.entries_processed.toLocaleString(), icon: '🛡️' })
        }
        if (metrics.policy_violations !== undefined) {
          formatted.push({ label: 'Policy Violations', value: metrics.policy_violations.toString(), icon: '⚠️' })
        }
        break
      
      case 'reporting':
        if (metrics.entries_processed !== undefined) {
          formatted.push({ label: 'Entries Processed', value: metrics.entries_processed.toLocaleString(), icon: '📄' })
        }
        if (metrics.pdf_size_bytes !== undefined) {
          formatted.push({ label: 'Report Size', value: formatFileSize(metrics.pdf_size_bytes), icon: '📊' })
        }
        if (metrics.threshold !== undefined) {
          formatted.push({ label: 'Threshold', value: metrics.threshold.toString(), icon: '📈' })
        }
        break
      
      case 'indexing':
        if (metrics.chunks_indexed !== undefined) {
          formatted.push({ label: 'Chunks Indexed', value: metrics.chunks_indexed.toLocaleString(), icon: '🔍' })
        }
        if (metrics.collection_name !== undefined) {
          formatted.push({ label: 'Collection', value: metrics.collection_name, icon: '🗂️' })
        }
        if (metrics.vectors_created !== undefined) {
          formatted.push({ label: 'Vectors Created', value: metrics.vectors_created.toLocaleString(), icon: '🔢' })
        }
        break
    }
    
    return formatted
  }

  const stageMetrics = logs?.stage_metrics || initialMetrics?.aird_stages || {}
  
  // Check if pipeline was cancelled
  // cancelled_reason is stored in run.metrics.cancelled_reason
  // It can come from:
  // 1. logs.metrics.cancelled_reason (from getPipelineRunLogs API)
  // 2. initialMetrics.cancelled_reason (from selectedRunForDetails.metrics passed as prop)
  // Note: Both should be the metrics dictionary with cancelled_reason as a direct property
  const cancelledReason = logs?.metrics?.cancelled_reason || 
                         (initialMetrics && typeof initialMetrics === 'object' && 'cancelled_reason' in initialMetrics ? initialMetrics.cancelled_reason : null)
  
  // Only check for 'failed' status (cancellation sets status to 'failed')
  const isCancelled = runStatus === 'failed' && !!cancelledReason

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
        <div className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onClick={onClose} />

        <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
          {/* Header */}
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-white">Pipeline Run Details</h3>
              <p className="text-sm text-blue-100 mt-1">Version {runVersion} • {runStatus}</p>
            </div>
            <button
              onClick={onClose}
              className="text-white hover:text-gray-200 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4 max-h-[70vh] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
              </div>
            ) : (
              <div className="space-y-4">
                {/* Cancellation Notice */}
                {isCancelled && (
                  <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
                    <div className="flex items-start">
                      <AlertTriangle className="h-5 w-5 text-orange-600 mr-3 mt-0.5 flex-shrink-0" />
                      <div>
                        <h4 className="text-sm font-semibold text-orange-900">Pipeline Cancelled</h4>
                        <p className="text-sm text-orange-800 mt-1">
                          {cancelledReason}
                        </p>
                        <p className="text-xs text-orange-700 mt-2">
                          Note: Stages that completed successfully before cancellation will show as "succeeded", 
                          but the pipeline overall status is "failed" because it was manually cancelled.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Stage Status Overview */}
                {Object.keys(stageMetrics).length > 0 && (
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-3">Pipeline Stages</h4>
                    <div className="space-y-2">
                      {sortTasksByOrder(Object.entries(stageMetrics)).map(([stageName, stageData]: [string, any]) => (
                        <div
                          key={stageName}
                          className="border border-gray-200 rounded-lg overflow-hidden"
                        >
                          <button
                            onClick={() => toggleStage(stageName)}
                            className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                          >
                            <div className="flex items-center space-x-3">
                              {getStageStatusIcon(stageData?.status)}
                              <span className="font-medium text-gray-900 capitalize">
                                {stageName.replace(/_/g, ' ')}
                              </span>
                              {stageData?.status && (
                                <span className={`text-xs px-2 py-0.5 rounded ${getStatusColor(stageData.status)}`}>
                                  {stageData.status}
                                </span>
                              )}
                              {stageData?.error && (
                                <span className="text-xs text-red-600">(Error)</span>
                              )}
                            </div>
                            {expandedStages.has(stageName) ? (
                              <ChevronUp className="h-4 w-4 text-gray-500" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-gray-500" />
                            )}
                          </button>

                          {expandedStages.has(stageName) && (
                            <div className="px-4 py-3 bg-white border-t border-gray-200 space-y-3">
                              {stageData?.error && (
                                <div className="p-3 bg-red-50 border border-red-200 rounded">
                                  <p className="text-sm font-medium text-red-800">Error:</p>
                                  <p className="text-sm text-red-700 mt-1">{stageData.error}</p>
                                </div>
                              )}
                              {stageData?.status === 'skipped' && stageData?.metrics?.reason && (
                                <div className="p-3 bg-yellow-50 border border-yellow-200 rounded">
                                  <p className="text-sm font-medium text-yellow-800">Skipped:</p>
                                  <p className="text-sm text-yellow-700 mt-1">{formatSkipReason(stageData.metrics.reason)}</p>
                                </div>
                              )}
                              
                              {/* Human-readable metrics */}
                              {stageData?.metrics && Object.keys(stageData.metrics).length > 0 && (
                                <div>
                                  <p className="text-sm font-medium text-gray-900 mb-2">Metrics</p>
                                  {(() => {
                                    const formattedMetrics = formatStageMetrics(stageName, stageData.metrics)
                                    if (formattedMetrics.length > 0) {
                                      return (
                                        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3">
                                          {formattedMetrics.map((metric, idx) => (
                                            <div key={idx} className="flex items-center gap-2 p-2 bg-gray-50 rounded border border-gray-200">
                                              {metric.icon && <span className="text-base">{metric.icon}</span>}
                                              <div className="flex-1 min-w-0">
                                                <p className="text-xs text-gray-500 truncate">{metric.label}</p>
                                                <p className="text-sm font-semibold text-gray-900">{metric.value}</p>
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      )
                                    }
                                    return null
                                  })()}
                                  
                                  {/* Duration */}
                                  {stageData?.started_at && stageData?.finished_at && (() => {
                                    const duration = formatDuration(stageData.started_at, stageData.finished_at)
                                    if (duration) {
                                      return (
                                        <div className="flex items-center gap-2 p-2 bg-gray-50 rounded border border-gray-200 mb-3">
                                          <span className="text-base">⏱️</span>
                                          <div>
                                            <p className="text-xs text-gray-500">Duration</p>
                                            <p className="text-sm font-semibold text-gray-900">{duration}</p>
                                          </div>
                                        </div>
                                      )
                                    }
                                    return null
                                  })()}
                                  
                                  {/* Timestamps */}
                                  <div className="flex flex-wrap gap-4 text-xs text-gray-500">
                                    {stageData?.started_at && (
                                      <div>
                                        <span className="font-medium">Started:</span>{' '}
                                        {new Date(stageData.started_at).toLocaleString()}
                                      </div>
                                    )}
                                    {stageData?.finished_at && (
                                      <div>
                                        <span className="font-medium">Finished:</span>{' '}
                                        {new Date(stageData.finished_at).toLocaleString()}
                                      </div>
                                    )}
                                  </div>
                                  
                                  {/* Raw JSON (collapsible) */}
                                  <details className="mt-3">
                                    <summary className="text-xs font-medium text-gray-600 cursor-pointer hover:text-gray-800">
                                      View Raw Metrics (JSON)
                                    </summary>
                                    <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto mt-2 border border-gray-200">
                                      {JSON.stringify(stageData.metrics, null, 2)}
                                    </pre>
                                  </details>
                                </div>
                              )}
                              
                              {/* Show timestamps even if no metrics */}
                              {(!stageData?.metrics || Object.keys(stageData.metrics).length === 0) && (
                                <div className="flex flex-wrap gap-4 text-xs text-gray-500">
                                  {stageData?.started_at && (
                                    <div>
                                      <span className="font-medium">Started:</span>{' '}
                                      {new Date(stageData.started_at).toLocaleString()}
                                    </div>
                                  )}
                                  {stageData?.finished_at && (
                                    <div>
                                      <span className="font-medium">Finished:</span>{' '}
                                      {new Date(stageData.finished_at).toLocaleString()}
                                    </div>
                                  )}
                                </div>
                              )}
                              
                              {/* Task Logs for this stage */}
                              {logs?.logs && (() => {
                                const stageTasks = Object.entries(logs.logs)
                                  .filter(([taskId]) => getStageFromTaskId(taskId) === stageName)
                                  .map(([taskId, taskLog]): { taskId: string } & TaskLog => ({ 
                                    taskId, 
                                    ...(taskLog && typeof taskLog === 'object' ? taskLog as TaskLog : {} as TaskLog) 
                                  }))
                                
                                if (stageTasks.length === 0) return null
                                
                                return (
                                  <div className="mt-4 pt-4 border-t border-gray-200">
                                    <p className="text-sm font-medium text-gray-900 mb-2 flex items-center gap-2">
                                      <FileText className="h-4 w-4 text-gray-500" />
                                      Task Logs
                                    </p>
                                    <div className="space-y-2">
                                      {stageTasks.map(({ taskId, content, status, error }) => (
                                        <div key={taskId} className="border border-gray-200 rounded-lg overflow-hidden">
                                          <button
                                            onClick={() => toggleTask(taskId)}
                                            className="w-full px-3 py-2 bg-gray-50 hover:bg-gray-100 border-b border-gray-200 flex items-center justify-between transition-colors"
                                          >
                                            <div className="flex items-center space-x-2">
                                              <FileText className="h-3 w-3 text-gray-500" />
                                              <span className="text-xs font-medium text-gray-700">{taskId}</span>
                                              {status && (
                                                <span className={`text-xs px-1.5 py-0.5 rounded ${getStatusColor(status)}`}>
                                                  {status}
                                                </span>
                                              )}
                                            </div>
                                            {expandedTasks.has(taskId) ? (
                                              <ChevronUp className="h-3 w-3 text-gray-500" />
                                            ) : (
                                              <ChevronDown className="h-3 w-3 text-gray-500" />
                                            )}
                                          </button>
                                          {expandedTasks.has(taskId) && (
                                            <div className="px-3 py-2 bg-gray-900 text-gray-100">
                                              {content ? (
                                                <pre className="text-xs font-mono whitespace-pre-wrap overflow-x-auto">
                                                  {content}
                                                </pre>
                                              ) : error ? (
                                                <p className="text-xs text-red-400">{error}</p>
                                              ) : (
                                                <p className="text-xs text-gray-400">No logs available</p>
                                              )}
                                            </div>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )
                              })()}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Unmapped Task Logs (fallback for tasks that don't map to any stage) */}
                {logs?.logs && (() => {
                  const unmappedTasks = Object.entries(logs.logs)
                    .filter(([taskId]) => !getStageFromTaskId(taskId))
                  
                  if (unmappedTasks.length === 0) return null
                  
                  return (
                    <div>
                      <h4 className="text-sm font-semibold text-gray-900 mb-3">Additional Task Logs</h4>
                      <div className="space-y-2">
                        {sortTasksByOrder(unmappedTasks).map(([taskId, taskLog]: [string, any]) => (
                          <div
                            key={taskId}
                            className="border border-gray-200 rounded-lg overflow-hidden"
                          >
                            <button
                              onClick={() => toggleTask(taskId)}
                              className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                            >
                              <div className="flex items-center space-x-2">
                                <FileText className="h-4 w-4 text-gray-500" />
                                <span className="font-medium text-gray-900">{taskId}</span>
                                {taskLog.status && (
                                  <span className={`text-xs px-2 py-0.5 rounded ${getStatusColor(taskLog.status)}`}>
                                    {taskLog.status}
                                  </span>
                                )}
                              </div>
                              {expandedTasks.has(taskId) ? (
                                <ChevronUp className="h-4 w-4 text-gray-500" />
                              ) : (
                                <ChevronDown className="h-4 w-4 text-gray-500" />
                              )}
                            </button>

                            {expandedTasks.has(taskId) && (
                              <div className="px-4 py-3 bg-gray-900 text-gray-100 border-t border-gray-200">
                                {taskLog.content ? (
                                  <pre className="text-xs font-mono whitespace-pre-wrap overflow-x-auto">
                                    {taskLog.content}
                                  </pre>
                                ) : taskLog.error ? (
                                  <p className="text-xs text-red-400">{taskLog.error}</p>
                                ) : (
                                  <p className="text-xs text-gray-400">No logs available</p>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })()}

                {logs?.error && (
                  <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <p className="text-sm text-yellow-800">{logs.error}</p>
                  </div>
                )}

                {Object.keys(stageMetrics).length === 0 && (!logs?.logs || Object.keys(logs.logs).length === 0) && (
                  <div className="text-center py-8 text-gray-500">
                    <p>No stage information or logs available for this pipeline run.</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="bg-gray-50 px-6 py-3 flex justify-end items-center">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
