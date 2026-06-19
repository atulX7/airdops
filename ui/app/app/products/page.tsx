'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import Link from 'next/link'
import { Plus, Package, MoreVertical, Trash2, Edit, GitBranch } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/ui/status-badge'
import { ConfirmModal, ResultModal } from '@/components/ui/modal'
import { ErrorState } from '@/components/ui/error-state'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'

interface Product {
  id: string
  workspace_id: string
  owner_user_id: string
  name: string
  status: 'draft' | 'running' | 'ready' | 'failed'
  current_version: number
  created_at: string
  updated_at?: string
}

export default function ProductsPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const queryClient = useQueryClient()
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteProductId, setDeleteProductId] = useState<string | null>(null)
  const [showResultModal, setShowResultModal] = useState(false)
  const [resultModalData, setResultModalData] = useState<{
    type: 'success' | 'error' | 'warning' | 'info'
    title: string
    message: string
  } | null>(null)
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)

  // Fetch products with React Query caching
  const { data: products = [], isLoading, error } = useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const response = await apiClient.getProducts()
      if (response.error) {
        throw new Error(response.error)
      }
      return (response.data as Product[]) || []
    },
    enabled: status === 'authenticated',
    staleTime: 30 * 1000, // 30 seconds - data is fresh for 30s
  })

  // Delete mutation with cache invalidation
  const deleteMutation = useMutation({
    mutationFn: async (productId: string) => {
      const response = await apiClient.deleteProduct(productId)
      if (response.error) {
        throw new Error(response.error)
      }
      return productId
    },
    onSuccess: (deletedId) => {
      // Optimistically remove from cache
      queryClient.setQueryData<Product[]>(['products'], (old = []) =>
        old.filter(p => p.id !== deletedId)
      )
      // Invalidate to sync with server
      queryClient.invalidateQueries({ queryKey: ['products'] })
      
      setResultModalData({
        type: 'success',
        title: 'Product Deleted',
        message: 'Product has been successfully deleted'
      })
      setShowResultModal(true)
    },
    onError: (err: Error) => {
      setResultModalData({
        type: 'error',
        title: 'Delete Failed',
        message: err.message || 'Failed to delete product'
      })
      setShowResultModal(true)
    },
  })

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/')
      return
    }
  }, [status, router])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = () => {
      setOpenDropdown(null)
    }

    if (openDropdown) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [openDropdown])

  // Listen for product creation events (from new product page)
  useEffect(() => {
    const handleProductCreated = () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
    }
    window.addEventListener('productCreated', handleProductCreated)
    return () => window.removeEventListener('productCreated', handleProductCreated)
  }, [queryClient])

  const handleDeleteProduct = (productId: string) => {
    setDeleteProductId(productId)
    setShowDeleteModal(true)
    setOpenDropdown(null)
  }

  const confirmDeleteProduct = async () => {
    if (!deleteProductId) return
    deleteMutation.mutate(deleteProductId)
    setShowDeleteModal(false)
    setDeleteProductId(null)
  }

  const getStatusDescription = (status: string) => {
    switch (status) {
      case 'draft': return 'Product is being configured and not yet running'
      case 'running': return 'Product is actively processing data'
      case 'ready': return 'Product is ready for use'
      case 'failed': return 'Product encountered an error and needs attention'
      default: return 'Unknown status'
    }
  }

  if (status === 'loading' || isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading products...</p>
        </div>
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return null
  }

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        {/* Header */}
        <div className="mb-8">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-4xl font-bold text-gray-900 mb-2 tracking-tight">Products</h1>
              <p className="text-lg text-gray-600">Manage your data products and pipelines</p>
            </div>
            <Link href="/app/products/new">
              <Button className="flex items-center bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg transition-all">
                <Plus className="h-4 w-4 mr-2" />
                New Product
              </Button>
            </Link>
          </div>
        </div>

        {/* Content */}
        <div>
        {error ? (
          <ErrorState
            title="Failed to load products"
            message={error instanceof Error ? error.message : 'An error occurred'}
            onRetry={() => queryClient.invalidateQueries({ queryKey: ['products'] })}
          />
        ) : products.length === 0 ? (
          <div className="text-center py-16">
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-full w-24 h-24 flex items-center justify-center mx-auto mb-6">
              <Package className="h-12 w-12 text-blue-600" />
            </div>
            <h3 className="text-2xl font-semibold text-gray-900 mb-2">No products yet</h3>
            <p className="text-gray-600 mb-8 max-w-md mx-auto">Get started by creating your first data product to begin processing and analyzing your data.</p>
            <Link href="/app/products/new">
              <Button className="flex items-center mx-auto bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg">
                <Plus className="h-4 w-4 mr-2" />
                Create Product
              </Button>
            </Link>
          </div>
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((product) => (
              <div key={product.id} className="bg-white rounded-xl shadow-md border-2 border-gray-100 p-6 hover:shadow-xl hover:border-blue-300 transition-all duration-200 hover:-translate-y-1 group">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-2.5 shadow-sm group-hover:scale-110 transition-transform">
                        <Package className="h-5 w-5 text-white" />
                      </div>
                      <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                        <Link 
                          href={`/app/products/${product.id}`}
                          className="hover:text-blue-600 transition-colors"
                        >
                          {product.name}
                        </Link>
                      </h3>
                    </div>
                    <div className="flex items-center gap-2 mb-3">
                      <StatusBadge status={product.status as any} size="sm" />
                      <div className="flex items-center text-xs text-gray-500 bg-gray-50 px-2 py-1 rounded-md">
                        <GitBranch className="h-3 w-3 mr-1" />
                        <span>v{product.current_version}</span>
                      </div>
                    </div>
                    <p className="text-sm text-gray-500">
                      Created {new Date(product.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="relative">
                    <button 
                      className="text-gray-400 hover:text-gray-600 p-1 rounded-md hover:bg-gray-100 transition-colors"
                      onClick={(e) => {
                        e.stopPropagation()
                        setOpenDropdown(openDropdown === product.id ? null : product.id)
                      }}
                    >
                      <MoreVertical className="h-4 w-4" />
                    </button>
                    {openDropdown === product.id && (
                      <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-xl border-2 border-gray-100 z-20 overflow-hidden">
                        <div className="py-1">
                          <button
                            className="flex items-center w-full px-4 py-2.5 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition-colors"
                            onClick={() => {
                              setOpenDropdown(null)
                              router.push(`/app/products/${product.id}/edit`)
                            }}
                          >
                            <Edit className="h-4 w-4 mr-2" />
                            Edit Product
                          </button>
                          <button
                            className="flex items-center w-full px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
                            onClick={() => handleDeleteProduct(product.id)}
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Delete Product
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <div className="mt-6 pt-4 border-t border-gray-100 flex gap-2">
                  <Link href={`/app/products/${product.id}`} className="flex-1">
                    <Button variant="outline" size="sm" className="w-full border-2 hover:border-blue-300 hover:bg-blue-50 transition-all">
                      View Details
                    </Button>
                  </Link>
                  <Link href={`/app/products/${product.id}/datasources/new`} className="flex-1">
                    <Button size="sm" className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-sm hover:shadow-md transition-all">
                      Add Data Source
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
        </div>

        {/* Modals */}
        <ConfirmModal
          isOpen={showDeleteModal}
          onClose={() => {
            setShowDeleteModal(false)
            setDeleteProductId(null)
          }}
          onConfirm={confirmDeleteProduct}
          title="Delete Product"
          message="Are you sure you want to delete this product? This action cannot be undone and will also delete all associated data sources."
          confirmText="Delete"
          cancelText="Cancel"
          variant="danger"
        />

        {resultModalData && (
          <ResultModal
            isOpen={showResultModal}
            onClose={() => {
              setShowResultModal(false)
              setResultModalData(null)
            }}
            title={resultModalData.title}
            message={resultModalData.message}
            type={resultModalData.type}
          />
        )}
      </div>
    </AppLayout>
  )
}
