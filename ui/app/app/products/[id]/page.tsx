'use client'

import { useState, useEffect, useCallback } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, ArrowRight, Package, Database, Settings, Settings2, Play, Pause, Search, TrendingUp, BarChart3, AlertTriangle, GitBranch, FileText, Download, FileSpreadsheet, Upload, Loader2, ArrowDownToLine, CheckCircle2, Home, Shield, Layers, Lock, FileCheck, FileJson, FileCode, FileSpreadsheet as FileCsv, RefreshCw, X, Eye, Cpu, Rocket } from 'lucide-react'
import { StatusBadge } from '@/components/ui/status-badge'
import { TableSkeleton, CardSkeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { ConfirmModal, ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient, LineageOverview, LineageRecord, ChunkMetadata } from '@/lib/api-client'
import { getApiUrl } from '@/lib/config'
import { DataQualityBanner } from '@/components/DataQualityBanner'
import { DataQualityViolationsDrawer } from '@/components/DataQualityViolationsDrawer'
import { DataQualityRulesEditor } from '@/components/DataQualityRulesEditor'
import { AITrustScoreDisplay } from '@/components/AITrustScoreDisplay'
import { useToast } from '@/components/ui/toast'
import PipelineDetailsModal from '@/components/PipelineDetailsModal'
import { SectionHeader } from '@/components/ui/section-header'
import { ComingSoonBadge } from '@/components/ui/coming-soon-badge'


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

interface Product {
  id: string
  workspace_id: string
  owner_user_id: string
  name: string
  status: 'draft' | 'running' | 'ready' | 'failed' | 'failed_policy' | 'ready_with_warnings'  // M2
  current_version: number
  promoted_version?: number
  playbook_id?: string | null  // M1 (null means auto-detect)
  playbook_selection?: {  // Auto-detection metadata
    playbook_id?: string
    method?: 'auto_detected' | 'manual' | 'document_type_mapped'
    reason?: string
    detected_at?: string
    confidence?: number
    files_analyzed?: number
  }
  chunking_config?: {
    mode?: 'auto' | 'manual'
    resolved_settings?: {
      content_type?: string
      source_quality?: string
      chunk_size?: number
      chunk_overlap?: number
      chunking_strategy?: string
      confidence?: number
    }
    auto_settings?: any
    manual_settings?: any
    last_analyzed?: string
    analysis_confidence?: number
    sample_files_analyzed?: any[]
  }
  preprocessing_stats?: {  // M1
    sections?: number
    chunks?: number
    mid_sentence_boundary_rate?: number
    [key: string]: any
  }
  trust_score?: number  // M2
  policy_status?: string  // M2: 'passed' | 'failed' | 'warnings' | 'unknown'
  chunking_strategy?: string  // From latest successful pipeline run
  vector_creation_enabled?: boolean  // Enable vector/embedding creation and indexing
  created_at: string
  updated_at?: string
}

interface DataSource {
  id: string
  workspace_id: string
  product_id: string
  type: 'web' | 'db' | 'confluence' | 'sharepoint' | 'folder'
  config: any
  last_cursor?: any
  created_at: string
  updated_at?: string
}

interface PipelineRun {
  id: string
  product_id: string
  version: number
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  started_at?: string
  finished_at?: string
  dag_run_id?: string
  metrics: any
  created_at: string
}

// MLflowMetrics interface removed - MLflow integration disabled

export default function ProductDetailPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  const { addToast } = useToast()
  
  const [product, setProduct] = useState<Product | null>(null)
  const [dataSources, setDataSources] = useState<DataSource[]>([])
  // MLflow metrics state removed - MLflow integration disabled
  const [loading, setLoading] = useState(true)
  const [loadingData, setLoadingData] = useState({
    product: true,
    dataSources: true,
    artifacts: false,
    pipelineRuns: false,
  })
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'ai-trust-score' | 'lineage' | 'chunk-metadata' | 'acl' | 'datasources' | 'data-quality' | 'exports'>('overview')
  const [testingConnection, setTestingConnection] = useState<string | null>(null)
  const [ingestingDataSource, setIngestingDataSource] = useState<string | null>(null)
  const [ingestionResults, setIngestionResults] = useState<Record<string, any>>({})
  const [pipelineArtifacts, setPipelineArtifacts] = useState<any[]>([])
  const [loadingArtifacts, setLoadingArtifacts] = useState(false)
  const [pipelineRuns, setPipelineRuns] = useState<PipelineRun[]>([])
  const [loadingPipelineRuns, setLoadingPipelineRuns] = useState(false)
  const [pipelineRunsPage, setPipelineRunsPage] = useState(0)
  const [pipelineRunsTotal, setPipelineRunsTotal] = useState(0)
  const PIPELINE_RUNS_PER_PAGE = 5
  const [runningPipeline, setRunningPipeline] = useState(false)
  const [pipelineConflict, setPipelineConflict] = useState<any>(null)
  const [promotingVersion, setPromotingVersion] = useState<number | null>(null)
  const [selectedRunForDetails, setSelectedRunForDetails] = useState<PipelineRun | null>(null)
  const [downloadingValidationSummary, setDownloadingValidationSummary] = useState(false)
  const [downloadingTrustReport, setDownloadingTrustReport] = useState(false)
  const [viewingArtifact, setViewingArtifact] = useState<any | null>(null)
  const [artifactContent, setArtifactContent] = useState<string | null>(null)
  const [loadingArtifactContent, setLoadingArtifactContent] = useState(false)
  
  // Data quality states
  const [dataQualityViolations, setDataQualityViolations] = useState<any[]>([])
  const [showViolationsDrawer, setShowViolationsDrawer] = useState(false)
  const [showRulesEditor, setShowRulesEditor] = useState(false)
  const [loadingViolations, setLoadingViolations] = useState(false)
  const [existingRules, setExistingRules] = useState<any>(null)
  const [exports, setExports] = useState<any[]>([])
  const [loadingExports, setLoadingExports] = useState(false)
  const [showCreateExportModal, setShowCreateExportModal] = useState(false)
  const [creatingExport, setCreatingExport] = useState(false)
  const showAccessControlAndExports = false

  // Lineage state
  const [lineageOverview, setLineageOverview] = useState<LineageOverview | null>(null)
  const [lineageRecords, setLineageRecords] = useState<LineageRecord[]>([])
  const [loadingLineage, setLoadingLineage] = useState(false)
  const [lineageError, setLineageError] = useState<string | null>(null)

  // Chunk metadata state
  const [chunkMetadata, setChunkMetadata] = useState<ChunkMetadata[]>([])
  const [chunkMetadataHasMore, setChunkMetadataHasMore] = useState<boolean>(false)
  const [chunkMetadataPage, setChunkMetadataPage] = useState<number>(0)
  const [loadingChunkMetadata, setLoadingChunkMetadata] = useState(false)
  const [chunkMetadataError, setChunkMetadataError] = useState<string | null>(null)
  
  // Modal states
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deleteDataSourceId, setDeleteDataSourceId] = useState<string | null>(null)
  const [showResultModal, setShowResultModal] = useState(false)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [confirmModalData, setConfirmModalData] = useState<{
    title: string
    message: string
    onConfirm: () => void
  } | null>(null)
  const [showPipelineModal, setShowPipelineModal] = useState(false)
  const [resultModalData, setResultModalData] = useState<{
    type: 'success' | 'error' | 'warning' | 'info'
    title: string
    message: string
    details?: string
  } | null>(null)

  // Fix 1 & 2: Parallelize initial API calls
  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/')
      return
    }

    if (status === 'authenticated' && productId) {
      // Load product and data sources in parallel
      Promise.all([
        loadProduct(),
      loadDataSources()
      ]).catch(err => {
        console.error('Failed to load initial data:', err)
      })
    }
  }, [status, router, productId])

  // Fix 1 & 2: Load pipeline runs first, then artifacts (artifacts need pipeline runs to determine correct version)
  useEffect(() => {
    if (!product) return

    // Load pipeline runs first, then artifacts (artifacts need pipeline runs to determine correct version)
    const loadData = async () => {
      const runs = await loadPipelineRuns()
      // After pipeline runs are loaded, load artifacts with correct version
      // Pass the runs data directly to avoid async state issues
      await loadPipelineArtifacts(runs)
    }
    
    loadData().catch(err => {
      console.error('Failed to load product-dependent data:', err)
    })

    // Fix 4: Lazy load non-critical data - only load when needed (in tab change handler)
  }, [product])


  // Fix 4: Lazy load data when switching to relevant tabs
  useEffect(() => {
    if (!product) return

    // Load data quality violations only when data-quality tab is active
    if (activeTab === 'data-quality' && dataQualityViolations.length === 0 && !loadingViolations) {
      loadDataQualityViolations()
      loadDataQualityRules()
    }

    // Load exports only when exports tab is active
    if (activeTab === 'exports' && exports.length === 0 && !loadingExports) {
      loadExports()
    }

    // Load lineage data only when lineage tab is active
    if (activeTab === 'lineage' && !loadingLineage && !lineageOverview && !lineageError) {
      loadLineageData()
    }

    // Load chunk metadata only when chunk-metadata tab is active
    if (activeTab === 'chunk-metadata' && !loadingChunkMetadata && chunkMetadata.length === 0 && !chunkMetadataError) {
      loadChunkMetadata(0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, product?.id])

  const loadProduct = async () => {
    setLoadingData(prev => ({ ...prev, product: true }))
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
      setLoadingData(prev => ({ ...prev, product: false }))
    }
  }

  // MLflow metrics loading removed - MLflow integration disabled

  const loadDataSources = async () => {
    setLoadingData(prev => ({ ...prev, dataSources: true }))
    try {
      const response = await apiClient.getDataSources(productId)
      
      if (response.error) {
        console.error('Failed to load data sources:', response.error)
      } else {
        setDataSources((response.data as DataSource[]) || [])
      }
    } catch (err) {
      console.error('Failed to load data sources:', err)
    } finally {
      setLoadingData(prev => ({ ...prev, dataSources: false }))
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'draft': return 'bg-gray-100 text-gray-800'
      case 'running': return 'bg-blue-100 text-blue-800'
      case 'ready': return 'bg-green-100 text-green-800'
      case 'failed': return 'bg-red-100 text-red-800'
      case 'failed_policy': return 'bg-red-100 text-red-800'  // M2
      case 'ready_with_warnings': return 'bg-yellow-100 text-yellow-800'  // M2
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const getDataSourceTypeIcon = (type: string) => {
    switch (type) {
      case 'web': return '🌐'
      case 'db': return '🗄️'
      case 'confluence': return '📄'
      case 'sharepoint': return '📁'
      case 'folder': return '📂'
      default: return '📊'
    }
  }

  const truncateText = (text: string, maxLength: number = 30) => {
    if (text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  const getDataSourceDisplayInfo = (datasource: DataSource) => {
    const config = datasource.config || {}
    
    switch (datasource.type) {
      case 'web':
        return {
          title: 'Web Scraping',
          subtitle: config.url ? truncateText(config.url, 35) : 'No URL configured',
          details: config.selector ? `Selector: ${truncateText(config.selector, 20)}` : 'No selector',
          fullSubtitle: config.url || 'No URL configured'
        }
      case 'db':
        return {
          title: 'Database',
          subtitle: `${config.host || 'Unknown'}:${config.port || 'Unknown'}`,
          details: config.database ? `Database: ${config.database}` : 'No database specified',
          fullSubtitle: `${config.host || 'Unknown'}:${config.port || 'Unknown'}`
        }
      case 'confluence':
        // Check for both space_keys (plural) and space_key (singular) to handle different data formats
        const spaceKeys = config.space_keys || config.space_key
        const hasSpaceKeys = spaceKeys && 
          (typeof spaceKeys === 'string' ? spaceKeys.trim() : String(spaceKeys).trim())
        
        return {
          title: 'Confluence',
          subtitle: config.base_url ? truncateText(config.base_url, 35) : 'No base URL configured',
          details: hasSpaceKeys ? `Spaces: ${truncateText(String(spaceKeys), 20)}` : 'All spaces',
          fullSubtitle: config.base_url || 'No base URL configured'
        }
      case 'sharepoint':
        return {
          title: 'SharePoint',
          subtitle: config.site_url ? truncateText(config.site_url, 35) : 'No site URL configured',
          details: config.tenant_id ? `Tenant: ${truncateText(config.tenant_id, 20)}` : 'No tenant ID',
          fullSubtitle: config.site_url || 'No site URL configured'
        }
      case 'folder':
        return {
          title: 'Local Folder',
          subtitle: config.path ? truncateText(config.path, 35) : 'No path configured',
          details: config.file_types ? `Types: ${truncateText(config.file_types, 20)}` : 'All file types',
          fullSubtitle: config.path || 'No path configured'
        }
      default:
        return {
          title: 'Custom',
          subtitle: 'Custom configuration',
          details: 'Custom data source',
          fullSubtitle: 'Custom configuration'
        }
    }
  }

  const handleIngestDataSource = async (datasourceId: string) => {
    setIngestingDataSource(datasourceId)
    try {
      const response = await apiClient.syncFullDataSource(datasourceId)
      
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Ingestion Failed',
          message: typeof response.error === 'string' ? response.error : 'Ingestion failed'
        })
      } else {
        // Store the ingestion result
        setIngestionResults(prev => ({
          ...prev,
          [datasourceId]: response.data
        }))
        
        setResultModalData({
          type: 'success',
          title: 'Ingestion Completed',
          message: `Successfully ingested ${response.data.files} files (${(response.data.bytes / 1024 / 1024).toFixed(2)} MB) in ${response.data.duration.toFixed(2)}s`
        })
      }
      setShowResultModal(true)
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Ingestion Failed',
        message: 'Failed to run ingestion'
      })
      setShowResultModal(true)
    } finally {
      setIngestingDataSource(null)
    }
  }

  const handleTestConnection = async (datasourceId: string) => {
    setTestingConnection(datasourceId)
    try {
      const response = await apiClient.testConnection(datasourceId)
      
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Connection Test Failed',
          message: typeof response.error === 'string' ? response.error : 'Connection test failed'
        })
      } else {
        setResultModalData({
          type: response.data.ok ? 'success' : 'error',
          title: response.data.ok ? 'Connection Test Successful' : 'Connection Test Failed',
          message: typeof response.data.message === 'string' ? response.data.message : 'Connection test completed'
        })
      }
      setShowResultModal(true)
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Connection Test Failed',
        message: 'Failed to test connection'
      })
      setShowResultModal(true)
    } finally {
      setTestingConnection(null)
    }
  }


  const loadPipelineArtifacts = async (runsOverride?: PipelineRun[]) => {
    if (!product) return
    
    setLoadingArtifacts(true)
    setLoadingData(prev => ({ ...prev, artifacts: true }))
    try {
      let artifactsVersion: number | null = null
      let pipelineRunId: string | undefined = undefined
      
      // Priority 1: Use promoted_version if available (actual production)
      if (product.promoted_version !== null && product.promoted_version !== undefined) {
        artifactsVersion = product.promoted_version
      } else {
        // Priority 2: Find the most recent succeeded pipeline run
        // Use runsOverride if provided (from async call), otherwise use state
        const runsToCheck = runsOverride || pipelineRuns
        const succeededRuns = runsToCheck.filter(run => run.status === 'succeeded')
        
        if (succeededRuns.length > 0) {
          // Sort by created_at descending to get most recent
          const mostRecentSucceeded = succeededRuns.sort((a, b) => {
            const dateA = new Date(a.started_at || a.created_at || 0).getTime()
            const dateB = new Date(b.started_at || b.created_at || 0).getTime()
            return dateB - dateA
          })[0]
          artifactsVersion = mostRecentSucceeded.version
          pipelineRunId = mostRecentSucceeded.id
        } else {
          // No succeeded runs found, don't load artifacts
          setPipelineArtifacts([])
          setLoadingArtifacts(false)
          setLoadingData(prev => ({ ...prev, artifacts: false }))
          return
        }
      }
      
      if (artifactsVersion === null) {
        setPipelineArtifacts([])
        setLoadingArtifacts(false)
        setLoadingData(prev => ({ ...prev, artifacts: false }))
        return
      }
      
      const response = await apiClient.getPipelineArtifacts(product.id, artifactsVersion, pipelineRunId)
      
      if (response.data) {
        setPipelineArtifacts(response.data.artifacts || [])
      } else {
        setPipelineArtifacts([])
      }
    } catch (err) {
      console.error('Failed to load pipeline artifacts:', err)
      setPipelineArtifacts([])
    } finally {
      setLoadingArtifacts(false)
      setLoadingData(prev => ({ ...prev, artifacts: false }))
    }
  }

  const handleViewArtifact = async (artifact: any) => {
    setViewingArtifact(artifact)
    setLoadingArtifactContent(true)
    setArtifactContent(null)

    try {
      if (artifact.artifact_type?.toLowerCase() === 'vector') {
        // For vectors, show info message - no downloadable content
        setArtifactContent('Vector artifacts are stored in the vector database. Use the Playground to query them.')
        setLoadingArtifactContent(false)
        return
      }

      if (!artifact.id) {
        addToast({
          type: 'error',
          message: 'Artifact ID is missing',
        })
        setArtifactContent('Artifact ID is missing. Please contact support.')
        setLoadingArtifactContent(false)
        return
      }

      // Use full backend API URL to avoid Next.js routing
      const apiUrl = getApiUrl()
      
      // Get authentication token from cookie
      const getAuthToken = () => {
        const cookie = document.cookie
          .split('; ')
          .find(row => row.startsWith('primedata_api_token='))
        if (!cookie) return null
        const value = cookie.split('=').slice(1).join('=')
        return value ? decodeURIComponent(value) : null
      }
      
      const token = getAuthToken()
      const headers: Record<string, string> = { 'Accept': '*/*' }
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      
      const fetchResponse = await fetch(`${apiUrl}/api/v1/pipeline/artifacts/${artifact.id}/content`, {
        method: 'GET',
        headers,
        // Removed credentials: 'include' - using Authorization header only
      })

      if (!fetchResponse.ok) {
        const errorText = await fetchResponse.text()
        throw new Error(`Failed to fetch artifact: ${fetchResponse.status} ${fetchResponse.statusText} - ${errorText}`)
      }

      const contentType = fetchResponse.headers.get('content-type') || ''
      
      if (contentType.includes('application/json') || artifact.artifact_type?.toLowerCase() === 'json') {
        const json = await fetchResponse.json()
        setArtifactContent(JSON.stringify(json, null, 2))
      } else if (contentType.includes('text/csv') || artifact.artifact_type?.toLowerCase() === 'csv') {
        const text = await fetchResponse.text()
        setArtifactContent(text)
      } else if (contentType.includes('application/pdf') || artifact.artifact_type?.toLowerCase() === 'pdf') {
        // For PDF, show message and provide download link
        setArtifactContent('PDF files cannot be displayed in the viewer. Please use the download button to view the file.')
      } else {
        // For JSONL or other text formats
        const text = await fetchResponse.text()
        setArtifactContent(text)
      }
    } catch (err) {
      console.error('Failed to load artifact content:', err)
      const errorMessage = err instanceof Error ? err.message : 'Failed to load artifact content'
      addToast({
        type: 'error',
        message: errorMessage,
      })
      // Set error content to show in modal
      setArtifactContent(`Error loading artifact: ${errorMessage}`)
    } finally {
      setLoadingArtifactContent(false)
    }
  }

  const loadPipelineRuns = async (): Promise<PipelineRun[]> => {
    if (!product) return []
    
    setLoadingPipelineRuns(true)
    setLoadingData(prev => ({ ...prev, pipelineRuns: true }))
    try {
      // Always load only the first 5 runs (no pagination on overview page)
      const response = await apiClient.getPipelineRuns(product.id, 5, 0)
      if (response.data) {
        let runs: PipelineRun[] = []
        // Handle both old format (array) and new format (object with runs, total, etc.)
        if (Array.isArray(response.data)) {
          runs = response.data.slice(0, 5) // Ensure only 5
          setPipelineRuns(runs)
          setPipelineRunsTotal(response.data.length)
        } else {
          runs = (response.data.runs || []).slice(0, 5) // Ensure only 5
          setPipelineRuns(runs)
          setPipelineRunsTotal(response.data.total || 0)
        }
        setPipelineRunsPage(0) // Always reset to page 0
        return runs
      }
      return []
    } catch (err) {
      console.error('Failed to load pipeline runs:', err)
      return []
    } finally {
      setLoadingPipelineRuns(false)
      setLoadingData(prev => ({ ...prev, pipelineRuns: false }))
    }
  }

  const CHUNK_METADATA_PAGE_SIZE = 20

  const loadLineageData = async () => {
    if (!product) return

    setLoadingLineage(true)
    setLineageError(null)
    try {
      const overviewResp = await apiClient.getLineageOverview(product.id)
      if (overviewResp.error) {
        throw new Error(overviewResp.error)
      }
      if (overviewResp.data) {
        setLineageOverview(overviewResp.data as LineageOverview)
      }

      // Ensure we have pipeline runs to pick the latest run ID
      let runs = pipelineRuns
      if (!runs || runs.length === 0) {
        runs = await loadPipelineRuns()
      }

      const latestRun = runs && runs[0]
      if (latestRun?.id) {
        const lineageResp = await apiClient.getLineageForRun(product.id, latestRun.id as string)
        if (lineageResp.error) {
          throw new Error(lineageResp.error)
        }
        setLineageRecords((lineageResp.data?.records || []) as LineageRecord[])
      } else {
        setLineageRecords([])
      }
    } catch (err: any) {
      const message = err instanceof Error ? err.message : 'Failed to load lineage data'
      setLineageError(message)
      addToast({
        type: 'error',
        message,
      })
    } finally {
      setLoadingLineage(false)
    }
  }

  const loadChunkMetadata = async (page: number = 0) => {
    if (!product) return

    setLoadingChunkMetadata(true)
    setChunkMetadataError(null)
    try {
      const offset = page * CHUNK_METADATA_PAGE_SIZE
      const resp = await apiClient.getChunkMetadata(product.id, {
        limit: CHUNK_METADATA_PAGE_SIZE,
        offset,
      })

      if (resp.error) {
        throw new Error(resp.error)
      }

      const data = (resp.data as ChunkMetadata[]) || []
      setChunkMetadata(data)
      setChunkMetadataPage(page)
      setChunkMetadataHasMore(data.length === CHUNK_METADATA_PAGE_SIZE)
    } catch (err: any) {
      const message = err instanceof Error ? err.message : 'Failed to load chunk metadata'
      setChunkMetadataError(message)
      addToast({
        type: 'error',
        message,
      })
    } finally {
      setLoadingChunkMetadata(false)
    }
  }

  const loadDataQualityViolations = async () => {
    if (!product) return
    
    setLoadingViolations(true)
    try {
      const response = await apiClient.get(`/data-quality/products/${product.id}/violations`)
      if (response.data) {
        setDataQualityViolations(response.data || [])
      }
    } catch (err) {
      console.error('Failed to load data quality violations:', err)
    } finally {
      setLoadingViolations(false)
    }
  }

  const loadDataQualityRules = async () => {
    if (!product) return
    
    try {
      const response = await apiClient.get(`/data-quality/products/${product.id}/rules`)
      if (response.data) {
        setExistingRules(response.data)
      }
    } catch (err) {
      console.error('Failed to load data quality rules:', err)
      // Don't show error to user, just log it
    }
  }

  const handleSaveDataQualityRules = async (rules: any) => {
    if (!product) return
    
    try {
      const response = await apiClient.put(`/data-quality/products/${product.id}/rules`, { rules })
      
      if (response.error) {
        throw new Error(response.error)
      }
      
      if (response.data) {
        setResultModalData({
          type: 'success',
          title: 'Data Quality Rules Saved',
          message: 'Your data quality rules have been saved successfully.',
          details: `Rules will be applied to the next pipeline run.`
        })
        setShowResultModal(true)
      }
    } catch (err) {
      console.error('Failed to save data quality rules:', err)
      
      let errorMessage = 'Unknown error occurred'
      let errorDetails = ''
      
      if (err instanceof Error) {
        errorMessage = err.message
        // Try to extract more specific error details
        if (err.message.includes('Invalid rules format')) {
          errorDetails = 'The rules format is invalid. Please check your rule configurations.'
        } else if (err.message.includes('400')) {
          errorDetails = 'Bad request - please check your rule data.'
        } else if (err.message.includes('404')) {
          errorDetails = 'Product not found.'
        } else if (err.message.includes('500')) {
          errorDetails = 'Server error occurred while saving rules.'
        }
      }
      
      setResultModalData({
        type: 'error',
        title: 'Failed to Save Rules',
        message: errorMessage,
        details: errorDetails
      })
      setShowResultModal(true)
    }
  }

  const handleRunPipeline = async (version?: number, forceRun?: boolean) => {
    if (!product) return
    
    setRunningPipeline(true)
    try {
      const response = await apiClient.triggerPipeline(product.id, version, forceRun)
      
      if (response.error) {
        // Check if it's a conflict error (409)
        if (response.status === 409) {
          // Handle both structured errorData and plain error messages
          const conflictData = response.errorData && typeof response.errorData === 'object' 
            ? response.errorData 
            : { message: response.error || 'A pipeline run is already in progress' }
          setPipelineConflict(conflictData)
          setShowPipelineModal(false)
          return
        }
        
        setResultModalData({
          type: 'error',
          title: 'Pipeline Failed',
          message: typeof response.error === 'string' ? response.error : 'An unexpected error occurred'
        })
        setShowResultModal(true)
      } else {
        setResultModalData({
          type: 'success',
          title: 'Pipeline Started',
          message: `Pipeline run triggered successfully. Version: ${response.data.version}`
        })
        
        // Refresh pipeline runs
        await loadPipelineRuns()
        setShowResultModal(true)
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Pipeline Failed',
        message: 'Failed to trigger pipeline'
      })
      setShowResultModal(true)
    } finally {
      setRunningPipeline(false)
      setShowPipelineModal(false)
    }
  }

  const handleDownloadValidationSummary = async () => {
    if (!product) return
    
    setDownloadingValidationSummary(true)
    try {
      const blob = await apiClient.downloadValidationSummary(product.id)
      if (blob) {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `validation_summary_${product.id}.csv`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        
        addToast({
          type: 'success',
          message: 'Validation summary downloaded successfully',
        })
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to download validation summary',
      })
    } finally {
      setDownloadingValidationSummary(false)
    }
  }

  const handleDownloadTrustReport = async () => {
    if (!product) return
    
    setDownloadingTrustReport(true)
    try {
      const blob = await apiClient.downloadTrustReport(product.id)
      if (blob) {
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `trust_report_${product.id}.pdf`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
        
        addToast({
          type: 'success',
          message: 'Trust report downloaded successfully',
        })
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to download trust report',
      })
    } finally {
      setDownloadingTrustReport(false)
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
          const friendlyGates = formatFailedGates(failedGates)
          
          const gatesList = friendlyGates.length > 0 
            ? `\n\nThe following quality gates did not meet the required thresholds:\n${friendlyGates.map(g => `• ${g}`).join('\n')}`
            : ''
          
          setConfirmModalData({
            title: 'Quality Gates Failed',
            message: `Version ${version} has failed quality gates and is blocking promotion to production.${gatesList}\n\nAre you sure you want to promote this version anyway? This will override the quality gates.`,
            onConfirm: () => {
              setShowConfirmModal(false)
              handlePromoteVersion(version, true)
            }
          })
          setShowConfirmModal(true)
          setPromotingVersion(null)
          return
        }
        
        setResultModalData({
          type: 'error',
          title: 'Promotion Failed',
          message: typeof response.error === 'string' ? response.error : 'Failed to promote version'
        })
        setShowResultModal(true)
      } else {
        setResultModalData({
          type: 'success',
          title: 'Version Promoted',
          message: `Version ${version} has been promoted to production successfully${forceOverride ? ' (quality gates overridden)' : ''}`
        })
        
        // Refresh product data to get updated promoted_version
        await loadProduct()
        setShowResultModal(true)
      }
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Promotion Failed',
        message: 'Failed to promote version'
      })
      setShowResultModal(true)
    } finally {
      setPromotingVersion(null)
    }
  }

  const handleEditDataSource = (datasourceId: string) => {
    // Navigate to edit page (we'll create this)
    router.push(`/app/products/${productId}/datasources/${datasourceId}/edit`)
  }

  const handleDeleteDataSource = (datasourceId: string) => {
    setDeleteDataSourceId(datasourceId)
    setShowDeleteModal(true)
  }

  const confirmDeleteDataSource = async () => {
    if (!deleteDataSourceId) return

    try {
      const response = await apiClient.deleteDataSource(deleteDataSourceId)
      
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Delete Failed',
          message: typeof response.error === 'string' ? response.error : 'Delete failed'
        })
      } else {
        // Reload data sources to update the list
        loadDataSources()
        setResultModalData({
          type: 'success',
          title: 'Data Source Deleted',
          message: 'Data source has been successfully deleted'
        })
      }
      setShowResultModal(true)
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Delete Failed',
        message: 'Failed to delete data source'
      })
      setShowResultModal(true)
    } finally {
      setShowDeleteModal(false)
      setDeleteDataSourceId(null)
    }
  }

  const loadExports = async () => {
    if (!product) return
    
    setLoadingExports(true)
    try {
      const response = await apiClient.get(`/api/v1/exports?product_id=${product.id}`)
      if (response.data) {
        setExports(response.data)
      }
    } catch (err) {
      console.error('Failed to load exports:', err)
      setExports([])
    } finally {
      setLoadingExports(false)
    }
  }

  const handleCreateExport = async (version?: number | 'prod') => {
    if (!product) return
    
    setCreatingExport(true)
    try {
      const response = await apiClient.post(`/api/v1/exports/${product.id}/create`, {
        version: version
      })
      
      if (response.data) {
        setResultModalData({
          type: 'success',
          title: 'Export Created',
          message: 'Export bundle has been created successfully',
          details: `Bundle: ${response.data.bundle_name} (${formatFileSize(response.data.size_bytes)})`
        })
        setShowResultModal(true)
        setShowCreateExportModal(false)
        // Reload exports
        loadExports()
      }
    } catch (err) {
      console.error('Failed to create export:', err)
      setResultModalData({
        type: 'error',
        title: 'Export Failed',
        message: 'Failed to create export bundle'
      })
      setShowResultModal(true)
    } finally {
      setCreatingExport(false)
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  if (status === 'loading' || loading) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-600">Loading product...</p>
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
        {/* Enhanced Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href="/app/products" className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors font-medium">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Products
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-semibold text-gray-900">{product.name}</span>
        </div>

        {/* Enhanced Page Header */}
        <div className="mb-8 bg-white rounded-xl shadow-md border border-gray-100 p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-3 mr-4 shadow-sm">
                <Package className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">{product.name}</h1>
                <div className="flex items-center gap-3">
                  <StatusBadge status={product.status as any} />
                  <div className="flex items-center text-sm text-gray-500 bg-gray-50 px-2 py-1 rounded-md">
                    <GitBranch className="h-3 w-3 mr-1" />
                    <span>v{product.current_version}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex space-x-2">
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => router.push(`/app/products/${productId}/edit`)}
                className="border-2 hover:border-blue-300 hover:bg-blue-50"
              >
                <Settings className="h-4 w-4 mr-2" />
                Settings
              </Button>
              <Button 
                size="sm"
                onClick={() => setShowPipelineModal(true)}
                disabled={runningPipeline || dataSources.length === 0}
                className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"
              >
                <Play className="h-4 w-4 mr-2" />
                Run Pipeline
              </Button>
            </div>
          </div>
        </div>

        {/* Data Quality Banner */}
        {dataQualityViolations.length > 0 && (
          <div className="mb-6">
            <DataQualityBanner
              violations={dataQualityViolations}
              onViewDetails={() => setShowViolationsDrawer(true)}
            />
          </div>
        )}

        {/* Enhanced Tabs */}
        <div className="mb-8 border-b border-gray-200">
          <nav className="flex space-x-1 overflow-x-auto">
            <button
              onClick={() => setActiveTab('overview')}
              className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                activeTab === 'overview'
                  ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Home className="h-4 w-4" />
              Overview
            </button>
            <button
              onClick={() => setActiveTab('ai-trust-score')}
              className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                activeTab === 'ai-trust-score'
                  ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Shield className="h-4 w-4" />
              AI Trust Score
              {product?.trust_score != null && (() => {
                // Handle trust_score: can be a number in [0,1] or [0,100] range
                // Note: trust_score === 0 is valid and should be displayed
                const rawScore = Number(product.trust_score) || 0
                // Normalize: if > 1, assume it's in [0,100] format, otherwise [0,1] format
                const normalizedScore = rawScore > 1 ? rawScore / 100 : rawScore
                const displayPercentage = rawScore > 1 ? rawScore : rawScore * 100
                
                return (
                  <span className={`ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                    normalizedScore >= 0.8 ? 'bg-green-100 text-green-800' :
                    normalizedScore >= 0.6 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {displayPercentage.toFixed(0)}%
                  </span>
                )
              })()}
            </button>
            <button
              onClick={() => setActiveTab('lineage')}
              className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                activeTab === 'lineage'
                  ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              <GitBranch className="h-4 w-4" />
              Lineage
            </button>
            <button
              onClick={() => setActiveTab('chunk-metadata')}
              className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                activeTab === 'chunk-metadata'
                  ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Layers className="h-4 w-4" />
              Chunk Metadata
            </button>
            {showAccessControlAndExports && (
              <button
                onClick={() => setActiveTab('acl')}
                className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                  activeTab === 'acl'
                    ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                <Lock className="h-4 w-4" />
                Access Control
              </button>
            )}
            <button
              onClick={() => setActiveTab('datasources')}
              className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                activeTab === 'datasources'
                  ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              <Database className="h-4 w-4" />
              Data Sources
              <span className="ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-700">
                {dataSources.length}
              </span>
            </button>
            <button
              onClick={() => setActiveTab('data-quality')}
              className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                activeTab === 'data-quality'
                  ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              <FileCheck className="h-4 w-4" />
              Data Quality
              {dataQualityViolations.length > 0 && (
                <span className="ml-1 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800">
                  {dataQualityViolations.length}
                </span>
              )}
            </button>
            {showAccessControlAndExports && (
              <button
                onClick={() => setActiveTab('exports')}
                className={`flex items-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-all whitespace-nowrap ${
                  activeTab === 'exports'
                    ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                <Download className="h-4 w-4" />
                Exports
              </button>
            )}
          </nav>
        </div>

        {/* Content */}
        <div>
        {activeTab === 'ai-trust-score' && (
          <div className="space-y-6">
            <AITrustScoreDisplay productId={productId} />
          </div>
        )}

        {activeTab === 'lineage' && (
          <div className="space-y-4">
            {loadingLineage && (
              <div className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
                <TableSkeleton rows={3} cols={5} />
              </div>
            )}

            {!loadingLineage && lineageError && (
              <div className="bg-white rounded-xl shadow-md border border-red-200 p-4 text-red-700 text-sm flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  <span>{lineageError}</span>
                </div>
                <Button size="sm" variant="outline" onClick={loadLineageData}>
                  Retry
                </Button>
              </div>
            )}

            {!loadingLineage && !lineageError && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
                    <p className="text-sm text-gray-500">Chunks</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {lineageOverview?.chunk_count ?? 0}
                    </p>
                  </div>
                  <div className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
                    <p className="text-sm text-gray-500">Vectors</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {lineageOverview?.vector_count ?? 0}
                    </p>
                  </div>
                  <div className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
                    <p className="text-sm text-gray-500">DQ Findings</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {lineageOverview?.dq_failures ?? 0}
                    </p>
                  </div>
                </div>

                <div className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className="text-base font-semibold text-gray-900">Latest Run Lineage</h3>
                      <p className="text-sm text-gray-500">
                        {pipelineRuns[0]?.id
                          ? `Pipeline Run: ${pipelineRuns[0].id} (v${pipelineRuns[0].version ?? 'n/a'})`
                          : 'No pipeline runs yet'}
                      </p>
                    </div>
                    <Button size="sm" variant="outline" onClick={loadLineageData}>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Refresh
                    </Button>
                  </div>

                  {lineageRecords.length === 0 ? (
                    <div className="text-sm text-gray-500">
                      No lineage records available for this product yet.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Type</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Chunk / Vector</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Source</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Section / Field</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Page</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Model</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Status</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-700">Created</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {lineageRecords.map((record) => (
                            <tr key={record.id}>
                              <td className="px-3 py-2 capitalize text-gray-800">{record.lineage_type || 'n/a'}</td>
                              <td className="px-3 py-2 text-gray-800">
                                {record.chunk_id || record.vector_id || '—'}
                              </td>
                              <td className="px-3 py-2 text-gray-600">
                                {record.source_file || record.metadata_id || '—'}
                              </td>
                              <td className="px-3 py-2 text-gray-600">
                                {[record.section, record.field_name].filter(Boolean).join(' / ') || '—'}
                              </td>
                              <td className="px-3 py-2 text-gray-600">{record.page_start ?? record.page_end ?? '—'}</td>
                              <td className="px-3 py-2 text-gray-600">
                                {record.model_name || record.model_version ? `${record.model_name || ''} ${record.model_version || ''}`.trim() : '—'}
                              </td>
                              <td className="px-3 py-2 text-gray-600">{record.status || '—'}</td>
                              <td className="px-3 py-2 text-gray-600">
                                {record.created_at ? new Date(record.created_at).toLocaleString() : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === 'chunk-metadata' && (
          <div className="space-y-4">
            {loadingChunkMetadata && (
              <div className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
                <TableSkeleton rows={4} cols={6} />
              </div>
            )}

            {!loadingChunkMetadata && chunkMetadataError && (
              <div className="bg-white rounded-xl shadow-md border border-red-200 p-4 text-red-700 text-sm flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4" />
                  <span>{chunkMetadataError}</span>
                </div>
                <Button size="sm" variant="outline" onClick={() => loadChunkMetadata(chunkMetadataPage)}>
                  Retry
                </Button>
              </div>
            )}

            {!loadingChunkMetadata && !chunkMetadataError && (
              <div className="bg-white rounded-xl shadow-md border border-gray-100 p-4">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-gray-900">Chunk Metadata</h3>
                    <p className="text-sm text-gray-500">
                      Showing {chunkMetadata.length} item{chunkMetadata.length === 1 ? '' : 's'} (page {chunkMetadataPage + 1})
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={() => loadChunkMetadata(chunkMetadataPage)}>
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Refresh
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => loadChunkMetadata(Math.max(chunkMetadataPage - 1, 0))}
                      disabled={chunkMetadataPage === 0 || loadingChunkMetadata}
                    >
                      Prev
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => loadChunkMetadata(chunkMetadataPage + 1)}
                      disabled={!chunkMetadataHasMore || loadingChunkMetadata}
                    >
                      Next
                    </Button>
                  </div>
                </div>

                {chunkMetadata.length === 0 ? (
                  <div className="text-sm text-gray-500">
                    No chunk metadata available yet. Run the pipeline to generate chunks.
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-3 py-2 text-left font-semibold text-gray-700">Chunk ID</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-700">Source</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-700">Section / Field</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-700">Page</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-700">Score</th>
                          <th className="px-3 py-2 text-left font-semibold text-gray-700">Created</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {chunkMetadata.map((meta, idx) => (
                          <tr key={meta.chunk_id || idx}>
                            <td className="px-3 py-2 text-gray-800">{meta.chunk_id || '—'}</td>
                            <td className="px-3 py-2 text-gray-600">{meta.source_file || '—'}</td>
                            <td className="px-3 py-2 text-gray-600">
                              {[meta.section, meta.field_name].filter(Boolean).join(' / ') || '—'}
                            </td>
                            <td className="px-3 py-2 text-gray-600">{meta.page_number ?? '—'}</td>
                            <td className="px-3 py-2 text-gray-600">{meta.score != null ? meta.score.toFixed(3) : '—'}</td>
                            <td className="px-3 py-2 text-gray-600">
                              {meta.created_at ? new Date(meta.created_at as any).toLocaleString() : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {showAccessControlAndExports && activeTab === 'acl' && (
          <ComingSoonBadge
            title="Access Control"
            description="Manage user permissions and access control lists (ACLs) for this product, including read, write, and admin roles."
            icon={Lock}
          />
        )}

        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Product Information</h2>
              <dl className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
                <div>
                  <dt className="text-sm font-medium text-gray-500">Status</dt>
                  <dd className="mt-1">
                    <StatusBadge status={product.status as any} />
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500">Created</dt>
                  <dd className="mt-1 text-sm text-gray-900">
                    {new Date(product.created_at).toLocaleString()}
                  </dd>
                </div>
                {product.updated_at && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500">Last Updated</dt>
                    <dd className="mt-1 text-sm text-gray-900">
                      {new Date(product.updated_at).toLocaleString()}
                    </dd>
                  </div>
                )}
                {(() => {
                  // Get playbook_id from product or fallback to preprocessing_stats
                  const playbookId = product.playbook_id || 
                    (product.preprocessing_stats && typeof product.preprocessing_stats === 'object' &&
                     product.preprocessing_stats.playbook_id) ||
                    (product.playbook_selection && product.playbook_selection.playbook_id)
                  
                  const selection = product.playbook_selection
                  const isAutoDetected = selection?.method === 'auto_detected'
                  const detectionReason = selection?.reason
                  const isAutoDetectMode = product.playbook_id === null || product.playbook_id === undefined
                  
                  return (
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Playbook</dt>
                      <dd className="mt-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          {isAutoDetectMode && !playbookId ? (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                              Auto-Detect (Will be detected during pipeline run)
                            </span>
                          ) : playbookId ? (
                            <>
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                {playbookId}
                              </span>
                              {isAutoDetected && (
                                <span 
                                  className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800"
                                  title={detectionReason ? `Auto-detected: ${detectionReason}` : 'Auto-detected'}
                                >
                                  Auto-Detected
                                </span>
                              )}
                              {selection?.method === 'manual' && (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                                  Manual
                                </span>
                              )}
                            </>
                          ) : null}
                        </div>
                        {isAutoDetected && detectionReason && (
                          <p className="mt-1 text-xs text-gray-500">
                            Reason: {detectionReason.replace(/_/g, ' ')}
                            {selection?.confidence && ` (Confidence: ${(selection.confidence * 100).toFixed(0)}%)`}
                          </p>
                        )}
                        {isAutoDetected && selection?.files_analyzed && (
                          <p className="mt-1 text-xs text-gray-500">
                            Analyzed {selection.files_analyzed} file{selection.files_analyzed !== 1 ? 's' : ''}
                          </p>
                        )}
                        {selection?.detected_at && (
                          <p className="mt-1 text-xs text-gray-400">
                            Detected: {new Date(selection.detected_at).toLocaleString()}
                          </p>
                        )}
                      </dd>
                    </div>
                  )
                })()}
                {product?.trust_score != null && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500">AI Trust Score</dt>
                    <dd className="mt-1">
                      {(() => {
                        // Handle trust_score: can be a number in [0,1] or [0,100] range
                        // Note: trust_score === 0 is valid and should be displayed
                        const rawScore = Number(product.trust_score) || 0
                        // Normalize: if > 1, assume it's in [0,100] format, otherwise [0,1] format
                        const normalizedScore = rawScore > 1 ? rawScore / 100 : rawScore
                        const displayPercentage = rawScore > 1 ? rawScore : rawScore * 100
                        
                        return (
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            normalizedScore >= 0.8 ? 'bg-green-100 text-green-800' :
                            normalizedScore >= 0.6 ? 'bg-yellow-100 text-yellow-800' :
                            'bg-red-100 text-red-800'
                          }`}>
                            {displayPercentage.toFixed(1)}%
                          </span>
                        )
                      })()}
                    </dd>
                  </div>
                )}
                {product.policy_status && product.policy_status !== 'unknown' && (
                  <div>
                    <dt className="text-sm font-medium text-gray-500">Policy Status</dt>
                    <dd className="mt-1">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        product.policy_status === 'passed' ? 'bg-green-100 text-green-800' :
                        product.policy_status === 'failed' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                      }`}>
                        {product.policy_status}
                      </span>
                    </dd>
                  </div>
                )}
                {/* Chunking Configuration */}
                {(() => {
                  const chunkingConfig = (product as any)?.chunking_config;
                  if (!chunkingConfig) return null;

                  const mode = chunkingConfig.mode || "auto";

                  const manual = chunkingConfig.manual_settings;
                  const resolved = chunkingConfig.resolved_settings;
                  const auto = chunkingConfig.auto_settings;

                  // Effective settings = what pipeline should use
                  const effective =
                    mode === "manual"
                      ? (manual ?? resolved ?? auto)
                      : (resolved ?? auto ?? manual);

                  if (!effective) return null;

                  // Units (prefer explicit if present)
                  const units =
                    effective.units ||
                    (mode === "manual" ? "characters" : "tokens");

                  const contentType =
                    effective.content_type || auto?.content_type || "general";

                  const usingManual = mode === "manual" && !!manual;

                  return (
                    <div>
                      <dt className="text-sm font-medium text-gray-500">
                        Chunking Configuration
                      </dt>

                      <dd className="mt-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800 capitalize">
                            {contentType}
                          </span>

                          {usingManual ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                              Manual (Effective)
                            </span>
                          ) : resolved ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                              Auto-Detected (Effective)
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                              Auto (Pending Detection)
                            </span>
                          )}
                        </div>

                        <div className="mt-2 text-xs text-gray-600 space-y-1">
                          <p>
                            Chunk Size: {effective.chunk_size ?? "N/A"} {units}
                          </p>
                          <p>
                            Chunk Overlap: {effective.chunk_overlap ?? "N/A"} {units}
                          </p>
                          <p>Strategy: {effective.chunking_strategy ?? "N/A"}</p>

                          {effective.confidence != null && (
                            <p>Confidence: {(effective.confidence * 100).toFixed(0)}%</p>
                          )}

                          {usingManual && (
                            <p className="mt-1 text-xs text-gray-500 italic">
                              Using manual settings (overrides playbook defaults)
                            </p>
                          )}
                        </div>

                        {/* Show auto-analysis metadata ONLY if it's relevant */}
                        {!usingManual && chunkingConfig.last_analyzed && (
                          <p className="mt-1 text-xs text-gray-400">
                            Last analyzed: {new Date(chunkingConfig.last_analyzed).toLocaleString()}
                          </p>
                        )}

                        {!usingManual &&
                          Array.isArray(chunkingConfig.sample_files_analyzed) &&
                          chunkingConfig.sample_files_analyzed.length > 0 && (
                            <p className="mt-1 text-xs text-gray-400">
                              Analyzed {chunkingConfig.sample_files_analyzed.length} sample file
                              {chunkingConfig.sample_files_analyzed.length !== 1 ? "s" : ""}
                            </p>
                          )}

                        {/* Optional: show detected config as "not used" when manual */}
                        {usingManual && resolved && (
                          <details className="mt-2 text-xs text-gray-500">
                            <summary className="cursor-pointer">
                              Auto-detected suggestion (not used)
                            </summary>
                            <div className="mt-1 space-y-1">
                              <p>Chunk Size: {resolved.chunk_size ?? "N/A"} {resolved.units ?? "tokens"}</p>
                              <p>Chunk Overlap: {resolved.chunk_overlap ?? "N/A"} {resolved.units ?? "tokens"}</p>
                              <p>Strategy: {resolved.chunking_strategy ?? "N/A"}</p>
                              {resolved.confidence != null && (
                                <p>Confidence: {(resolved.confidence * 100).toFixed(0)}%</p>
                              )}
                              {chunkingConfig.last_analyzed && (
                                <p>
                                  Auto-detection last analyzed:{" "}
                                  {new Date(chunkingConfig.last_analyzed).toLocaleString()}
                                </p>
                              )}
                            </div>
                          </details>
                        )}
                      </dd>
                    </div>
                  );
                })()}
                {/* Chunking Strategy from latest successful pipeline run */}
                {(() => {
                  const chunkingStrategy = (product as any).chunking_strategy
                  
                  if (!chunkingStrategy) return null
                  
                  // Format the strategy name (replace underscores with spaces and capitalize)
                  const formattedStrategy = chunkingStrategy
                    .replace(/_/g, ' ')
                    .split(' ')
                    .map((word: string) => word.charAt(0).toUpperCase() + word.slice(1))
                    .join(' ')
                  
                  return (
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Chunking Strategy</dt>
                      <dd className="mt-1">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                          {formattedStrategy}
                        </span>
                      </dd>
                    </div>
                  )
                })()}
                {/* Embedding Model from embedding config */}
                {(() => {
                  const embeddingConfig = (product as any).embedding_config
                  const modelName = embeddingConfig?.embedder_name
                  
                  if (!modelName) return null
                  
                  return (
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Embedding Model</dt>
                      <dd className="mt-1">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                          {modelName}
                        </span>
                        {embeddingConfig?.embedding_dimension && (
                          <span className="ml-2 text-xs text-gray-500">
                            ({embeddingConfig.embedding_dimension}D)
                          </span>
                        )}
                      </dd>
                    </div>
                  )
                })()}
              </dl>
            </div>

            {/* Preprocessing Stats Section (M1) */}
            {product.preprocessing_stats && (
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Preprocessing Statistics</h2>
                <dl className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-3">
                  {product.preprocessing_stats.sections !== undefined && (
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Sections Detected</dt>
                      <dd className="mt-1 text-2xl font-semibold text-gray-900">
                        {product.preprocessing_stats.sections}
                      </dd>
                    </div>
                  )}
                  {product.preprocessing_stats.chunks !== undefined && (
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Chunks Created</dt>
                      <dd className="mt-1 text-2xl font-semibold text-gray-900">
                        {product.preprocessing_stats.chunks}
                      </dd>
                    </div>
                  )}
                  {product.preprocessing_stats.mid_sentence_boundary_rate !== undefined && (
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Mid-Sentence Boundary Rate</dt>
                      <dd className="mt-1 text-2xl font-semibold text-gray-900">
                        {(product.preprocessing_stats.mid_sentence_boundary_rate * 100).toFixed(1)}%
                      </dd>
                      <p className="mt-1 text-xs text-gray-500">
                        Lower is better (indicates better chunking)
                      </p>
                    </div>
                  )}
                </dl>
              </div>
            )}

            {/* MLflow Metrics Section removed - MLflow integration disabled */}

            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                <Link href={`/app/products/${product.id}/datasources/new`}>
                  <div className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 cursor-pointer h-full flex flex-col">
                    <Database className="h-8 w-8 text-blue-600 mb-2" />
                    <h3 className="font-medium text-gray-900">Add Data Source</h3>
                    <p className="text-sm text-gray-600">Connect a new data source to this product</p>
                  </div>
                </Link>
                {(product.vector_creation_enabled !== false) && (
                  <Link href={`/app/products/${productId}/playground`}>
                    <div className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 cursor-pointer h-full flex flex-col">
                      <Search className="h-8 w-8 text-purple-600 mb-2" />
                      <h3 className="font-medium text-gray-900">Playground</h3>
                      <p className="text-sm text-gray-600">Search and explore your indexed data</p>
                    </div>
                  </Link>
                )}
                {(product.vector_creation_enabled !== false) && (
                  <Link href={`/app/products/${productId}/rag-quality`}>
                    <div className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 cursor-pointer h-full flex flex-col">
                      <BarChart3 className="h-8 w-8 text-emerald-600 mb-2" />
                      <h3 className="font-medium text-gray-900">Retrieval Evaluation</h3>
                      <p className="text-sm text-gray-600">Evaluate retrieval system performance and quality metrics</p>
                    </div>
                  </Link>
                )}
                <Link href={`/app/products/${productId}/pipeline-runs`}>
                  <div className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 cursor-pointer h-full flex flex-col">
                    <GitBranch className="h-8 w-8 text-indigo-600 mb-2" />
                    <h3 className="font-medium text-gray-900">Pipeline Runs</h3>
                    <p className="text-sm text-gray-600">Monitor and manage data processing pipeline executions</p>
                  </div>
                </Link>
              </div>
            </div>


            {/* Pipeline Section */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Pipeline</h2>
              </div>
              
              {dataSources.length === 0 ? (
                <div className="text-center py-8">
                  <Database className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">No data sources</h3>
                  <p className="text-gray-600">Add data sources before running the pipeline.</p>
                </div>
              ) : (
                <div className="space-y-6">
                  <p className="text-sm text-gray-600">
                    Run the complete data processing pipeline to ingest, clean, score with AI-Ready metrics, generate fingerprint, chunk, embed, and index your data.
                  </p>
                  
                  {/* Recent Runs Table */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-md font-medium text-gray-900 flex items-center gap-2">
                        <GitBranch className="h-4 w-4 text-blue-600" />
                        Recent Runs
                      </h3>
                      <Link href={`/app/products/${productId}/pipeline-runs`}>
                        <Button variant="outline" size="sm">
                          View All
                        </Button>
                      </Link>
                    </div>
                    {loadingPipelineRuns ? (
                      <TableSkeleton rows={3} cols={5} />
                    ) : pipelineRuns.length === 0 ? (
                      <div className="text-center py-8">
                        <Package className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                        <p className="text-gray-500 mb-4">No pipeline runs yet</p>
                        {dataSources.length === 0 ? (
                          <p className="text-sm text-gray-400">Add data sources before running the pipeline.</p>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => setShowPipelineModal(true)}
                            disabled={runningPipeline}
                            className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"
                          >
                            <Play className="h-4 w-4 mr-2" />
                            Run First Pipeline
                          </Button>
                        )}
                      </div>
                    ) : (
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
                            {pipelineRuns.map((run) => (
                              <tr key={run.id} className="hover:bg-blue-50/50 transition-colors">
                                <td className="px-6 py-4 whitespace-nowrap">
                                  <div className="flex items-center space-x-2">
                                    <span className="text-sm font-semibold text-gray-900">v{run.version}</span>
                                    {product?.promoted_version === run.version && (
                                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gradient-to-r from-purple-500 to-pink-600 text-white shadow-sm">
                                        🚀 PROD
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                  <StatusBadge status={run.status as any} size="sm" />
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                  {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                  {run.started_at && run.finished_at ? 
                                    `${Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s` :
                                    run.started_at ? 'Running...' : '-'
                                  }
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                  <div className="flex items-center gap-1">
                                    <Link href={`/app/products/${productId}/pipeline-runs`}>
                                      <Button 
                                        variant="ghost" 
                                        size="sm" 
                                        className="h-8 w-8 p-0"
                                        title="View Details"
                                      >
                                        <Eye className="h-4 w-4" />
                                      </Button>
                                    </Link>
                                    {run.status === 'succeeded' && (
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className={`h-8 w-8 p-0 ${
                                          product?.promoted_version === run.version
                                            ? 'text-green-600 hover:text-green-700 hover:bg-green-50'
                                            : ''
                                        }`}
                                        onClick={() => handlePromoteVersion(run.version)}
                                        disabled={promotingVersion === run.version || product?.promoted_version === run.version}
                                        title={
                                          product?.promoted_version === run.version
                                            ? 'Already Promoted'
                                            : promotingVersion === run.version
                                            ? 'Promoting...'
                                            : 'Promote to Production'
                                        }
                                      >
                                        {promotingVersion === run.version ? (
                                          <Loader2 className="h-4 w-4 animate-spin" />
                                        ) : product?.promoted_version === run.version ? (
                                          <CheckCircle2 className="h-4 w-4" />
                                        ) : (
                                          <Rocket className="h-4 w-4" />
                                        )}
                                      </Button>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {/* No pagination - only show recent 5 runs */}
                      </div>
                    )}
                  </div>

                  {/* Artifacts Section */}
                  {((product.current_version > 0 || product.promoted_version) && (pipelineArtifacts.length > 0 || pipelineRuns.length > 0)) && (() => {
                    // Determine which version to show
                    const artifactsVersion = product.promoted_version || product.current_version
                    const isProductionVersion = product.promoted_version !== null && product.promoted_version === artifactsVersion
                    
                    return (
                      <div>
                        <SectionHeader
                          title="Artifacts"
                          icon={Package}
                          subtitle={pipelineArtifacts.length > 0 ? `Version ${artifactsVersion}` : undefined}
                          status={pipelineArtifacts.length > 0 ? {
                            label: isProductionVersion ? 'Production' : 'Latest Version',
                            color: isProductionVersion ? 'green' : 'blue',
                          } : undefined}
                          tooltip={
                            <>
                              <p className="font-semibold mb-1.5 text-gray-900">About These Artifacts</p>
                              <p className="text-gray-600 mb-2">
                                {pipelineArtifacts.length > 0 ? (
                                  isProductionVersion 
                                    ? `These artifacts are from version ${artifactsVersion}, which is the current production version.`
                                    : `These artifacts are from version ${artifactsVersion} (latest version). ${product.promoted_version ? `Production version is ${product.promoted_version}.` : 'No version has been promoted to production yet.'}`
                                ) : (
                                  'No artifacts are available yet. Artifacts will appear here after pipeline execution.'
                                )}
                              </p>
                              {pipelineArtifacts.length > 0 && (
                                <p className="text-gray-600">
                                  Each pipeline execution generates new artifacts. To view artifacts from specific pipeline runs, 
                                  visit the <span className="font-medium">Pipeline Runs</span> page.
                                </p>
                              )}
                            </>
                          }
                        />
                      {loadingData.artifacts ? (
                        <div className="flex items-center justify-center py-12">
                          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                        </div>
                      ) : pipelineArtifacts.length === 0 ? (
                        <div className="text-center py-8">
                          <Package className="h-10 w-10 text-gray-400 mx-auto mb-3" />
                          <p className="text-gray-600">No artifacts available for this version</p>
                          <p className="text-sm text-gray-500 mt-2">Artifacts will appear here after pipeline execution</p>
                        </div>
                      ) : (
                        <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
                          <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gradient-to-r from-gray-50 to-blue-50">
                              <tr>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                                  Artifact Name
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                                  Type
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                                  Size
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                                  Actions
                                </th>
                              </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                              {pipelineArtifacts.map((artifact: any, index: number) => {
                                const formatFileSize = (bytes: number) => {
                                  if (bytes < 1024) return `${bytes} B`
                                  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
                                  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
                                  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
                                }

                                const getArtifactIcon = (type: string) => {
                                  switch (type?.toLowerCase()) {
                                    case 'json':
                                    case 'jsonl':
                                      return <FileJson className="h-4 w-4 text-yellow-600" />
                                    case 'csv':
                                      return <FileSpreadsheet className="h-4 w-4 text-green-600" />
                                    case 'pdf':
                                      return <FileText className="h-4 w-4 text-red-600" />
                                    case 'vector':
                                      return <Layers className="h-4 w-4 text-purple-600" />
                                    default:
                                      return <FileText className="h-4 w-4 text-gray-600" />
                                  }
                                }

                                return (
                                  <tr key={artifact.id || index} className="hover:bg-blue-50/50 transition-colors">
                                    <td className="px-6 py-4 whitespace-nowrap">
                                      <div className="flex items-center gap-2">
                                        {getArtifactIcon(artifact.artifact_type)}
                                        <span className="text-sm font-medium text-gray-900">
                                          {artifact.display_name || artifact.artifact_name?.replace(/_/g, ' ') || 'Unknown Artifact'}
                                        </span>
                                      </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                      <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
                                        {artifact.artifact_type?.toUpperCase() || 'UNKNOWN'}
                                      </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                      <span className="text-sm text-gray-600">
                                        {artifact.file_size ? formatFileSize(artifact.file_size) : 'N/A'}
                                      </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                      <div className="flex items-center gap-2">
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          onClick={() => handleViewArtifact(artifact)}
                                          className="p-2"
                                          title="View artifact"
                                        >
                                          <Eye className="h-4 w-4" />
                                        </Button>
                                        {artifact.download_url && (
                                          <button
                                            onClick={() => {
                                              // For GCS signed URLs, use direct download (skip fetch to avoid CORS issues)
                                              if (artifact.download_url.includes('storage.googleapis.com') || 
                                                  artifact.download_url.includes('X-Goog-Signature')) {
                                                const a = document.createElement('a')
                                                a.href = artifact.download_url
                                                a.download = artifact.display_name || artifact.artifact_name || 'artifact'
                                                a.target = '_blank'
                                                a.style.display = 'none'
                                                document.body.appendChild(a)
                                                a.click()
                                                document.body.removeChild(a)
                                                return
                                              }
                                              
                                              // For non-GCS URLs, use fetch approach
                                              fetch(artifact.download_url)
                                                .then(response => {
                                                  if (!response.ok) throw new Error('Download failed')
                                                  return response.blob()
                                                })
                                                .then(blob => {
                                                  const url = window.URL.createObjectURL(blob)
                                                  const a = document.createElement('a')
                                                  a.href = url
                                                  a.download = artifact.display_name || artifact.artifact_name || 'artifact'
                                                  a.style.display = 'none'
                                                  document.body.appendChild(a)
                                                  a.click()
                                                  window.URL.revokeObjectURL(url)
                                                  document.body.removeChild(a)
                                                })
                                                .catch(err => {
                                                  console.error('Download failed:', err)
                                                  // Fallback: try direct link
                                                  const a = document.createElement('a')
                                                  a.href = artifact.download_url
                                                  a.download = artifact.display_name || artifact.artifact_name || 'artifact'
                                                  a.target = '_blank'
                                                  a.style.display = 'none'
                                                  document.body.appendChild(a)
                                                  a.click()
                                                  document.body.removeChild(a)
                                                })
                                            }}
                                            className="inline-flex items-center justify-center p-2 text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                                            title="Download artifact"
                                          >
                                            <Download className="h-4 w-4" />
                                          </button>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                      </div>
                    )
                  })()}
                </div>
              )}
            </div>

          </div>
        )}

        {activeTab === 'datasources' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold text-gray-900">Data Sources</h2>
              <Link href={`/app/products/${product.id}/datasources/new`}>
                <Button>
                  <Database className="h-4 w-4 mr-2" />
                  Add Data Source
                </Button>
              </Link>
            </div>

            {dataSources.length === 0 ? (
              <div className="text-center py-12 bg-white rounded-xl shadow-md border border-gray-100">
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-4">
                  <Database className="h-10 w-10 text-blue-600" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">No data sources yet</h3>
                <p className="text-gray-600 mb-6">Connect your first data source to get started.</p>
                <Link href={`/app/products/${product.id}/datasources/new`}>
                  <Button className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg">
                    <Database className="h-4 w-4 mr-2" />
                    Add Data Source
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {dataSources.map((datasource) => {
                  const displayInfo = getDataSourceDisplayInfo(datasource)
                  return (
                    <div key={datasource.id} className="bg-white rounded-xl shadow-md border-2 border-gray-100 p-6 hover:shadow-lg hover:border-blue-300 transition-all duration-200 group">
                      <div className="flex items-start mb-4">
                        <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-2.5 mr-3 flex-shrink-0 shadow-sm group-hover:scale-110 transition-transform">
                          <span className="text-xl">{getDataSourceTypeIcon(datasource.type)}</span>
                        </div>
                        <div className="min-w-0 flex-1">
                          <h3 className="font-semibold text-gray-900 text-sm mb-1 group-hover:text-blue-600 transition-colors">{displayInfo.title}</h3>
                          <p className="text-xs text-gray-600 truncate mb-1" title={displayInfo.fullSubtitle}>
                            {displayInfo.subtitle}
                          </p>
                          <p className="text-xs text-gray-500 truncate" title={displayInfo.details}>
                            {displayInfo.details}
                          </p>
                        </div>
                      </div>
                      
                      <div className="mb-4 pb-4 border-b border-gray-100">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-xs text-gray-500">
                            Created {new Date(datasource.created_at).toLocaleDateString()}
                          </p>
                          <div className="flex items-center bg-green-50 px-2 py-1 rounded-md border border-green-200">
                            <div className="w-2 h-2 bg-green-500 rounded-full mr-1.5 animate-pulse"></div>
                            <span className="text-xs font-medium text-green-700">Active</span>
                          </div>
                        </div>
                        {datasource.last_cursor && (
                          <p className="text-xs text-blue-600">
                            Last sync: {new Date(datasource.last_cursor.timestamp || datasource.updated_at).toLocaleDateString()}
                          </p>
                        )}
                      </div>
                      
                      <div className="space-y-2">
                        <div className="flex space-x-2">
                          <Button 
                            variant="outline" 
                            size="sm" 
                            className="flex-1 text-xs border-2 hover:border-blue-300 hover:bg-blue-50"
                            onClick={() => handleEditDataSource(datasource.id)}
                          >
                            Edit
                          </Button>
                          <Button 
                            size="sm" 
                            className="flex-1 text-xs bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-sm hover:shadow-md"
                            onClick={() => handleTestConnection(datasource.id)}
                            disabled={testingConnection === datasource.id}
                          >
                            {testingConnection === datasource.id ? (
                              <>
                                <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-white mr-1"></div>
                                Testing...
                              </>
                            ) : (
                              'Test'
                            )}
                          </Button>
                          <Button 
                            variant="outline" 
                            size="sm" 
                            className="flex-1 text-xs text-red-600 border-2 border-red-300 hover:bg-red-50 hover:border-red-400"
                            onClick={() => handleDeleteDataSource(datasource.id)}
                          >
                            Delete
                          </Button>
                        </div>
                        
                        {/* Only show "Run Initial Ingest" for datasource types that need it (not folder/local) */}
                        {datasource.type !== 'folder' && (
                        <div className="mt-3">
                          <Button
                            variant="outline"
                            size="default"
                            className="w-full border-green-500 text-green-600 hover:bg-green-50 hover:border-green-600 hover:text-green-700 font-medium shadow-sm transition-all duration-200 hover:shadow-md"
                            onClick={() => handleIngestDataSource(datasource.id)}
                            disabled={ingestingDataSource === datasource.id}
                          >
                            {ingestingDataSource === datasource.id ? (
                              <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin text-green-600" />
                                <span className="text-green-600">Ingesting Data...</span>
                              </>
                            ) : (
                              <>
                                <ArrowDownToLine className="mr-2 h-4 w-4 text-green-600" />
                                <span className="text-green-600">Run Initial Ingest</span>
                              </>
                            )}
                          </Button>
                          
                          {ingestionResults[datasource.id] && (
                            <div className="mt-2 flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
                              <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
                              <span className="font-medium">
                                Successfully ingested {ingestionResults[datasource.id].files} file{ingestionResults[datasource.id].files !== 1 ? 's' : ''}
                              </span>
                              <span className="text-green-600">
                                ({(ingestionResults[datasource.id].bytes / 1024 / 1024).toFixed(2)} MB)
                              </span>
                              {ingestionResults[datasource.id].errors > 0 && (
                                <span className="text-orange-600 font-medium">
                                  • {ingestionResults[datasource.id].errors} error{ingestionResults[datasource.id].errors !== 1 ? 's' : ''}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        )}
                        
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}
        </div>

      {/* Modals */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false)
          setDeleteDataSourceId(null)
        }}
        onConfirm={confirmDeleteDataSource}
        title="Delete Data Source"
        message="Are you sure you want to delete this data source? This action cannot be undone."
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

      {showConfirmModal && confirmModalData && (
        <ConfirmModal
          isOpen={showConfirmModal}
          onClose={() => {
            setShowConfirmModal(false)
            setConfirmModalData(null)
          }}
          onConfirm={confirmModalData.onConfirm}
          title={confirmModalData.title}
          message={confirmModalData.message}
          confirmText="Promote Anyway"
          cancelText="Cancel"
          variant="warning"
        />
      )}

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
                  disabled={runningPipeline}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => handleRunPipeline()}
                  disabled={runningPipeline}
                  className="bg-blue-600 hover:bg-blue-700 text-white"
                >
                  {runningPipeline ? (
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

      {/* Pipeline Conflict Modal */}
      {pipelineConflict && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Pipeline Conflict</h3>
              <div className="mb-4">
                <p className="text-sm text-gray-600 mb-3">
                  {typeof pipelineConflict.message === 'string' ? pipelineConflict.message : 'A pipeline conflict occurred'}
                </p>
                <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3 mb-4">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                      </svg>
                    </div>
                    <div className="ml-3">
                      <h3 className="text-sm font-medium text-yellow-800">
                        Existing Pipeline Run
                      </h3>
                      <div className="mt-2 text-sm text-yellow-700">
                        <p><strong>Status:</strong> {pipelineConflict.existing_status || 'Unknown'}</p>
                        <p><strong>Started:</strong> {pipelineConflict.existing_started_at ? new Date(pipelineConflict.existing_started_at).toLocaleString() : 'Unknown'}</p>
                        <p><strong>Run ID:</strong> {pipelineConflict.existing_run_id || 'Unknown'}</p>
                      </div>
                    </div>
                  </div>
                </div>
                <p className="text-sm text-gray-600">
                  {typeof pipelineConflict.suggestion === 'string' ? pipelineConflict.suggestion : 'Please wait for the current run to complete or use force run to override.'}
                </p>
              </div>
              <div className="flex justify-end space-x-3">
                <Button
                  variant="outline"
                  onClick={() => setPipelineConflict(null)}
                  disabled={runningPipeline}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => {
                    setPipelineConflict(null)
                    handleRunPipeline(undefined, true)
                  }}
                  disabled={runningPipeline}
                  className="bg-orange-600 hover:bg-orange-700 text-white"
                >
                  {runningPipeline ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Starting...
                    </>
                  ) : (
                    'Force Run (Override)'
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
        )}

        {activeTab === 'data-quality' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold text-gray-900">Data Quality</h2>
              <div className="flex space-x-2">
                <Button
                  variant="outline"
                  onClick={() => setShowRulesEditor(true)}
                >
                  <Settings className="h-4 w-4 mr-2" />
                  Manage Rules
                </Button>
                {dataQualityViolations.length > 0 && (
                  <Button
                    variant="outline"
                    onClick={() => setShowViolationsDrawer(true)}
                  >
                    <AlertTriangle className="h-4 w-4 mr-2" />
                    View Violations ({dataQualityViolations.length})
                  </Button>
                )}
              </div>
            </div>

            {dataQualityViolations.length === 0 ? (
              <div className="text-center py-12">
                <AlertTriangle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No Quality Issues</h3>
                <p className="text-gray-600 mb-4">
                  Great! No data quality violations were detected in the latest pipeline run.
                </p>
                <Button
                  variant="outline"
                  onClick={() => setShowRulesEditor(true)}
                >
                  <Settings className="h-4 w-4 mr-2" />
                  Configure Quality Rules
                </Button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <h3 className="text-lg font-medium text-gray-900 mb-4">Quality Summary</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-red-600">
                        {dataQualityViolations.filter(v => v.severity === 'error').length}
                      </div>
                      <div className="text-sm text-gray-600">Errors</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-orange-600">
                        {dataQualityViolations.filter(v => v.severity === 'warning').length}
                      </div>
                      <div className="text-sm text-gray-600">Warnings</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-600">
                        {dataQualityViolations.filter(v => v.severity === 'info').length}
                      </div>
                      <div className="text-sm text-gray-600">Info</div>
                    </div>
                  </div>
                </div>

                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <h3 className="text-lg font-medium text-gray-900 mb-4">Recent Violations</h3>
                  <div className="space-y-3">
                    {dataQualityViolations.slice(0, 5).map((violation) => (
                      <div key={violation.id} className="flex items-center justify-between p-3 border rounded-lg">
                        <div className="flex items-center space-x-3">
                          <AlertTriangle className={`h-5 w-5 ${
                            violation.severity === 'error' ? 'text-red-600' :
                            violation.severity === 'warning' ? 'text-orange-600' : 'text-blue-600'
                          }`} />
                          <div>
                            <div className="font-medium text-gray-900">{violation.rule_name}</div>
                            <div className="text-sm text-gray-600">{violation.message}</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                            violation.severity === 'error' ? 'bg-red-100 text-red-800' :
                            violation.severity === 'warning' ? 'bg-orange-100 text-orange-800' : 'bg-blue-100 text-blue-800'
                          }`}>
                            {violation.severity}
                          </span>
                          <div className="text-xs text-gray-500 mt-1">
                            {violation.affected_count} of {violation.total_count}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  {dataQualityViolations.length > 5 && (
                    <div className="text-center mt-4">
                      <Button
                        variant="outline"
                        onClick={() => setShowViolationsDrawer(true)}
                      >
                        View All {dataQualityViolations.length} Violations
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {showAccessControlAndExports && activeTab === 'exports' && (
          <ComingSoonBadge
            title="Exports"
            description="Create and download export bundles containing processed data, embeddings, and metadata for offline use or backup."
            icon={Download}
          />
        )}
      </div>

      {/* Data Quality Components */}
      <DataQualityViolationsDrawer
        isOpen={showViolationsDrawer}
        onClose={() => setShowViolationsDrawer(false)}
        violations={dataQualityViolations}
        productId={productId}
        version={product?.current_version}
      />

      <DataQualityRulesEditor
        isOpen={showRulesEditor}
        onClose={() => setShowRulesEditor(false)}
        onSave={handleSaveDataQualityRules}
        initialRules={existingRules}
        productId={productId}
      />

      {/* Create Export Modal */}
      {showCreateExportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div className="p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Create Export Bundle</h3>
              <p className="text-sm text-gray-600 mb-6">
                Choose which version to export. The bundle will include chunked data, embeddings, and provenance information.
              </p>
              
              <div className="space-y-4">
                <div className="flex items-center space-x-3">
                  <input
                    type="radio"
                    id="current-version"
                    name="export-version"
                    value="current"
                    defaultChecked
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                  />
                  <label htmlFor="current-version" className="text-sm font-medium text-gray-700">
                    Current Version (v{product?.current_version})
                  </label>
                </div>
                
                {product?.promoted_version && product.promoted_version !== product.current_version && (
                  <div className="flex items-center space-x-3">
                    <input
                      type="radio"
                      id="promoted-version"
                      name="export-version"
                      value="prod"
                      className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                    />
                    <label htmlFor="promoted-version" className="text-sm font-medium text-gray-700">
                      Promoted Version (v{product.promoted_version})
                    </label>
                  </div>
                )}
              </div>
              
              <div className="flex justify-end space-x-3 mt-6">
                <Button
                  variant="outline"
                  onClick={() => setShowCreateExportModal(false)}
                  disabled={creatingExport}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => {
                    const selectedInput = document.querySelector('input[name="export-version"]:checked') as HTMLInputElement | null
                    const selectedVersion = selectedInput?.value
                    if (selectedVersion === 'prod') {
                      handleCreateExport('prod')
                    } else {
                      handleCreateExport()
                    }
                  }}
                  disabled={creatingExport}
                >
                  {creatingExport ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Creating...
                    </>
                  ) : (
                    <>
                      <Package className="h-4 w-4 mr-2" />
                      Create Export
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Pipeline Details Modal */}
      {selectedRunForDetails && (
        <PipelineDetailsModal
          isOpen={!!selectedRunForDetails}
          onClose={() => setSelectedRunForDetails(null)}
          runId={selectedRunForDetails.id}
          runVersion={selectedRunForDetails.version}
          runStatus={selectedRunForDetails.status}
          initialMetrics={selectedRunForDetails.metrics}
          onPipelineCancelled={async () => {
            // Refresh pipeline runs list
            const runs = await loadPipelineRuns()
            // Optionally refresh artifacts too
            loadPipelineArtifacts(runs)
          }}
        />
      )}

      {/* Artifact Viewer Modal */}
      {viewingArtifact && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onClick={() => setViewingArtifact(null)} />

            <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
              {/* Header */}
              <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex items-center justify-between">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-white">
                    {viewingArtifact.display_name || viewingArtifact.artifact_name?.replace(/_/g, ' ') || 'Unknown Artifact'}
                  </h3>
                  <div className="flex items-center gap-3 mt-1">
                    <p className="text-sm text-blue-100">
                      {viewingArtifact.artifact_type?.toUpperCase() || 'UNKNOWN'} • {(() => {
                        const formatFileSize = (bytes: number) => {
                          if (bytes < 1024) return `${bytes} B`
                          if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
                          return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
                        }
                        return formatFileSize(viewingArtifact.file_size || 0)
                      })()}
                    </p>
                    {viewingArtifact.stage_name && (
                      <span className="text-xs text-blue-200 bg-blue-700/30 px-2 py-1 rounded">
                        Stage: {viewingArtifact.stage_name.replace(/_/g, ' ')}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => setViewingArtifact(null)}
                  className="text-white hover:text-gray-200 transition-colors ml-4"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Content */}
              <div className="px-6 py-4 max-h-[70vh] overflow-y-auto">
                {loadingArtifactContent ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                    <p className="ml-3 text-gray-600">Loading artifact content...</p>
                  </div>
                ) : artifactContent ? (
                  <div className="bg-gray-900 rounded-lg p-4">
                    <pre className="text-xs font-mono text-gray-100 whitespace-pre-wrap overflow-x-auto">
                      {artifactContent}
                    </pre>
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    <p>Unable to load artifact content</p>
                    {viewingArtifact.download_url && (
                      <p className="text-sm mt-2">You can download the artifact using the download button below.</p>
                    )}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="bg-gray-50 px-6 py-3 flex justify-end">
                <button
                  onClick={() => setViewingArtifact(null)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  )
}
