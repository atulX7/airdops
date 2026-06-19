'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, CheckCircle2, XCircle, AlertTriangle, TrendingUp, BarChart3, Settings, FileText, Lightbulb, Play, Loader2, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/ui/status-badge'
import type { QualityGatesPayload } from '@/lib/rag-quality-gates'

interface Product {
  id: string
  name: string
  current_version: number
  promoted_version?: number
  vector_creation_enabled?: boolean
  rag_quality_thresholds?: Record<string, number>
}

interface EvaluationDataset {
  id: string
  name: string
  description?: string
  dataset_type: string
  status: string
  created_at: string
}

interface EvaluationRun {
  id: string
  product_id: string
  version: number
  status: string
  metrics?: {
    aggregate?: Record<string, any>
  }
  started_at?: string
  finished_at?: string
  created_at: string
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

export default function RAGQualityPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string

  const [product, setProduct] = useState<Product | null>(null)
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([])
  const [runs, setRuns] = useState<EvaluationRun[]>([])
  const [totalRuns, setTotalRuns] = useState(0)
  const [qualityGates, setQualityGates] = useState<QualityGatesPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingGates, setLoadingGates] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [showResultModal, setShowResultModal] = useState(false)
  const [resultModalData, setResultModalData] = useState<{
    type: 'success' | 'error' | 'warning' | 'info'
    title: string
    message: string
  } | null>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/')
      return
    }

    if (status === 'authenticated' && productId) {
      loadData()
    }
  }, [status, router, productId])

  const loadData = async () => {
    setLoading(true)
    try {
      // Load product
      const productResponse = await apiClient.getProduct(productId)
      if (productResponse.error) {
        setError(productResponse.error)
        return
      }
      setProduct(productResponse.data as Product)

      // Load datasets
      const datasetsResponse = await apiClient.listEvaluationDatasets(productId)
      if (!datasetsResponse.error && datasetsResponse.data) {
        setDatasets(datasetsResponse.data as EvaluationDataset[])
      }

      // Load recent runs - backend returns total count in paginated response
      const runsResponse = await apiClient.listEvaluationRuns(productId, 5, 0)
      if (!runsResponse.error && runsResponse.data) {
        // Handle both old format (array) and new format (object with runs, total, etc.)
        if (Array.isArray(runsResponse.data)) {
          // Old format fallback
          setRuns(runsResponse.data.slice(0, 5))
          setTotalRuns(runsResponse.data.length)
        } else {
          // New paginated format - extract both runs and total
          const responseData = runsResponse.data as any
          setRuns(responseData.runs || [])
          setTotalRuns(responseData.total || 0) // Extract total from response
        }
      }

      // Load quality gates
      await loadQualityGates()
    } catch (err) {
      setError('Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const loadQualityGates = async () => {
    setLoadingGates(true)
    try {
      const response = await apiClient.getRAGQualityGates(productId)
      if (!response.error && response.data) {
        setQualityGates(response.data as QualityGatesPayload)
      }
    } catch (err) {
      console.error('Failed to load quality gates:', err)
    } finally {
      setLoadingGates(false)
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6">
          <CardSkeleton />
        </div>
      </AppLayout>
    )
  }

  if (error || !product) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800">{error || 'Product not found'}</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  // Check if vector creation is disabled
  if (product.vector_creation_enabled === false) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center max-w-md">
            <AlertTriangle className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Vector Creation Disabled</h2>
            <p className="text-gray-600 mb-6">
              Retrieval Evaluation requires vector creation to be enabled for this product. 
              Please enable vector creation in the product settings to use this feature.
            </p>
            <div className="flex gap-4 justify-center">
              <Link href={`/app/products/${productId}`}>
                <Button variant="outline">Back to Product</Button>
              </Link>
              <Link href={`/app/products/${productId}/edit`}>
                <Button>Enable Vector Creation</Button>
              </Link>
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }

  const latestRun = runs[0]
  const aggregateMetrics = latestRun?.metrics?.aggregate || {}

  return (
    <AppLayout>
      <div className="p-6">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href={`/app/products/${productId}`} className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            {product.name}
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Retrieval Evaluation</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Retrieval Evaluation</h1>
          <p className="text-gray-600 mt-1">
            Evaluate and monitor retrieval system performance with comprehensive metrics and quality gates. 
            Quality gates must pass before promoting versions to production.
          </p>
        </div>

        {/* Quality Gates Status */}
        {qualityGates && (
          <div className="mb-6">
            {!qualityGates.evaluated ? (
              // Show info message when no evaluation has been run
              <div className="rounded-lg border p-6 bg-blue-50 border-blue-200">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <div className="flex items-center min-w-0">
                    <AlertTriangle className="h-6 w-6 text-blue-600 mr-3 shrink-0" />
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">
                        Quality Gates: Not Evaluated
                      </h3>
                      <p className="text-sm text-gray-600 mt-1">
                        {qualityGates.message ||
                          (datasets.length > 0
                            ? 'No evaluation run found. Run an evaluation to check quality gates.'
                            : 'No evaluation run found. Create a dataset and run an evaluation to check quality gates.')}
                      </p>
                    </div>
                  </div>
                  {datasets.length > 0 ? (
                    <Link href={`/app/products/${productId}/rag-quality/evaluations`}>
                      <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white shrink-0">
                        <Play className="h-4 w-4 mr-2" />
                        Go to evaluations
                      </Button>
                    </Link>
                  ) : (
                    <Link href={`/app/products/${productId}/rag-quality/datasets`}>
                      <Button size="sm" className="bg-blue-600 hover:bg-blue-700 text-white shrink-0">
                        <Play className="h-4 w-4 mr-2" />
                        Create dataset
                      </Button>
                    </Link>
                  )}
                </div>
              </div>
            ) : (
              // Summary only; per-gate breakdown lives on Evaluation runs
              <div
                className={`rounded-lg border p-6 ${qualityGates.all_passed ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-start sm:items-center">
                    {qualityGates.all_passed ? (
                      <CheckCircle2 className="h-6 w-6 text-green-600 mr-3 shrink-0 mt-0.5 sm:mt-0" />
                    ) : (
                      <XCircle className="h-6 w-6 text-red-600 mr-3 shrink-0 mt-0.5 sm:mt-0" />
                    )}
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">
                        Quality Gates: {qualityGates.all_passed ? 'Passed' : 'Failed'}
                      </h3>
                      <p className="text-sm text-gray-600 mt-1">
                        {qualityGates.blocking
                          ? 'Blocking promotion to production — quality gates must pass before promotion (or use force override on promote where allowed).'
                          : 'Ready for production — all quality gates passed.'}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 sm:items-end shrink-0">
                    <Link href={`/app/products/${productId}/rag-quality/settings`}>
                      <Button variant="outline" size="sm" className="w-full sm:w-auto">
                        <Settings className="h-4 w-4 mr-2" />
                        Configure Thresholds
                      </Button>
                    </Link>
                    {!qualityGates.all_passed && (
                      <Link href={`/app/products/${productId}/rag-quality/evaluations`}>
                        <Button variant="outline" size="sm" className="w-full sm:w-auto">
                          <BarChart3 className="h-4 w-4 mr-2" />
                          View evaluation runs
                        </Button>
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Datasets</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{datasets.length}</p>
              </div>
              <FileText className="h-8 w-8 text-blue-600" />
            </div>
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Evaluation Runs</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{totalRuns}</p>
              </div>
              <BarChart3 className="h-8 w-8 text-purple-600" />
            </div>
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Groundedness</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {aggregateMetrics.groundedness?.mean ? (aggregateMetrics.groundedness.mean * 100).toFixed(1) : '—'}%
                </p>
              </div>
              <TrendingUp className="h-8 w-8 text-green-600" />
            </div>
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-500">Citation Coverage</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {aggregateMetrics.citation_coverage?.mean ? (aggregateMetrics.citation_coverage.mean * 100).toFixed(1) : '—'}%
                </p>
              </div>
              <CheckCircle2 className="h-8 w-8 text-indigo-600" />
            </div>
          </div>
        </div>

        {/* Navigation Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <Link href={`/app/products/${productId}/rag-quality/datasets`}>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:bg-gray-50 cursor-pointer transition-colors">
              <FileText className="h-8 w-8 text-blue-600 mb-3" />
              <h3 className="font-medium text-gray-900 mb-1">Evaluation Datasets</h3>
              <p className="text-sm text-gray-600">Manage golden Q/A sets and test cases</p>
            </div>
          </Link>
          <Link href={`/app/products/${productId}/rag-quality/evaluations`}>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:bg-gray-50 cursor-pointer transition-colors">
              <BarChart3 className="h-8 w-8 text-purple-600 mb-3" />
              <h3 className="font-medium text-gray-900 mb-1">Evaluation Runs</h3>
              <p className="text-sm text-gray-600">View and manage evaluation results</p>
            </div>
          </Link>
          <Link href={`/app/products/${productId}/rag-quality/settings`}>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:bg-gray-50 cursor-pointer transition-colors">
              <Settings className="h-8 w-8 text-gray-600 mb-3" />
              <h3 className="font-medium text-gray-900 mb-1">Quality Thresholds</h3>
              <p className="text-sm text-gray-600">Configure quality gate thresholds</p>
            </div>
          </Link>
          <Link href={`/app/products/${productId}/rag-quality/recommendations`}>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:bg-gray-50 cursor-pointer transition-colors">
              <Lightbulb className="h-8 w-8 text-yellow-600 mb-3" />
              <h3 className="font-medium text-gray-900 mb-1">Recommendations</h3>
              <p className="text-sm text-gray-600">View and apply improvement suggestions</p>
            </div>
          </Link>
        </div>

        {/* Recent Evaluation Runs */}
        {runs.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Recent Evaluation Runs</h2>
              <Link href={`/app/products/${productId}/rag-quality/evaluations`}>
                <Button variant="outline" size="sm">View All</Button>
              </Link>
            </div>
            <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gradient-to-r from-gray-50 to-blue-50">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Version
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Started
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Duration
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {runs.map((run) => {
                    // Calculate duration - check status first, then finished_at
                    const duration = (run.status === 'completed' || run.status === 'failed') && run.started_at && run.finished_at
                      ? `${Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s`
                      : (run.status === 'completed' || run.status === 'failed') && run.started_at
                      ? '-' // Completed but no finished_at (shouldn't happen, but handle gracefully)
                      : run.started_at
                      ? 'Running...'
                      : '-'
                    
                    return (
                      <tr key={run.id} className="hover:bg-blue-50/50 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className="text-sm font-semibold text-gray-900">v{run.version}</span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <StatusBadge status={mapEvaluationStatus(run.status)} size="sm" />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                          {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                          {duration}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
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
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Empty State */}
        {runs.length === 0 && datasets.length === 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <BarChart3 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No evaluations yet</h3>
            <p className="text-gray-600 mb-6">Get started by creating an evaluation dataset and running your first evaluation.</p>
            <Link href={`/app/products/${productId}/rag-quality/datasets`}>
              <Button className="bg-blue-600 hover:bg-blue-700 text-white">
                <FileText className="h-4 w-4 mr-2" />
                Create Dataset
              </Button>
            </Link>
          </div>
        )}

        {showResultModal && resultModalData && (
          <ResultModal
            isOpen={showResultModal}
            type={resultModalData.type}
            title={resultModalData.title}
            message={resultModalData.message}
            onClose={() => setShowResultModal(false)}
          />
        )}
      </div>
    </AppLayout>
  )
}



