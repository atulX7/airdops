'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Lightbulb, CheckCircle2, XCircle, AlertTriangle, Loader2, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfirmModal, ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'

interface Product {
  id: string
  name: string
  chunking_config?: any
  embedding_config?: any
}

interface Recommendation {
  type: string
  message: string
  action: string
  config: Record<string, any>
  expected_impact: string
  priority: 'high' | 'medium' | 'low'
}

interface RecommendationsResponse {
  recommendations: Recommendation[]
  primary_recommendation?: Recommendation
}

export default function RecommendationsPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  const { addToast } = useToast()

  const [product, setProduct] = useState<Product | null>(null)
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState<string | null>(null)
  const [showApplyModal, setShowApplyModal] = useState(false)
  const [selectedRecommendation, setSelectedRecommendation] = useState<Recommendation | null>(null)

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
      const productResponse = await apiClient.getProduct(productId)
      if (!productResponse.error && productResponse.data) {
        setProduct(productResponse.data as Product)
      }

      // Get latest evaluation run to generate recommendations
      const runsResponse = await apiClient.listEvaluationRuns(productId, 1, 0)
      if (!runsResponse.error && runsResponse.data) {
        // Handle both old format (array) and new format (object with runs, total, etc.)
        const runsData = Array.isArray(runsResponse.data) 
          ? runsResponse.data 
          : (runsResponse.data as any)?.runs || []
        if (runsData.length > 0) {
          const latestRun = runsData[0]
          if (latestRun.status === 'completed' && latestRun.metrics) {
            // Generate recommendations based on latest evaluation
            const recResponse = await apiClient.getRAGRecommendations(productId)
            if (!recResponse.error && recResponse.data) {
              const recData = recResponse.data as RecommendationsResponse
              setRecommendations(recData.recommendations || [])
            }
          }
        }
      }
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async () => {
    if (!selectedRecommendation) return

    setApplying(selectedRecommendation.type)
    try {
      const response = await apiClient.applyRAGRecommendation(
        productId,
        selectedRecommendation.type,
        selectedRecommendation.config
      )

      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Apply Failed',
          message: response.error
        })
      } else {
        setResultModalData({
          type: 'success',
          title: 'Recommendation Applied',
          message: 'The recommendation has been applied. A pipeline re-run will be triggered to apply the changes.'
        })
        loadData()
      }
      setShowResultModal(true)
      setShowApplyModal(false)
      setSelectedRecommendation(null)
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Apply Failed',
        message: 'An unexpected error occurred'
      })
      setShowResultModal(true)
    } finally {
      setApplying(null)
    }
  }

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high':
        return 'bg-red-100 text-red-800'
      case 'medium':
        return 'bg-yellow-100 text-yellow-800'
      case 'low':
        return 'bg-blue-100 text-blue-800'
      default:
        return 'bg-gray-100 text-gray-800'
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
      <div className="p-6">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href={`/app/products/${productId}/rag-quality`} className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Retrieval Evaluation
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Recommendations</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Improvement Recommendations</h1>
          <p className="text-gray-600 mt-1">
            View and apply recommendations to improve your retrieval system performance based on evaluation results.
          </p>
        </div>

        {/* Recommendations List */}
        {recommendations.length > 0 ? (
          <div className="space-y-4">
            {recommendations.map((rec, index) => (
              <div key={index} className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center mb-3">
                      <Lightbulb className="h-5 w-5 text-yellow-600 mr-2" />
                      <h3 className="text-lg font-semibold text-gray-900">{rec.message}</h3>
                      <span className={`ml-3 px-2 py-1 text-xs font-medium rounded ${getPriorityColor(rec.priority)}`}>
                        {rec.priority.toUpperCase()} PRIORITY
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mb-3">{rec.expected_impact}</p>
                    {rec.config && Object.keys(rec.config).length > 0 && (
                      <div className="bg-gray-50 rounded-lg p-3 mb-3">
                        <p className="text-xs font-medium text-gray-700 mb-2">Configuration Changes:</p>
                        <ul className="text-xs text-gray-600 space-y-1">
                          {Object.entries(rec.config).map(([key, value]) => (
                            <li key={key}>
                              <span className="font-medium">{key}:</span> {String(value)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                  <Button
                    onClick={() => {
                      setSelectedRecommendation(rec)
                      setShowApplyModal(true)
                    }}
                    disabled={applying === rec.type}
                    className="bg-blue-600 hover:bg-blue-700 text-white ml-4"
                  >
                    {applying === rec.type ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Applying...
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4 mr-2" />
                        Apply
                      </>
                    )}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <Lightbulb className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No recommendations available</h3>
            <p className="text-gray-600 mb-6">
              Run an evaluation first to get recommendations based on your retrieval system's performance.
            </p>
            <Link href={`/app/products/${productId}/rag-quality/evaluations`}>
              <Button className="bg-blue-600 hover:bg-blue-700 text-white">
                Run Evaluation
              </Button>
            </Link>
          </div>
        )}

        {showApplyModal && selectedRecommendation && (
          <ConfirmModal
            isOpen={showApplyModal}
            title="Apply Recommendation"
            message={`Are you sure you want to apply this recommendation? This will update your product configuration and trigger a pipeline re-run.`}
            onConfirm={handleApply}
            onClose={() => {
              setShowApplyModal(false)
              setSelectedRecommendation(null)
            }}
            confirmText="Apply"
            cancelText="Cancel"
          />
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

