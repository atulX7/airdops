'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Plus, Upload, FileText, Trash2, Loader2, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfirmModal } from '@/components/ui/modal'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'
import { DEFAULT_ITEMS_PER_PAGE } from '@/lib/constants'

interface DatasetItem {
  id: string
  query: string
  expected_answer?: string
  expected_chunks?: string[]
  expected_docs?: string[]
  question_type?: string
  metadata?: Record<string, any>
}

interface EvaluationDataset {
  id: string
  name: string
  description?: string
  dataset_type: string
  status: string
}

export default function DatasetDetailPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  const datasetId = params.datasetId as string
  const { addToast } = useToast()

  const [dataset, setDataset] = useState<EvaluationDataset | null>(null)
  const [items, setItems] = useState<DatasetItem[]>([])
  const [currentPage, setCurrentPage] = useState(0)
  const [totalItems, setTotalItems] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showBulkImportModal, setShowBulkImportModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteItemId, setDeleteItemId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (status === 'authenticated' && datasetId) {
      loadData(0, true)
    }
  }, [status, datasetId])

  const loadData = async (page: number = 0, showLoading = true) => {
    if (showLoading) setLoading(true)
    try {
      const datasetResponse = await apiClient.getEvaluationDataset(datasetId)
      if (!datasetResponse.error && datasetResponse.data) {
        setDataset(datasetResponse.data as EvaluationDataset)
      }

      const offset = page * DEFAULT_ITEMS_PER_PAGE
      const itemsResponse = await apiClient.listDatasetItems(datasetId, DEFAULT_ITEMS_PER_PAGE, offset)
      if (!itemsResponse.error && itemsResponse.data) {
        // Handle both old format (array) and new format (object with items, total, etc.)
        if (Array.isArray(itemsResponse.data)) {
          setItems(itemsResponse.data as DatasetItem[])
          setTotalItems(itemsResponse.data.length)
        } else {
          setItems(itemsResponse.data.items || [])
          setTotalItems(itemsResponse.data.total || 0)
        }
        setCurrentPage(page)
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to load dataset'
      })
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteItemId) return

    setDeleting(true)
    try {
      const response = await apiClient.deleteDatasetItem(datasetId, deleteItemId)
      if (response.error) {
        addToast({
          type: 'error',
          message: response.error
        })
      } else {
        addToast({
          type: 'success',
          message: 'Item deleted successfully'
        })
        // Reload current page after deletion
        loadData(currentPage, false)
      }
      setShowDeleteModal(false)
      setDeleteItemId(null)
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to delete item'
      })
    } finally {
      setDeleting(false)
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

  if (!dataset) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800">Dataset not found</p>
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
          <Link href={`/app/products/${productId}/rag-quality/datasets`} className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Datasets
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">{dataset.name}</span>
        </div>

        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{dataset.name}</h1>
            {dataset.description && (
              <p className="text-gray-600 mt-1">{dataset.description}</p>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowAddModal(true)}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Items
            </Button>
            <Button
              variant="outline"
              onClick={() => setShowBulkImportModal(true)}
            >
              <Upload className="h-4 w-4 mr-2" />
              Bulk Import
            </Button>
          </div>
        </div>

        {/* Items List */}
        {items.length > 0 ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Dataset Items ({totalItems})
              </h2>
            </div>
            <div className="divide-y divide-gray-200">
              {items.map((item, index) => (
                <div key={item.id} className="p-4 hover:bg-gray-50">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center mb-2">
                        <span className="text-sm font-medium text-gray-500 mr-2">
                          #{currentPage * DEFAULT_ITEMS_PER_PAGE + index + 1}
                        </span>
                        {item.question_type && (
                          <span className="px-2 py-1 text-xs font-medium rounded bg-gray-100 text-gray-800">
                            {item.question_type}
                          </span>
                        )}
                      </div>
                      <p className="text-sm font-medium text-gray-900 mb-2">{item.query}</p>
                      {item.expected_answer && (
                        <p className="text-sm text-gray-600 mb-2">
                          <span className="font-medium">Expected Answer:</span> {item.expected_answer.substring(0, 200)}
                          {item.expected_answer.length > 200 && '...'}
                        </p>
                      )}
                      {item.expected_chunks && item.expected_chunks.length > 0 && (
                        <p className="text-xs text-gray-500">
                          Expected Chunks: {item.expected_chunks.length}
                        </p>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        setDeleteItemId(item.id)
                        setShowDeleteModal(true)
                      }}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50 ml-4"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
            {/* Pagination Controls */}
            {totalItems > DEFAULT_ITEMS_PER_PAGE && (
              <div className="mt-4 flex items-center justify-between border-t border-gray-200 px-6 py-4 bg-white">
                <div className="text-sm text-gray-700">
                  Showing {currentPage * DEFAULT_ITEMS_PER_PAGE + 1} to{' '}
                  {Math.min((currentPage + 1) * DEFAULT_ITEMS_PER_PAGE, totalItems)} of{' '}
                  {totalItems} items
                </div>
                <div className="flex space-x-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => loadData(currentPage - 1)}
                    disabled={currentPage === 0 || loading}
                    className="px-3 py-1.5"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => loadData(currentPage + 1)}
                    disabled={(currentPage + 1) * DEFAULT_ITEMS_PER_PAGE >= totalItems || loading}
                    className="px-3 py-1.5"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No items yet</h3>
            <p className="text-gray-600 mb-6">Add items to this dataset to start evaluation.</p>
            <Button
              onClick={() => setShowAddModal(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Items
            </Button>
          </div>
        )}

        {showAddModal && (
          <AddItemsModal
            datasetId={datasetId}
            datasetType={dataset.dataset_type}
            onClose={() => {
              setShowAddModal(false)
              loadData(currentPage, false)
            }}
          />
        )}

        {showBulkImportModal && (
          <BulkImportModal
            datasetId={datasetId}
            datasetType={dataset.dataset_type}
            onClose={() => {
              setShowBulkImportModal(false)
              loadData(currentPage, false)
            }}
          />
        )}

        <ConfirmModal
          isOpen={showDeleteModal}
          title="Delete Item"
          message="Are you sure you want to delete this item?"
          onConfirm={handleDelete}
          onClose={() => {
            setShowDeleteModal(false)
            setDeleteItemId(null)
          }}
          confirmText="Delete"
          cancelText="Cancel"
          variant="danger"
        />
      </div>
    </AppLayout>
  )
}

function AddItemsModal({ datasetId, datasetType, onClose }: { datasetId: string; datasetType: string; onClose: () => void }) {
  const { addToast } = useToast()
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<Array<{
    query: string
    expected_answer?: string
    expected_chunks?: string[]
    expected_docs?: string[]
    question_type?: string
    metadata?: Record<string, any>
  }>>([{ query: '', expected_answer: '' }])

  const questionTypes = [
    { value: 'factual', label: 'Factual Lookup' },
    { value: 'summarization', label: 'Summarization' },
    { value: 'policy', label: 'Policy/Compliance' },
    { value: 'synthesis', label: 'Multi-Document Synthesis' },
    { value: 'adversarial', label: 'Adversarial' },
    { value: 'comparison', label: 'Comparison' },
    { value: 'causal', label: 'Causal Reasoning' },
    { value: 'temporal', label: 'Temporal' },
    { value: 'general', label: 'General' },
  ]

  const handleAddItem = () => {
    setItems([...items, { query: '', expected_answer: '' }])
  }

  const handleRemoveItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index))
  }

  const handleSubmit = async () => {
    setLoading(true)
    try {
      const validItems = items.filter(item => item.query.trim())
      if (validItems.length === 0) {
        addToast({
          type: 'error',
          message: 'Please add at least one item with a query'
        })
        return
      }

      const response = await apiClient.addDatasetItems(datasetId, validItems)
      if (response.error) {
        addToast({
          type: 'error',
          message: response.error
        })
      } else {
        addToast({
          type: 'success',
          message: `Added ${validItems.length} items successfully`
        })
        onClose()
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to add items'
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Add Dataset Items</h2>
        </div>
        <div className="p-6 space-y-4">
          {items.map((item, index) => (
            <div key={index} className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-gray-900">Item {index + 1}</h3>
                {items.length > 1 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleRemoveItem(index)}
                    className="text-red-600"
                  >
                    Remove
                  </Button>
                )}
              </div>
              <div className="space-y-3">
                <div>
                  <Label>Query *</Label>
                  <Textarea
                    value={item.query}
                    onChange={(e) => {
                      const newItems = [...items]
                      newItems[index].query = e.target.value
                      setItems(newItems)
                    }}
                    placeholder="Enter the query/question"
                    rows={2}
                    className="mt-1"
                  />
                </div>
                {(datasetType === 'golden_qa' || datasetType === 'adversarial') && (
                  <div>
                    <Label>Expected Answer</Label>
                    <Textarea
                      value={item.expected_answer || ''}
                      onChange={(e) => {
                        const newItems = [...items]
                        newItems[index].expected_answer = e.target.value
                        setItems(newItems)
                      }}
                      placeholder="Enter the expected answer"
                      rows={3}
                      className="mt-1"
                    />
                  </div>
                )}
                {datasetType === 'golden_retrieval' && (
                  <>
                    <div>
                      <Label>Expected Chunk IDs (comma-separated)</Label>
                      <Input
                        value={item.expected_chunks?.join(', ') || ''}
                        onChange={(e) => {
                          const newItems = [...items]
                          newItems[index].expected_chunks = e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                          setItems(newItems)
                        }}
                        placeholder="chunk1, chunk2, chunk3"
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <Label>Expected Document IDs (comma-separated)</Label>
                      <Input
                        value={item.expected_docs?.join(', ') || ''}
                        onChange={(e) => {
                          const newItems = [...items]
                          newItems[index].expected_docs = e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                          setItems(newItems)
                        }}
                        placeholder="doc1.pdf, doc2.pdf"
                        className="mt-1"
                      />
                    </div>
                  </>
                )}
                {(datasetType === 'golden_qa' || datasetType === 'adversarial') && (
                  <div>
                    <Label>Expected Document IDs (comma-separated, optional)</Label>
                    <Input
                      value={item.expected_docs?.join(', ') || ''}
                      onChange={(e) => {
                        const newItems = [...items]
                        newItems[index].expected_docs = e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                        setItems(newItems)
                      }}
                      placeholder="doc1.pdf, doc2.pdf"
                      className="mt-1"
                    />
                  </div>
                )}
                <div>
                  <Label>Question Type</Label>
                  <select
                    value={item.question_type || ''}
                    onChange={(e) => {
                      const newItems = [...items]
                      newItems[index].question_type = e.target.value || undefined
                      setItems(newItems)
                    }}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  >
                    <option value="">Select question type...</option>
                    {questionTypes.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label>Metadata (JSON, optional)</Label>
                  <Textarea
                    value={item.metadata ? JSON.stringify(item.metadata, null, 2) : ''}
                    onChange={(e) => {
                      const newItems = [...items]
                      try {
                        newItems[index].metadata = e.target.value.trim() ? JSON.parse(e.target.value) : undefined
                      } catch (err) {
                        // Invalid JSON, keep as is for now
                      }
                      setItems(newItems)
                    }}
                    placeholder='{"difficulty": "easy", "tags": ["important"], "source": "product_docs"}'
                    rows={3}
                    className="mt-1 font-mono text-sm"
                  />
                  <p className="mt-1 text-xs text-gray-500">Enter valid JSON or leave empty</p>
                </div>
              </div>
            </div>
          ))}
          <Button
            variant="outline"
            onClick={handleAddItem}
            className="w-full"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Another Item
          </Button>
        </div>
        <div className="p-6 border-t border-gray-200 flex items-center justify-end gap-3">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Adding...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Add Items
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

function BulkImportModal({ datasetId, datasetType, onClose }: { datasetId: string; datasetType: string; onClose: () => void }) {
  const { addToast } = useToast()
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileInputKey, setFileInputKey] = useState(0) // Key to force re-render of file input
  const [importResult, setImportResult] = useState<{
    items_imported?: number
    errors?: string[]
    error_count?: number
  } | null>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      if (!file.name.endsWith('.csv')) {
        addToast({
          type: 'error',
          message: 'Please select a CSV file'
        })
        // Reset file input
        setFileInputKey(prev => prev + 1)
        return
      }
      setSelectedFile(file)
      setImportResult(null)
    } else {
      setSelectedFile(null)
    }
  }

  const handleRemoveFile = () => {
    setSelectedFile(null)
    setImportResult(null)
    // Force file input to reset by changing its key
    setFileInputKey(prev => prev + 1)
  }

  const handleDownloadTemplate = async () => {
    try {
      setLoading(true)
      await apiClient.downloadDatasetTemplate(datasetType)
      addToast({
        type: 'success',
        message: 'Template downloaded successfully'
      })
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to download template'
      })
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    if (!selectedFile) {
      addToast({
        type: 'error',
        message: 'Please select a CSV file to import'
      })
      return
    }

    setUploading(true)
    try {
      const response = await apiClient.bulkImportDatasetItems(datasetId, selectedFile)
      if (response.error) {
        addToast({
          type: 'error',
          message: response.error
        })
      } else {
        const result = response.data as any
        setImportResult(result)
        if (result.error_count === 0) {
          addToast({
            type: 'success',
            message: `Successfully imported ${result.items_imported} items`
          })
          setTimeout(() => {
            onClose()
          }, 2000)
        } else {
          addToast({
            type: 'warning',
            message: `Imported ${result.items_imported} items with ${result.error_count} errors`
          })
        }
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to import items'
      })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Bulk Import Items</h2>
        </div>
        <div className="p-6 space-y-6">
          <div>
            <Label>CSV File</Label>
            <div className="mt-2 flex items-center gap-3">
              <Input
                key={fileInputKey}
                type="file"
                accept=".csv"
                onChange={handleFileSelect}
                className="flex-1"
              />
              <Button
                variant="outline"
                onClick={handleDownloadTemplate}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Downloading...
                  </>
                ) : (
                  <>
                    <FileText className="h-4 w-4 mr-2" />
                    Download Template
                  </>
                )}
              </Button>
            </div>
            <p className="mt-2 text-sm text-gray-500">
              Upload a CSV file matching the template format for {datasetType} datasets.
            </p>
            {selectedFile && (
              <p className="mt-2 text-sm text-gray-700">
                Selected: <span className="font-medium">{selectedFile.name}</span> ({(selectedFile.size / 1024).toFixed(2)} KB)
              </p>
            )}
          </div>

          {importResult && importResult.errors && importResult.errors.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <h3 className="text-sm font-medium text-yellow-800 mb-2">
                Import completed with {importResult.error_count} errors
              </h3>
              <div className="max-h-40 overflow-y-auto">
                <ul className="text-xs text-yellow-700 space-y-1">
                  {importResult.errors.map((error, idx) => (
                    <li key={idx}>{error}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {importResult && importResult.error_count === 0 && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <p className="text-sm font-medium text-green-800">
                ✅ Successfully imported {importResult.items_imported} items
              </p>
            </div>
          )}
        </div>
        <div className="p-6 border-t border-gray-200 flex items-center justify-end gap-3">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={handleImport}
            disabled={uploading || !selectedFile}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Importing...
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" />
                Import Items
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

