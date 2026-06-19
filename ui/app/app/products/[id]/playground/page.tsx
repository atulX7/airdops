'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Search, ExternalLink, Clock, Database, AlertCircle, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'

interface Product {
  id: string
  workspace_id: string
  owner_user_id: string
  name: string
  status: 'draft' | 'running' | 'ready' | 'failed'
  current_version: number
  promoted_version?: number
  vector_creation_enabled?: boolean
  created_at: string
  updated_at?: string
}

interface PlaygroundResult {
  text: string
  score: number
  doc_path: string
  section?: string
  meta: Record<string, any>
  presigned_url?: string
}

interface PlaygroundResponse {
  results: PlaygroundResult[]
  latency_ms: number
  collection_name: string
  total_results: number
}

interface PlaygroundStatus {
  ready: boolean
  reason?: string
  current_version: number
  latest_successful_version?: number  // The version actually being used
  collection_name?: string
  points_count?: number
  vectors_count?: number
}

export default function PlaygroundPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  
  const [product, setProduct] = useState<Product | null>(null)
  const [playgroundStatus, setPlaygroundStatus] = useState<PlaygroundStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Query state
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [useVersion, setUseVersion] = useState<'current' | 'prod'>('current')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<PlaygroundResponse | null>(null)
  
  // Modal states
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
      loadProduct()
      loadPlaygroundStatus()
    }
  }, [status, router, productId])

  const loadProduct = async () => {
    try {
      const response = await apiClient.getProduct(productId)
      
      if (response.error) {
        setError(response.error)
      } else {
        setProduct(response.data as Product)
      }
    } catch (err) {
      setError('Failed to load product')
    } finally {
      setLoading(false)
    }
  }

  const loadPlaygroundStatus = async () => {
    try {
      const response = await apiClient.getPlaygroundStatus(productId)
      
      if (response.error) {
        console.error('Failed to load playground status:', response.error)
        // Set a default status indicating not ready
        setPlaygroundStatus({
          ready: false,
          reason: response.error || 'Failed to check playground status',
          current_version: 0
        })
      } else {
        setPlaygroundStatus(response.data as PlaygroundStatus)
      }
    } catch (err) {
      console.error('Failed to load playground status:', err)
      // Set a default status indicating not ready
      setPlaygroundStatus({
        ready: false,
        reason: 'Failed to check playground status',
        current_version: 0
      })
    }
  }

  const handleSearch = async () => {
    if (!query.trim()) {
      setResultModalData({
        type: 'warning',
        title: 'Empty Query',
        message: 'Please enter a search query'
      })
      setShowResultModal(true)
      return
    }

    setSearching(true)
    try {
      const response = await apiClient.queryPlayground(productId, query.trim(), topK, useVersion)
      
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Search Failed',
          message: response.error
        })
        setShowResultModal(true)
      } else {
        setSearchResults(response.data as PlaygroundResponse)
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Search Failed',
        message: 'An unexpected error occurred'
      })
      setShowResultModal(true)
    } finally {
      setSearching(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !searching) {
      handleSearch()
    }
  }

  const formatScore = (score: number) => {
    return (score * 100).toFixed(1) + '%'
  }

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600 bg-green-100'
    if (score >= 0.6) return 'text-yellow-600 bg-yellow-100'
    return 'text-red-600 bg-red-100'
  }

  if (status === 'loading' || loading) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-600">Loading playground...</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error || !product) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <p className="text-red-600 mb-4">Error: {error || 'Product not found'}</p>
            <Link href="/app/products">
              <Button>Back to Products</Button>
            </Link>
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
            <AlertCircle className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Vector Creation Disabled</h2>
            <p className="text-gray-600 mb-6">
              Playground requires vector creation to be enabled for this product. 
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

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        <div className="max-w-7xl mx-auto">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href="/app/products" className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Products
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <Link href={`/app/products/${productId}`} className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            {product.name}
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Playground</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center">
            <div className="bg-gradient-to-br from-purple-500 to-indigo-600 rounded-xl p-3 mr-4 shadow-lg">
              <Search className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Playground</h1>
              <p className="text-sm text-gray-600 mt-1">Search and explore your indexed data with semantic queries</p>
            </div>
          </div>
        </div>

        {/* Playground Status Banner */}
        {playgroundStatus && !playgroundStatus.ready && (
          <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex items-start">
              <AlertCircle className="h-5 w-5 text-yellow-400 mt-0.5 mr-3 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="text-sm font-medium text-yellow-800">Playground Not Ready</h3>
                <p className="text-sm text-yellow-700 mt-1">{playgroundStatus.reason}</p>
                <div className="mt-3">
                  <Link href={`/app/products/${productId}`}>
                    <Button size="sm" className="bg-yellow-600 hover:bg-yellow-700 text-white">
                      <Play className="h-4 w-4 mr-2" />
                      Run Pipeline
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Playground Status Info */}
        {playgroundStatus && playgroundStatus.ready && (
          <div className="mb-6 bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="flex items-center">
              <Database className="h-5 w-5 text-green-400 mr-3" />
              <div>
                <h3 className="text-sm font-medium text-green-800">Playground Ready</h3>
                <p className="text-sm text-green-700">
                  Version {playgroundStatus.latest_successful_version || playgroundStatus.current_version} • {playgroundStatus.points_count} documents indexed
                </p>
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Panel - Query Interface */}
          <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Search Query</h2>
            
            <div className="space-y-4">
              <div>
                <Label htmlFor="query" className="block text-sm font-medium text-gray-700 mb-2">
                  Query
                </Label>
                <Input
                  id="query"
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Enter your search query..."
                  className="w-full"
                  disabled={!playgroundStatus?.ready || searching}
                />
              </div>

              <div>
                <Label htmlFor="topK" className="block text-sm font-medium text-gray-700 mb-2">
                  Number of Results
                </Label>
                <select
                  id="topK"
                  value={topK}
                  onChange={(e) => setTopK(parseInt(e.target.value))}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  disabled={!playgroundStatus?.ready || searching}
                >
                  {[1, 3, 5, 10, 15, 20].map(num => (
                    <option key={num} value={num}>{num}</option>
                  ))}
                </select>
              </div>

              <div>
                <Label htmlFor="useVersion" className="block text-sm font-medium text-gray-700 mb-2">
                  Version
                </Label>
                <div className="flex space-x-4">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="useVersion"
                      value="current"
                      checked={useVersion === 'current'}
                      onChange={(e) => setUseVersion(e.target.value as 'current' | 'prod')}
                      className="mr-2"
                      disabled={!playgroundStatus?.ready || searching}
                    />
                    <span className="text-sm text-gray-700">Latest (v{playgroundStatus?.latest_successful_version || playgroundStatus?.current_version || 'N/A'})</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="useVersion"
                      value="prod"
                      checked={useVersion === 'prod'}
                      onChange={(e) => setUseVersion(e.target.value as 'current' | 'prod')}
                      className="mr-2"
                      disabled={!playgroundStatus?.ready || searching || !product?.promoted_version}
                    />
                    <span className={`text-sm ${!product?.promoted_version ? 'text-gray-400' : 'text-gray-700'}`}>
                      Production {product?.promoted_version ? `(v${product.promoted_version})` : '(Not Available)'}
                    </span>
                  </label>
                </div>
              </div>

              <Button
                onClick={handleSearch}
                disabled={!playgroundStatus?.ready || searching || !query.trim()}
                className="w-full bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white shadow-md"
              >
                {searching ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Searching...
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4 mr-2" />
                    Search
                  </>
                )}
              </Button>
            </div>

            {/* Search Tips */}
            <div className="mt-6 p-4 bg-gray-50 rounded-lg">
              <h3 className="text-sm font-medium text-gray-900 mb-2">Search Tips</h3>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>• Use natural language queries</li>
                <li>• Try different phrasings for better results</li>
                <li>• Be specific about what you're looking for</li>
                <li>• Results are ranked by semantic similarity</li>
              </ul>
            </div>
          </div>

          {/* Right Panel - Results */}
          <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Search Results</h2>
            
            {!searchResults ? (
              <div className="text-center py-12">
                <Search className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No search performed</h3>
                <p className="text-gray-600">Enter a query and click search to see results</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Search Stats */}
                <div className="flex items-center justify-between text-sm text-gray-600 pb-4 border-b border-gray-200">
                  <span>{searchResults.total_results} results found</span>
                  <div className="flex items-center">
                    <Clock className="h-4 w-4 mr-1" />
                    {searchResults.latency_ms.toFixed(0)}ms
                  </div>
                </div>

                {/* Results List */}
                <div className="space-y-4">
                  {searchResults.results.map((result, index) => (
                    <div key={index} className="border-2 border-gray-200 rounded-xl p-5 hover:border-purple-300 hover:shadow-md transition-all duration-200 bg-gradient-to-br from-white to-gray-50/50">
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center">
                          <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-r from-purple-500 to-indigo-600 text-white text-sm font-bold mr-3">
                            #{index + 1}
                          </span>
                          <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold ${
                            result.score >= 0.8 ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white' :
                            result.score >= 0.6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600 text-white' : 
                            'bg-gradient-to-r from-red-500 to-rose-600 text-white'
                          }`}>
                            {formatScore(result.score)}
                          </span>
                        </div>
                        {result.presigned_url && (
                          <a
                            href={result.presigned_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:text-blue-900 text-sm flex items-center font-medium hover:underline"
                          >
                            <ExternalLink className="h-4 w-4 mr-1" />
                            View Document
                          </a>
                        )}
                      </div>
                      
                      <p className="text-sm text-gray-700 mb-3 line-clamp-3 leading-relaxed">
                        {result.text}
                      </p>
                      
                      <div className="text-xs text-gray-500 bg-gray-50 rounded-lg p-2">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{result.section || 'N/A'}</span>
                          <span className="font-mono text-gray-600">{result.doc_path.split('/').pop()}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {searchResults.results.length === 0 && (
                  <div className="text-center py-8">
                    <Search className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                    <p className="text-gray-600">No results found for your query</p>
                    <p className="text-sm text-gray-500 mt-1">Try different keywords or phrases</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Result Modal */}
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
      </div>
    </AppLayout>
  )
}
