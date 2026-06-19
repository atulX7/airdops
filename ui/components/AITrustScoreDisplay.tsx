'use client'

import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, AlertTriangle, Loader2, AlertCircle, Lightbulb, BookOpen, TrendingUp, Sparkles, Shield, FileText, Layers, Database, Search, ChevronDown, ChevronUp, Info } from 'lucide-react'
import { apiClient, ProductInsightsResponse } from '@/lib/api-client'
import { useToast } from './ui/toast'
import { Button } from '@/components/ui/button'

interface AITrustScoreDisplayProps {
  productId: string
  showTitle?: boolean
}

const METRIC_NAMES: Record<string, string> = {
  // Canonical snake_case metrics
  ai_trust_score: 'AI Trust Score',
  completeness: 'Completeness',
  validity: 'Validity',
  consistency: 'Consistency',
  uniqueness: 'Uniqueness',
  timeliness: 'Timeliness',
  text_integrity: 'Text Integrity',
  parse_success: 'Parse Success',
  chunk_boundary_quality: 'Chunk Boundary Quality',
  chunk_coherence: 'Chunk Coherence',
  chunk_size_health: 'Chunk Size Health',
  metadata_completeness: 'Metadata Completeness',
  provenance_coverage: 'Provenance Coverage',
  duplicate_ratio: 'Duplicate Ratio',
  // Raw token metrics
  total_tokens: 'Total Tokens',
  avg_tokens_per_chunk: 'Avg Tokens per Chunk',
  num_chunks: 'Number of Chunks',
  min_tokens: 'Min Tokens',
  max_tokens: 'Max Tokens',
  p95_tokens_per_chunk: 'P95 Tokens per Chunk',
  token_est: 'Token Estimate',
  // Legacy metrics (for backward compatibility)
  AI_Trust_Score: 'AI Trust Score',
  Completeness: 'Completeness',
  Accuracy: 'Accuracy',
  Secure: 'Security',
  Quality: 'Quality',
  Timeliness: 'Timeliness',
  Token_Count: 'Token Count',
  GPT_Confidence: 'GPT Confidence',
  Context_Quality: 'Context Quality',
  Metadata_Presence: 'Metadata Presence',
  Audience_Intentionality: 'Audience Intentionality',
  Diversity: 'Diversity',
  Audience_Accessibility: 'Audience Accessibility',
  KnowledgeBase_Ready: 'Knowledge Base Ready',
  // AI-Ready metrics (legacy)
  Chunk_Coherence: 'Chunk Coherence',
  Noise_Free_Score: 'Noise-Free Score',
  Chunk_Boundary_Quality: 'Chunk Boundary Quality',
  // Vector metrics
  Embedding_Dimension_Consistency: 'Embedding Dimension Consistency',
  Embedding_Success_Rate: 'Embedding Success Rate',
  Vector_Quality_Score: 'Vector Quality Score',
  Embedding_Model_Health: 'Embedding Model Health',
  Semantic_Search_Readiness: 'Semantic Search Readiness',
  // RAG metrics
  Retrieval_Recall_At_K: 'Retrieval Recall@K',
  Average_Precision_At_K: 'Average Precision@K',
}

const METRIC_DESCRIPTIONS: Record<string, string> = {
  // Canonical snake_case metrics
  ai_trust_score: 'Overall AI readiness score (weighted sum of all metrics)',
  completeness: 'How complete the content is (playbook-driven or extraction completeness)',
  validity: 'Validity/Conformance (playbook rule pass rate)',
  consistency: 'Consistency (playbook rule pass rate with severity weighting)',
  uniqueness: 'Uniqueness/Dedup (exact dup + near-dup rate)',
  timeliness: 'How current/timely the content is (staleness vs SLA/threshold)',
  text_integrity: 'Text integrity (OCR/text cleanliness, NOT factual accuracy)',
  parse_success: 'Parse/Extract Success (pages/chunks extracted vs attempted)',
  chunk_boundary_quality: 'Quality of chunk boundaries (fewer mid-sentence breaks)',
  chunk_coherence: 'Chunk Coherence (semantic cohesion within chunk)',
  chunk_size_health: 'Chunk Size Health (token length distribution vs target window)',
  metadata_completeness: 'Metadata Completeness (required metadata fields populated)',
  provenance_coverage: 'Provenance Coverage (weighted checklist of provenance fields)',
  duplicate_ratio: 'Duplicate ratio (1 - uniqueness)',
  // Raw token metrics
  total_tokens: 'Total tokens across all chunks (raw count, not a score)',
  avg_tokens_per_chunk: 'Average tokens per chunk (raw count, not a score)',
  num_chunks: 'Number of chunks processed (raw count, not a score)',
  min_tokens: 'Minimum tokens per chunk (raw count, not a score)',
  max_tokens: 'Maximum tokens per chunk (raw count, not a score)',
  p95_tokens_per_chunk: '95th percentile tokens per chunk (raw count, not a score)',
  token_est: 'Estimated token count for a chunk (raw count, not a score)',
  // Legacy metrics
  Completeness: 'How complete the content is',
  Accuracy: 'Accuracy of the information',
  Secure: 'Security and privacy compliance',
  Quality: 'Overall content quality',
  Timeliness: 'How current/timely the content is',
  Token_Count: 'Normalized token count',
  GPT_Confidence: 'Confidence level for GPT processing',
  Context_Quality: 'Quality of context provided',
  Metadata_Presence: 'How much metadata is present',
  Audience_Intentionality: 'How well content targets its audience',
  Diversity: 'Content diversity/variety',
  Audience_Accessibility: 'How accessible content is to audience',
  KnowledgeBase_Ready: 'Ready for knowledge base use',
  // AI-Ready metric descriptions (legacy)
  Chunk_Coherence: 'Semantic cohesion within chunks',
  Noise_Free_Score: 'Percentage of content free from boilerplate/navigation noise',
  Chunk_Boundary_Quality: 'Quality of chunk boundaries (fewer mid-sentence breaks)',
  // Vector metric descriptions
  Embedding_Dimension_Consistency: 'Percentage of vectors with expected dimension',
  Embedding_Success_Rate: 'Percentage of chunks successfully embedded and stored',
  Vector_Quality_Score: 'Composite score for valid vectors (no NaN/Inf), non-zero vectors, and optimal norm distribution',
  Embedding_Model_Health: 'Health score of the embedding model based on output consistency',
  Semantic_Search_Readiness: 'Composite score for RAG readiness (dimension consistency + vector quality + model health + success rate)',
  // RAG metric descriptions
  Retrieval_Recall_At_K: 'Percentage of relevant documents retrieved in top K results',
  Average_Precision_At_K: 'Average precision across top K retrieved results',
}

// Metric categories for professional organization
const METRIC_CATEGORIES = {
  governance: {
    name: 'Governance & Compliance',
    icon: Shield,
    metrics: ['Secure', 'completeness', 'Accuracy', 'Metadata_Presence', 'metadata_completeness'],
    headerBg: 'bg-blue-50',
    headerBorder: 'border-blue-200',
    iconClass: 'text-blue-600',
  },
  content: {
    name: 'Content Quality',
    icon: FileText,
    metrics: ['Quality', 'Context_Quality', 'Audience_Intentionality', 'Audience_Accessibility', 'Diversity', 'timeliness', 'KnowledgeBase_Ready', 'Token_Count', 'validity', 'consistency', 'text_integrity', 'parse_success'],
    headerBg: 'bg-blue-50',
    headerBorder: 'border-blue-200',
    iconClass: 'text-blue-600',
  },
  chunking: {
    name: 'Chunking & Structure',
    icon: Layers,
    metrics: ['chunk_coherence', 'chunk_boundary_quality', 'chunk_size_health', 'Chunk_Coherence', 'Noise_Free_Score', 'Chunk_Boundary_Quality'],
    headerBg: 'bg-blue-50',
    headerBorder: 'border-blue-200',
    iconClass: 'text-blue-600',
  },
  vector: {
    name: 'Vector Metrics',
    icon: Database,
    metrics: ['Embedding_Dimension_Consistency', 'Embedding_Success_Rate', 'Vector_Quality_Score', 'Embedding_Model_Health', 'Semantic_Search_Readiness'],
    headerBg: 'bg-blue-50',
    headerBorder: 'border-blue-200',
    iconClass: 'text-blue-600',
  },
  rag: {
    name: 'RAG Performance',
    icon: Search,
    metrics: ['Retrieval_Recall_At_K', 'Average_Precision_At_K'],
    headerBg: 'bg-blue-50',
    headerBorder: 'border-blue-200',
    iconClass: 'text-blue-600',
  },
}

export function AITrustScoreDisplay({ productId, showTitle = true }: AITrustScoreDisplayProps) {
  const [insights, setInsights] = useState<ProductInsightsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [applyingRecommendation, setApplyingRecommendation] = useState<string | null>(null)
  const { addToast } = useToast()
  
  // State for collapsible categories
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({
    governance: true,
    content: true,
    chunking: true,
    vector: true,
    rag: true,
  })

  useEffect(() => {
    loadInsights()
  }, [productId])

  const loadInsights = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.getProductInsights(productId)
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load AI Trust Score: ${response.error}`,
        })
      } else if (response.data) {
        setInsights(response.data)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load AI Trust Score'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const getActionLabel = (action: string): string => {
    switch (action) {
      case 'increase_chunk_overlap':
        return 'Increase Overlap'
      case 'switch_playbook':
        return 'Switch Playbook'
      case 'enhance_normalization':
        return 'Enhance Normalization'
      case 'extract_metadata':
        return 'Extract Metadata'
      case 'apply_all_recommendations':
        return 'Apply All'
      default:
        return 'Apply'
    }
  }

  const handleApplyRecommendation = async (recommendation: any, index: number) => {
    const recommendationKey = `${recommendation.type}-${index}`
    setApplyingRecommendation(recommendationKey)
    
    try {
      const response = await apiClient.applyRecommendation(
        productId,
        recommendation.action,
        recommendation.config || {}
      )
      
      if (response.error) {
        addToast({
          type: 'error',
          message: `Failed to apply recommendation: ${response.error}`,
        })
      } else if (response.data) {
        const result = response.data
        addToast({
          type: 'success',
          message: result.message || 'Recommendation applied successfully!',
        })
        
        // Reload insights to show updated recommendations
        setTimeout(() => {
          loadInsights()
        }, 1000)
        
        // Show message about pipeline rerun if needed
        if (result.requires_pipeline_rerun) {
          setTimeout(() => {
            addToast({
              type: 'info',
              message: 'Please re-run the pipeline to see the full effects of this change.',
            })
          }, 2000)
        }
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to apply recommendation',
      })
    } finally {
      setApplyingRecommendation(null)
    }
  }

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600 bg-green-50'
    if (score >= 0.6) return 'text-yellow-600 bg-yellow-50'
    return 'text-red-600 bg-red-50'
  }

  const getScoreIcon = (score: number) => {
    if (score >= 0.8) return <CheckCircle className="h-5 w-5 text-green-600" />
    if (score >= 0.6) return <AlertTriangle className="h-5 w-5 text-yellow-600" />
    return <XCircle className="h-5 w-5 text-red-600" />
  }

  const getPolicyStatusColor = (status: string) => {
    switch (status) {
      case 'passed':
        return 'bg-green-50 border-green-200 text-green-800'
      case 'failed':
        return 'bg-red-50 border-red-200 text-red-800'
      case 'warnings':
        return 'bg-yellow-50 border-yellow-200 text-yellow-800'
      default:
        return 'bg-gray-50 border-gray-200 text-gray-800'
    }
  }

  const getPolicyStatusIcon = (status: string) => {
    switch (status) {
      case 'passed':
        return <CheckCircle className="h-5 w-5 text-green-600" />
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-600" />
      case 'warnings':
        return <AlertTriangle className="h-5 w-5 text-yellow-600" />
      default:
        return <AlertCircle className="h-5 w-5 text-gray-600" />
    }
  }

  const formatMetricValue = (key: string, value: number) => {
    // Raw token metrics: show as integer with separators (never as percentage)
    const tokenMetrics = ['total_tokens', 'avg_tokens_per_chunk', 'num_chunks', 'min_tokens', 'max_tokens', 'p95_tokens_per_chunk', 'token_est']
    if (tokenMetrics.includes(key)) {
      return Math.round(value).toLocaleString()
    }
    
    // Legacy Token_Count: also show as integer
    if (key === 'Token_Count') {
      return Math.round(value).toLocaleString()
    }

    // Score metrics: backend returns in [0,1] range, convert to percentage for display
    let normalized = value
    
    // Handle different input scales (backward compatibility)
    if (normalized > 100) {
      // Values > 100: likely incorrectly scaled (e.g., 7500 means 75.0)
      normalized = normalized / 100
    } else if (normalized <= 1 && normalized >= 0) {
      // Values 0-1: convert to percentage (multiply by 100)
      normalized = normalized * 100
    }
    // Values 1-100: use as-is (already in correct scale)
    
    // Ensure normalized is between 0-100
    normalized = Math.max(0, Math.min(100, normalized))
    
    return `${normalized.toFixed(2)}%`
  }

  // Helper to get normalized value for progress bar (0-1 scale)
  const getNormalizedValueForProgress = (key: string, value: number): number => {
    // Raw token metrics: don't show as progress bar (they're counts, not scores)
    const tokenMetrics = ['total_tokens', 'avg_tokens_per_chunk', 'num_chunks', 'min_tokens', 'max_tokens', 'p95_tokens_per_chunk', 'token_est']
    if (tokenMetrics.includes(key)) {
      // Don't show progress bar for token metrics
      return 0
    }
    
    // Legacy Token_Count: don't show progress bar
    if (key === 'Token_Count') {
      return 0
    }
    
    // chunk_size_health: show as progress bar (it's a score)
    if (key === 'chunk_size_health') {
      let normalized = value
      if (normalized > 1) normalized = normalized / 100
      else if (normalized <= 1 && normalized >= 0) normalized = normalized
      return Math.max(0, Math.min(1, normalized))
    }
    
    // Score metrics: normalize to 0-1 for progress bar
    let normalized = value
    if (normalized > 100) {
      normalized = normalized / 100
    } else if (normalized <= 1 && normalized >= 0) {
      // Already in [0,1], use as-is
      normalized = normalized
    } else {
      // Values 1-100: divide by 100
      normalized = normalized / 100
    }
    normalized = Math.max(0, Math.min(1, normalized))
    return normalized
  }

  // Check if metric should show "Not Evaluated" for vector metrics
  const isNotEvaluated = (key: string, value: number): boolean => {
    const vectorMetrics = ['Embedding_Dimension_Consistency', 'Embedding_Success_Rate', 'Vector_Quality_Score', 'Embedding_Model_Health', 'Semantic_Search_Readiness', 'Retrieval_Recall_At_K', 'Average_Precision_At_K']
    return vectorMetrics.includes(key) && (value === 0 || value === null || value === undefined)
  }

  // Check if metric is a token metric (should not show progress bar)
  const isTokenMetric = (key: string): boolean => {
    const tokenMetrics = ['total_tokens', 'avg_tokens_per_chunk', 'num_chunks', 'min_tokens', 'max_tokens', 'p95_tokens_per_chunk', 'token_est', 'Token_Count']
    return tokenMetrics.includes(key)
  }

  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => ({
      ...prev,
      [category]: !prev[category],
    }))
  }

  // Organize metrics by category
  const organizeMetricsByCategory = (metrics: [string, any][]) => {
    const categorized: Record<string, [string, any][]> = {
      governance: [],
      content: [],
      chunking: [],
      vector: [],
      rag: [],
      other: [],
    }

    metrics.forEach(([key, value]) => {
      let found = false
      for (const [catKey, catConfig] of Object.entries(METRIC_CATEGORIES)) {
        if (catConfig.metrics.includes(key)) {
          categorized[catKey].push([key, value])
          found = true
          break
        }
      }
      if (!found) {
        categorized.other.push([key, value])
      }
    })

    return categorized
  }

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">AI Trust Score</h2>}
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 text-gray-400 animate-spin mr-2" />
          <p className="text-gray-600">Loading AI Trust Score...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">AI Trust Score</h2>}
        <div className="flex items-center justify-center py-8">
          <AlertCircle className="h-6 w-6 text-red-500 mr-2" />
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  if (!insights) {
    return null
  }

  const { fingerprint, policy, optimizer } = insights
  
  // Helper to get metric value from canonical schema (checks legacy_aliases if needed)
  const getMetricValue = (fingerprint: any, canonicalKey: string, legacyKey?: string): number => {
    // Try canonical key first
    if (canonicalKey && fingerprint?.[canonicalKey] !== undefined) {
      const val = fingerprint[canonicalKey]
      return typeof val === 'number' ? val : parseFloat(val) || 0
    }
    // Try legacy key at top-level
    if (legacyKey && fingerprint?.[legacyKey] !== undefined) {
      const val = fingerprint[legacyKey]
      return typeof val === 'number' ? val : parseFloat(val) || 0
    }
    // Try legacy_aliases
    if (legacyKey && fingerprint?.legacy_aliases?.[legacyKey] !== undefined) {
      const val = fingerprint.legacy_aliases[legacyKey]
      return typeof val === 'number' ? val : parseFloat(val) || 0
    }
    return 0
  }
  
  // Extract and normalize AI Trust Score (handle canonical and legacy formats)
  let trustScore = 0
  const rawTrustScore = getMetricValue(fingerprint, 'ai_trust_score', 'AI_Trust_Score')
  if (rawTrustScore > 0) {
    trustScore = rawTrustScore > 1 ? rawTrustScore / 100 : rawTrustScore
  }

  // Get all metrics except ai_trust_score/AI_Trust_Score, GPT_Confidence, legacy_aliases, metrics_semantics, and page
  const allMetrics = Object.entries(fingerprint || {})
    .filter(([key]) => {
      const excludeKeys = ['ai_trust_score', 'AI_Trust_Score', 'GPT_Confidence', 'legacy_aliases', 'metrics_semantics', 'page']
      return !excludeKeys.includes(key) && typeof fingerprint[key] === 'number'
    })
    .map(([key, value]) => [key, value] as [string, any])
  
  // Also extract metrics from legacy_aliases if present
  if (fingerprint?.legacy_aliases && typeof fingerprint.legacy_aliases === 'object') {
    Object.entries(fingerprint.legacy_aliases).forEach(([key, value]) => {
      if (typeof value === 'number' && !allMetrics.some(([k]) => k === key)) {
        allMetrics.push([key, value])
      }
    })
  }
  
  // Organize metrics by category
  const categorizedMetrics = organizeMetricsByCategory(allMetrics)

  return (
    <div className="space-y-6">
      {showTitle && <h2 className="text-lg font-semibold text-gray-900">AI Trust Score</h2>}

      {/* Overall AI Trust Score */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className={`rounded-lg p-6 ${getScoreColor(trustScore)}`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium mb-1">Overall AI Trust Score</p>
              <div className="flex items-baseline gap-2">
                <span className="text-4xl font-bold">{(trustScore * 100).toFixed(1)}%</span>
                <span className="text-sm opacity-75">/ 100%</span>
              </div>
              <p className="text-xs mt-2 opacity-75">
                {trustScore >= 0.8
                  ? 'Excellent - Ready for AI use'
                  : trustScore >= 0.6
                  ? 'Good - Minor improvements recommended'
                  : 'Needs Improvement - Significant enhancements required'}
              </p>
            </div>
            <div className="flex-shrink-0">{getScoreIcon(trustScore)}</div>
          </div>
        </div>
      </div>

      {/* Policy Status Banner */}
      {policy && (
        <div className={`rounded-lg border p-4 ${getPolicyStatusColor(policy.status || 'unknown')}`}>
          <div className="flex items-start gap-3">
            {getPolicyStatusIcon(policy.status || 'unknown')}
            <div className="flex-1">
              <h3 className="font-medium mb-1">
                Policy Evaluation: {policy.status ? (policy.status.charAt(0).toUpperCase() + policy.status.slice(1)) : 'Unknown'}
              </h3>
              {policy.violations && policy.violations.length > 0 && (
                <div className="mt-2">
                  <p className="text-sm font-medium mb-1">Violations:</p>
                  <ul className="list-disc list-inside text-sm space-y-1">
                    {(policy.violations || []).map((violation: string, idx: number) => (
                      <li key={idx}>{violation}</li>
                    ))}
                  </ul>
                </div>
              )}
              {policy.warnings && policy.warnings.length > 0 && (
                <div className="mt-2">
                  <p className="text-sm font-medium mb-1">Warnings:</p>
                  <ul className="list-disc list-inside text-sm space-y-1">
                    {(policy.warnings || []).map((warning: string, idx: number) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Detailed Metrics Breakdown - Categorized */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-6 flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-blue-600" />
          Detailed Metrics
        </h3>
        
        <div className="space-y-6">
          {Object.entries(METRIC_CATEGORIES).map(([catKey, catConfig]) => {
            const metrics = categorizedMetrics[catKey]
            if (metrics.length === 0) return null
            
            const Icon = catConfig.icon
            const isExpanded = expandedCategories[catKey]
            
            return (
              <div key={catKey} className={`border-2 rounded-xl overflow-hidden ${catConfig.headerBorder}`}>
                <button
                  onClick={() => toggleCategory(catKey)}
                  className={`w-full px-6 py-4 flex items-center justify-between ${catConfig.headerBg} border-b border-blue-200 hover:bg-blue-100 transition-colors`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`h-5 w-5 ${catConfig.iconClass}`} />
                    <h4 className="text-lg font-semibold text-gray-900">{catConfig.name}</h4>
                    <span className="text-sm text-blue-600 font-medium">({metrics.length})</span>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="h-5 w-5 text-gray-600" />
                  ) : (
                    <ChevronDown className="h-5 w-5 text-gray-600" />
                  )}
                </button>
                
                {isExpanded && (
                  <div className="p-6 bg-white">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {metrics.map(([key, value]) => {
                        const displayName = METRIC_NAMES[key] || key.replace(/_/g, ' ')
                        const description = METRIC_DESCRIPTIONS[key] || ''
                        const numericValue = typeof value === 'number' ? value : parseFloat(value as any) || 0
                        const notEvaluated = isNotEvaluated(key, numericValue)
                        const isToken = isTokenMetric(key)
                        
                        // Normalize value for color determination (0-1 scale)
                        // Token metrics don't have color coding (they're counts, not scores)
                        const normalizedForColor = (() => {
                          if (isToken) {
                            // Token metrics: don't color code
                            return 0.5  // Neutral color
                          }
                          // Score metrics: normalize to [0,1]
                          let n = numericValue
                          if (n <= 1 && n >= 0) n = n
                          else if (n > 100) n = n / 100
                          else n = n / 100  // Values 1-100: divide by 100
                          n = Math.max(0, Math.min(1, n))
                          return n
                        })()
                        
                        const scoreColor = notEvaluated 
                          ? 'text-gray-500' 
                          : isToken
                          ? 'text-gray-600'  // Neutral color for token metrics
                          : normalizedForColor >= 0.8 
                          ? 'text-green-600' 
                          : normalizedForColor >= 0.6 
                          ? 'text-yellow-600' 
                          : 'text-red-600'
                        
                        return (
                          <div key={key} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors relative group">
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex-1">
                                <div className="flex items-center gap-2">
                                  <h4 className="text-sm font-medium text-gray-900">{displayName}</h4>
                                  {description && (
                                    <div className="relative">
                                      <Info className="h-4 w-4 text-gray-400 cursor-help" />
                                      <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 w-64 p-2 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                                        {description}
                                      </div>
                                    </div>
                                  )}
                                </div>
                                {description && (
                                  <p className="text-xs text-gray-500 mt-1">{description}</p>
                                )}
                              </div>
                              <div className={`text-lg font-semibold ${scoreColor} ml-2`}>
                                {notEvaluated ? 'Not Evaluated' : formatMetricValue(key, numericValue)}
                              </div>
                            </div>
                            {/* Only show progress bar for score metrics, not token metrics or not evaluated */}
                            {!notEvaluated && !isToken && (
                              <div className="w-full bg-gray-200 rounded-full h-2">
                                <div
                                  className={`h-2 rounded-full transition-all ${
                                    normalizedForColor >= 0.8 ? 'bg-green-500' : normalizedForColor >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                                  }`}
                                  style={{ width: `${Math.min(normalizedForColor * 100, 100)}%` }}
                                />
                              </div>
                            )}
                            {notEvaluated && (
                              <div className="w-full bg-gray-100 rounded-full h-2">
                                <div className="h-2 rounded-full bg-gray-300" style={{ width: '100%' }} />
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
          
          {/* Other uncategorized metrics */}
          {categorizedMetrics.other.length > 0 && (
            <div className="border-2 border-gray-200 rounded-xl overflow-hidden">
              <div className="w-full px-6 py-4 bg-gray-50 flex items-center justify-between">
                <h4 className="text-lg font-semibold text-gray-900">Other Metrics</h4>
              </div>
              <div className="p-6 bg-white">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {categorizedMetrics.other.map(([key, value]) => {
                    const displayName = METRIC_NAMES[key] || key.replace(/_/g, ' ')
                    const description = METRIC_DESCRIPTIONS[key] || ''
                    const numericValue = typeof value === 'number' ? value : parseFloat(value as any) || 0
                    const isToken = isTokenMetric(key)
                    
                    // Normalize value for color determination
                    const normalizedForColor = (() => {
                      if (isToken) {
                        return 0.5  // Neutral color for token metrics
                      }
                      let n = numericValue
                      if (n <= 1 && n >= 0) n = n
                      else if (n > 100) n = n / 100
                      else n = n / 100
                      n = Math.max(0, Math.min(1, n))
                      return n
                    })()
                    
                    const scoreColor = isToken
                      ? 'text-gray-600'
                      : normalizedForColor >= 0.8 ? 'text-green-600' : normalizedForColor >= 0.6 ? 'text-yellow-600' : 'text-red-600'
                    
                    return (
                      <div key={key} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors relative group">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <h4 className="text-sm font-medium text-gray-900">{displayName}</h4>
                              {description && (
                                <div className="relative">
                                  <Info className="h-4 w-4 text-gray-400 cursor-help" />
                                  <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 w-64 p-2 bg-gray-900 text-white text-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                                    {description}
                                  </div>
                                </div>
                              )}
                            </div>
                            {description && (
                              <p className="text-xs text-gray-500 mt-1">{description}</p>
                            )}
                          </div>
                          <div className={`text-lg font-semibold ${scoreColor} ml-2`}>
                            {formatMetricValue(key, numericValue)}
                          </div>
                        </div>
                        {/* Only show progress bar for score metrics, not token metrics */}
                        {!isToken && (
                          <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                              className={`h-2 rounded-full ${
                                normalizedForColor >= 0.8 ? 'bg-green-500' : normalizedForColor >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${Math.min(normalizedForColor * 100, 100)}%` }}
                            />
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Optimizer Suggestions */}
      {optimizer && (optimizer.suggestions || optimizer.playbook_recommendations || (optimizer.actionable_recommendations && optimizer.actionable_recommendations.length > 0)) && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h3 className="text-md font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Lightbulb className="h-5 w-5 text-yellow-600" />
            Optimization Suggestions
          </h3>
          
          {/* Actionable Recommendations */}
          {optimizer.actionable_recommendations && optimizer.actionable_recommendations.length > 0 && (
            <div className="mb-6">
              <p className="text-sm font-medium text-gray-700 mb-3">Recommendations:</p>
              <div className="space-y-3">
                {optimizer.actionable_recommendations.map((rec: any, idx: number) => {
                  const isApplying = applyingRecommendation === `${rec.type}-${idx}`
                  const actionLabel = getActionLabel(rec.action)
                  
                  return (
                    <div key={idx} className="border border-gray-200 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 transition-colors">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <Sparkles className="h-4 w-4 text-blue-600" />
                            <p className="text-sm text-gray-700">{rec.message}</p>
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          className="flex-shrink-0"
                          onClick={() => handleApplyRecommendation(rec, idx)}
                          disabled={isApplying}
                        >
                          {isApplying ? (
                            <>
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                              Applying...
                            </>
                          ) : (
                            <>
                              <Sparkles className="h-3 w-3 mr-1" />
                              {actionLabel}
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          
          {/* General Suggestions (non-actionable) */}
          {optimizer.suggestions && optimizer.suggestions.length > 0 && (
            <div className="mb-4">
              <p className="text-sm font-medium text-gray-700 mb-2">General Suggestions:</p>
              <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                {(optimizer.suggestions || []).map((suggestion: string, idx: number) => (
                  <li key={idx}>{suggestion}</li>
                ))}
              </ul>
            </div>
          )}
          
          {/* Playbook Recommendations */}
          {optimizer.playbook_recommendations && optimizer.playbook_recommendations.length > 0 && (
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Playbook Recommendations:</p>
              <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                {(optimizer.playbook_recommendations || []).map((rec: string, idx: number) => (
                  <li key={idx}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
