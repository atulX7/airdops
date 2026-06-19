'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, CheckCircle, AlertTriangle, XCircle, TrendingUp, Settings, RefreshCw, Eye, FileText, Database, Zap, BarChart3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton, StatCardSkeleton } from '@/components/ui/skeleton'

interface Product {
  id: string
  workspace_id: string
  owner_user_id: string
  name: string
  status: 'draft' | 'running' | 'ready' | 'failed'
  current_version: number
  promoted_version?: number
  created_at: string
  updated_at?: string
}

interface DataQualityMetrics {
  total_documents: number
  total_chunks: number
  avg_chunk_size: number
  min_chunk_size: number
  max_chunk_size: number
  empty_chunks: number
  duplicate_chunks: number
  encoding_issues: number
  low_quality_chunks: number
}

interface AIReadinessScore {
  overall_score: number
  data_quality_score: number
  chunk_quality_score: number
  embedding_quality_score: number
  coverage_score: number
  recommendations: string[]
  critical_issues: string[]
}

interface AIReadinessResponse {
  product_id: string
  version: number
  collection_name: string
  metrics: DataQualityMetrics
  score: AIReadinessScore
  sample_chunks: Array<{
    text: string
    source_file: string
    chunk_index: number
    quality_issues: string[]
  }>
  last_assessed: string
}

export default function AIReadinessPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  
  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [assessing, setAssessing] = useState(false)
  const [improving, setImproving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [aiReadiness, setAIReadiness] = useState<AIReadinessResponse | null>(null)
  const [useVersion, setUseVersion] = useState<'current' | 'prod'>('current')
  
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

  const assessAIReadiness = async () => {
    setAssessing(true)
    try {
      const response = await apiClient.assessAIReadiness(productId, useVersion)
      
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Assessment Failed',
          message: response.error
        })
        setShowResultModal(true)
      } else {
        setAIReadiness(response.data as AIReadinessResponse)
        setResultModalData({
          type: 'success',
          title: 'Assessment Complete',
          message: `AI readiness assessment completed successfully for ${useVersion === 'prod' ? 'production' : 'current'} version`
        })
        setShowResultModal(true)
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Assessment Failed',
        message: 'An unexpected error occurred during assessment'
      })
      setShowResultModal(true)
    } finally {
      setAssessing(false)
    }
  }

  const improveAIReadiness = async () => {
    setImproving(true)
    try {
      const config = {
        min_chunk_size: 100,
        max_chunk_size: 2000,
        chunk_overlap: 200,
        remove_duplicates: true,
        clean_encoding: true,
        remove_low_quality: true,
        quality_threshold: 0.7
      }
      
      const response = await apiClient.improveAIReadiness(productId, config)
      
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Improvement Failed',
          message: response.error
        })
        setShowResultModal(true)
      } else {
        const result = response.data
        let message = ''
        let type: 'success' | 'error' | 'warning' | 'info' = 'success'
        
        if (result.status === 'completed') {
          message = `Improvement completed! ${result.improvements_applied} chunks improved, ${result.chunks_removed} chunks removed, ${result.chunks_fixed} chunks fixed.`
          type = 'success'
        } else if (result.status === 'no_improvements') {
          message = `No improvements needed. ${result.chunks_removed} low-quality chunks were removed.`
          type = 'info'
        } else if (result.status === 'no_data') {
          message = 'No data found to improve.'
          type = 'warning'
        } else {
          message = result.message || 'Improvement completed with issues.'
          type = 'warning'
        }
        
        setResultModalData({
          type: type,
          title: 'Improvement Complete',
          message: message
        })
        setShowResultModal(true)
        
        // Refresh the assessment to show updated scores
        setTimeout(() => {
          assessAIReadiness()
        }, 2000)
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Improvement Failed',
        message: 'An unexpected error occurred during improvement'
      })
      setShowResultModal(true)
    } finally {
      setImproving(false)
    }
  }

  const getScoreColor = (score: number) => {
    if (score >= 8) return 'text-green-600 bg-green-100'
    if (score >= 6) return 'text-yellow-600 bg-yellow-100'
    return 'text-red-600 bg-red-100'
  }

  const getScoreIcon = (score: number) => {
    if (score >= 8) return <CheckCircle className="h-5 w-5" />
    if (score >= 6) return <AlertTriangle className="h-5 w-5" />
    return <XCircle className="h-5 w-5" />
  }

  if (status === 'loading' || loading) {
    return (
      <AppLayout>
        <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
          <div className="max-w-7xl mx-auto space-y-6">
            <CardSkeleton />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <StatCardSkeleton key={i} />
              ))}
            </div>
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
          <span className="text-sm font-medium text-gray-900">AI Readiness</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="bg-gradient-to-br from-purple-500 to-indigo-600 rounded-xl p-3 mr-4 shadow-lg">
                <TrendingUp className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900">AI Readiness Dashboard</h1>
                <p className="text-sm text-gray-600 mt-1">Assess and improve data quality for optimal AI performance</p>
              </div>
            </div>
            <div className="flex space-x-3">
              {/* Data Source Toggle */}
              <div className="flex items-center space-x-4 mr-4">
                <span className="text-sm font-medium text-gray-700">Data Source:</span>
                <div className="flex space-x-2">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="useVersion"
                      value="current"
                      checked={useVersion === 'current'}
                      onChange={(e) => setUseVersion(e.target.value as 'current' | 'prod')}
                      className="mr-2"
                      disabled={assessing || improving}
                    />
                    <span className="text-sm text-gray-700">Current (v{product.current_version})</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="useVersion"
                      value="prod"
                      checked={useVersion === 'prod'}
                      onChange={(e) => setUseVersion(e.target.value as 'current' | 'prod')}
                      className="mr-2"
                      disabled={assessing || improving || !product.promoted_version}
                    />
                    <span className={`text-sm ${!product.promoted_version ? 'text-gray-400' : 'text-gray-700'}`}>
                      Production {product.promoted_version ? `(v${product.promoted_version})` : '(Not Available)'}
                    </span>
                  </label>
                </div>
              </div>
              
              <Button
                onClick={assessAIReadiness}
                disabled={assessing || (useVersion === 'current' && product.current_version <= 0) || (useVersion === 'prod' && !product.promoted_version)}
                variant="outline"
              >
                {assessing ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600 mr-2"></div>
                    Assessing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Assess
                  </>
                )}
              </Button>
              {aiReadiness && aiReadiness.score.overall_score < 8 && (
                <Button
                  onClick={improveAIReadiness}
                  disabled={improving}
                  className="bg-purple-600 hover:bg-purple-700 text-white"
                >
                  {improving ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Improving...
                    </>
                  ) : (
                    <>
                      <Settings className="h-4 w-4 mr-2" />
                      Improve
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Status Banner */}
        {product.current_version <= 0 && (
          <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="flex items-center">
              <AlertTriangle className="h-5 w-5 text-yellow-400 mr-3" />
              <div>
                <h3 className="text-sm font-medium text-yellow-800">No Data Available</h3>
                <p className="text-sm text-yellow-700 mt-1">Please run a pipeline first to index data before assessing AI readiness.</p>
              </div>
            </div>
          </div>
        )}

        {!aiReadiness ? (
          /* Initial State */
          <div className="text-center py-12">
            <TrendingUp className="h-16 w-16 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">Ready to Assess AI Readiness</h3>
            <p className="text-gray-600 mb-6">Click "Assess" to analyze your data quality and get recommendations for AI optimization.</p>
            <Button
              onClick={assessAIReadiness}
              disabled={assessing || (useVersion === 'current' && product.current_version <= 0) || (useVersion === 'prod' && !product.promoted_version)}
              className="bg-purple-600 hover:bg-purple-700 text-white"
            >
              {assessing ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  Assessing...
                </>
              ) : (
                <>
                  <TrendingUp className="h-4 w-4 mr-2" />
                  Start Assessment
                </>
              )}
            </Button>
          </div>
        ) : (
          /* Assessment Results */
          <div className="space-y-6">
            {/* Overall Score */}
            <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-8 relative overflow-hidden">
              <div className="absolute top-0 right-0 -mr-4 -mt-4 bg-gradient-to-br from-purple-500/10 to-indigo-500/10 rounded-full h-32 w-32"></div>
              <div className="relative">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900 mb-2">Overall AI Readiness Score</h2>
                    <p className="text-sm text-gray-600">
                      📊 Assessing {useVersion === 'prod' ? 'production' : 'current'} data • 
                      <span className="ml-1 inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-blue-500 to-indigo-600 text-white shadow-sm">
                        v{aiReadiness.version}
                      </span>
                    </p>
                  </div>
                  <div className={`flex items-center px-4 py-2 rounded-full text-lg font-bold shadow-md ${
                    aiReadiness.score.overall_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white' :
                    aiReadiness.score.overall_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600 text-white' : 
                    'bg-gradient-to-r from-red-500 to-rose-600 text-white'
                  }`}>
                    {getScoreIcon(aiReadiness.score.overall_score)}
                    <span className="ml-2">{aiReadiness.score.overall_score}/10</span>
                  </div>
                </div>
                
                <div className="w-full bg-gray-200 rounded-full h-4 mb-4 shadow-inner">
                  <div 
                    className={`h-4 rounded-full transition-all duration-700 shadow-md ${
                      aiReadiness.score.overall_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600' :
                      aiReadiness.score.overall_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600' : 
                      'bg-gradient-to-r from-red-500 to-rose-600'
                    }`}
                    style={{ width: `${(aiReadiness.score.overall_score / 10) * 100}%` }}
                  ></div>
                </div>
                
                <p className="text-sm text-gray-500">
                  Last assessed: {new Date(aiReadiness.last_assessed).toLocaleString()}
                </p>
              </div>
            </div>

            {/* Score Breakdown */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
                <div className="flex items-center justify-between mb-3">
                  <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg p-2">
                    <Database className="h-5 w-5 text-white" />
                  </div>
                  <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                    aiReadiness.score.data_quality_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white' :
                    aiReadiness.score.data_quality_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600 text-white' : 
                    'bg-gradient-to-r from-red-500 to-rose-600 text-white'
                  }`}>
                    {aiReadiness.score.data_quality_score}/10
                  </span>
                </div>
                <h3 className="text-base font-semibold text-gray-900 mb-1">Data Quality</h3>
                <p className="text-xs text-gray-600">Encoding, duplicates, empty chunks</p>
                <div className="mt-3 w-full bg-gray-200 rounded-full h-1.5">
                  <div 
                    className={`h-1.5 rounded-full ${
                      aiReadiness.score.data_quality_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600' :
                      aiReadiness.score.data_quality_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600' : 
                      'bg-gradient-to-r from-red-500 to-rose-600'
                    }`}
                    style={{ width: `${(aiReadiness.score.data_quality_score / 10) * 100}%` }}
                  ></div>
                </div>
              </div>
              
              <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
                <div className="flex items-center justify-between mb-3">
                  <div className="bg-gradient-to-br from-green-500 to-emerald-600 rounded-lg p-2">
                    <FileText className="h-5 w-5 text-white" />
                  </div>
                  <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                    aiReadiness.score.chunk_quality_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white' :
                    aiReadiness.score.chunk_quality_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600 text-white' : 
                    'bg-gradient-to-r from-red-500 to-rose-600 text-white'
                  }`}>
                    {aiReadiness.score.chunk_quality_score}/10
                  </span>
                </div>
                <h3 className="text-base font-semibold text-gray-900 mb-1">Chunk Quality</h3>
                <p className="text-xs text-gray-600">Size distribution, content quality</p>
                <div className="mt-3 w-full bg-gray-200 rounded-full h-1.5">
                  <div 
                    className={`h-1.5 rounded-full ${
                      aiReadiness.score.chunk_quality_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600' :
                      aiReadiness.score.chunk_quality_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600' : 
                      'bg-gradient-to-r from-red-500 to-rose-600'
                    }`}
                    style={{ width: `${(aiReadiness.score.chunk_quality_score / 10) * 100}%` }}
                  ></div>
                </div>
              </div>
              
              <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
                <div className="flex items-center justify-between mb-3">
                  <div className="bg-gradient-to-br from-purple-500 to-indigo-600 rounded-lg p-2">
                    <Zap className="h-5 w-5 text-white" />
                  </div>
                  <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                    aiReadiness.score.embedding_quality_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white' :
                    aiReadiness.score.embedding_quality_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600 text-white' : 
                    'bg-gradient-to-r from-red-500 to-rose-600 text-white'
                  }`}>
                    {aiReadiness.score.embedding_quality_score}/10
                  </span>
                </div>
                <h3 className="text-base font-semibold text-gray-900 mb-1">Embedding Quality</h3>
                <p className="text-xs text-gray-600">Vector representation quality</p>
                <div className="mt-3 w-full bg-gray-200 rounded-full h-1.5">
                  <div 
                    className={`h-1.5 rounded-full ${
                      aiReadiness.score.embedding_quality_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600' :
                      aiReadiness.score.embedding_quality_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600' : 
                      'bg-gradient-to-r from-red-500 to-rose-600'
                    }`}
                    style={{ width: `${(aiReadiness.score.embedding_quality_score / 10) * 100}%` }}
                  ></div>
                </div>
              </div>
              
              <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
                <div className="flex items-center justify-between mb-3">
                  <div className="bg-gradient-to-br from-orange-500 to-red-600 rounded-lg p-2">
                    <BarChart3 className="h-5 w-5 text-white" />
                  </div>
                  <span className={`px-3 py-1 rounded-full text-sm font-bold ${
                    aiReadiness.score.coverage_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white' :
                    aiReadiness.score.coverage_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600 text-white' : 
                    'bg-gradient-to-r from-red-500 to-rose-600 text-white'
                  }`}>
                    {aiReadiness.score.coverage_score}/10
                  </span>
                </div>
                <h3 className="text-base font-semibold text-gray-900 mb-1">Coverage</h3>
                <p className="text-xs text-gray-600">Document and chunk volume</p>
                <div className="mt-3 w-full bg-gray-200 rounded-full h-1.5">
                  <div 
                    className={`h-1.5 rounded-full ${
                      aiReadiness.score.coverage_score >= 8 ? 'bg-gradient-to-r from-green-500 to-emerald-600' :
                      aiReadiness.score.coverage_score >= 6 ? 'bg-gradient-to-r from-yellow-500 to-orange-600' : 
                      'bg-gradient-to-r from-red-500 to-rose-600'
                    }`}
                    style={{ width: `${(aiReadiness.score.coverage_score / 10) * 100}%` }}
                  ></div>
                </div>
              </div>
            </div>

            {/* Metrics */}
            <div className="bg-white rounded-xl shadow-lg border-2 border-gray-100 p-8">
              <h2 className="text-xl font-bold text-gray-900 mb-6 flex items-center">
                <BarChart3 className="h-5 w-5 mr-2 text-purple-600" />
                Data Quality Metrics
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                <div className="text-center p-4 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl border border-blue-100">
                  <div className="text-3xl font-bold text-gray-900 mb-1">{aiReadiness.metrics.total_documents}</div>
                  <div className="text-sm font-medium text-gray-600">Documents</div>
                </div>
                <div className="text-center p-4 bg-gradient-to-br from-green-50 to-emerald-50 rounded-xl border border-green-100">
                  <div className="text-3xl font-bold text-gray-900 mb-1">{aiReadiness.metrics.total_chunks}</div>
                  <div className="text-sm font-medium text-gray-600">Chunks</div>
                </div>
                <div className="text-center p-4 bg-gradient-to-br from-purple-50 to-indigo-50 rounded-xl border border-purple-100">
                  <div className="text-3xl font-bold text-gray-900 mb-1">{Math.round(aiReadiness.metrics.avg_chunk_size)}</div>
                  <div className="text-sm font-medium text-gray-600">Avg Chunk Size</div>
                </div>
                <div className="text-center p-4 bg-gradient-to-br from-orange-50 to-red-50 rounded-xl border border-orange-100">
                  <div className="text-3xl font-bold text-gray-900 mb-1">{aiReadiness.metrics.duplicate_chunks}</div>
                  <div className="text-sm font-medium text-gray-600">Duplicates</div>
                </div>
              </div>
            </div>

            {/* Critical Issues */}
            {aiReadiness.score.critical_issues.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-start">
                  <XCircle className="h-5 w-5 text-red-400 mt-0.5 mr-3 flex-shrink-0" />
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-red-800">Critical Issues</h3>
                    <div className="mt-2 space-y-3">
                      {aiReadiness.score.critical_issues.map((issue, index) => (
                        <div key={index} className="flex items-center justify-between bg-white rounded-lg p-3 border border-red-100">
                          <p className="text-sm text-red-700 flex-1">{issue}</p>
                          <div className="ml-3">
                            <Button
                              size="sm"
                              className="text-xs bg-red-600 hover:bg-red-700 text-white"
                              onClick={() => improveAIReadiness()}
                              disabled={improving}
                            >
                              {improving ? 'Fixing...' : 'Fix Now'}
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Recommendations */}
            {aiReadiness.score.recommendations.length > 0 && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start">
                  <AlertTriangle className="h-5 w-5 text-blue-400 mt-0.5 mr-3 flex-shrink-0" />
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-blue-800">Recommendations</h3>
                    <div className="mt-2 space-y-3">
                      {aiReadiness.score.recommendations.map((recommendation, index) => (
                        <div key={index} className="flex items-center justify-between bg-white rounded-lg p-3 border border-blue-100">
                          <p className="text-sm text-blue-700 flex-1">{recommendation}</p>
                          <div className="ml-3 flex space-x-2">
                            {recommendation.includes('duplicate') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-xs"
                                onClick={() => improveAIReadiness()}
                                disabled={improving}
                              >
                                {improving ? 'Processing...' : 'Remove Duplicates'}
                              </Button>
                            )}
                            {recommendation.includes('chunk size') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-xs"
                                onClick={() => improveAIReadiness()}
                                disabled={improving}
                              >
                                {improving ? 'Processing...' : 'Fix Chunk Sizes'}
                              </Button>
                            )}
                            {recommendation.includes('low-quality') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-xs"
                                onClick={() => improveAIReadiness()}
                                disabled={improving}
                              >
                                {improving ? 'Processing...' : 'Clean Quality'}
                              </Button>
                            )}
                            {recommendation.includes('data sources') && (
                              <Link href={`/app/products/${productId}/datasources/new`}>
                                <Button
                                  size="sm"
                                  className="text-xs bg-blue-600 hover:bg-blue-700 text-white"
                                >
                                  Add Data Source
                                </Button>
                              </Link>
                            )}
                            {recommendation.includes('chunking strategy') && (
                              <Link href={`/app/products/${productId}/edit`}>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="text-xs"
                                >
                                  Configure Chunking
                                </Button>
                              </Link>
                            )}
                            {!recommendation.includes('duplicate') && 
                             !recommendation.includes('chunk size') && 
                             !recommendation.includes('low-quality') && 
                             !recommendation.includes('data sources') && 
                             !recommendation.includes('chunking strategy') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-xs"
                                onClick={() => improveAIReadiness()}
                                disabled={improving}
                              >
                                {improving ? 'Processing...' : 'Apply Fix'}
                              </Button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Sample Chunks */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Sample Chunks</h2>
              <div className="space-y-4">
                {aiReadiness.sample_chunks.map((chunk, index) => (
                  <div key={index} className="border border-gray-200 rounded-lg p-4">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center">
                        <FileText className="h-4 w-4 text-gray-400 mr-2" />
                        <span className="text-sm font-medium text-gray-900">
                          {chunk.source_file.split('/').pop()} - Chunk {chunk.chunk_index}
                        </span>
                      </div>
                      {chunk.quality_issues.length > 0 && (
                        <div className="flex space-x-1">
                          {chunk.quality_issues.map((issue, issueIndex) => (
                            <span key={issueIndex} className="px-2 py-1 bg-red-100 text-red-800 text-xs rounded">
                              {issue}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <p className="text-sm text-gray-700">{chunk.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

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
