'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Plus, FileText, Edit, Trash2, CheckCircle2, XCircle, AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfirmModal, ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/ui/status-badge'

interface Product {
  id: string
  name: string
  current_version: number
}

interface EvaluationDataset {
  id: string
  name: string
  description?: string
  dataset_type: 'golden_qa' | 'golden_retrieval' | 'adversarial'
  status: 'draft' | 'active' | 'archived'
  version?: number
  metadata?: Record<string, any>
  created_at: string
  updated_at?: string
}

export default function DatasetsPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string

  const [product, setProduct] = useState<Product | null>(null)
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteDatasetId, setDeleteDatasetId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

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
      if (productResponse.error) {
        setError(productResponse.error)
        return
      }
      setProduct(productResponse.data as Product)

      const datasetsResponse = await apiClient.listEvaluationDatasets(productId)
      if (!datasetsResponse.error && datasetsResponse.data) {
        setDatasets(datasetsResponse.data as EvaluationDataset[])
      }
    } catch (err) {
      setError('Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteDatasetId) return

    setDeleting(true)
    try {
      const response = await apiClient.deleteEvaluationDataset(deleteDatasetId)
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Delete Failed',
          message: response.error
        })
      } else {
        setResultModalData({
          type: 'success',
          title: 'Dataset Deleted',
          message: 'Dataset has been successfully deleted'
        })
        loadData()
      }
      setShowResultModal(true)
      setShowDeleteModal(false)
      setDeleteDatasetId(null)
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Delete Failed',
        message: 'An unexpected error occurred'
      })
      setShowResultModal(true)
    } finally {
      setDeleting(false)
    }
  }

  const getDatasetTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      golden_qa: 'Golden Q/A',
      golden_retrieval: 'Golden Retrieval',
      adversarial: 'Adversarial'
    }
    return labels[type] || type
  }

  const getDatasetTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      golden_qa: 'bg-blue-100 text-blue-800',
      golden_retrieval: 'bg-green-100 text-green-800',
      adversarial: 'bg-red-100 text-red-800'
    }
    return colors[type] || 'bg-gray-100 text-gray-800'
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
          <span className="text-sm font-medium text-gray-900">Datasets</span>
        </div>

        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Evaluation Datasets</h1>
            <p className="text-gray-600 mt-1">
              Manage golden Q/A sets, retrieval test cases, and adversarial examples for RAG evaluation.
            </p>
          </div>
          <Link href={`/app/products/${productId}/rag-quality/datasets/new`}>
            <Button className="bg-blue-600 hover:bg-blue-700 text-white">
              <Plus className="h-4 w-4 mr-2" />
              Create Dataset
            </Button>
          </Link>
        </div>

        {/* Datasets List */}
        {datasets.length > 0 ? (
          <div className="grid grid-cols-1 gap-4">
            {datasets.map((dataset) => (
              <div key={dataset.id} className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center mb-2">
                      <h3 className="text-lg font-semibold text-gray-900 mr-3">{dataset.name}</h3>
                      <span className={`px-2 py-1 text-xs font-medium rounded ${getDatasetTypeColor(dataset.dataset_type)}`}>
                        {getDatasetTypeLabel(dataset.dataset_type)}
                      </span>
                      <StatusBadge status={dataset.status as any} className="ml-2" />
                    </div>
                    {dataset.description && (
                      <p className="text-sm text-gray-600 mb-3">{dataset.description}</p>
                    )}
                    <div className="flex items-center text-sm text-gray-500">
                      <span>Version: {dataset.version || 'All'}</span>
                      <span className="mx-2">•</span>
                      <span>Created: {new Date(dataset.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Link href={`/app/products/${productId}/rag-quality/datasets/${dataset.id}`}>
                      <Button variant="outline" size="sm">
                        <FileText className="h-4 w-4 mr-2" />
                        View Items
                      </Button>
                    </Link>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        setDeleteDatasetId(dataset.id)
                        setShowDeleteModal(true)
                      }}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No datasets yet</h3>
            <p className="text-gray-600 mb-6">Create your first evaluation dataset to start assessing retrieval system performance.</p>
            <Link href={`/app/products/${productId}/rag-quality/datasets/new`}>
              <Button className="bg-blue-600 hover:bg-blue-700 text-white">
                <Plus className="h-4 w-4 mr-2" />
                Create Dataset
              </Button>
            </Link>
          </div>
        )}

        <ConfirmModal
          isOpen={showDeleteModal}
          title="Delete Dataset"
          message="Are you sure you want to delete this dataset? This action cannot be undone."
          onConfirm={handleDelete}
          onClose={() => {
            setShowDeleteModal(false)
            setDeleteDatasetId(null)
          }}
          confirmText="Delete"
          cancelText="Cancel"
          variant="danger"
        />

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

