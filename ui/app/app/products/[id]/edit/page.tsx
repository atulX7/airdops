'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Save, X, Package, Settings, FileText, Sparkles, AlertCircle, CheckCircle2, Zap, DollarSign, Target } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ResultModal } from '@/components/ui/modal'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { getEmbeddingModelOptions, getEmbeddingModelOptionsSync, getEmbeddingDimension, getEmbeddingDimensionSync, preloadEmbeddingModels } from '@/lib/embedding-models'
import { PlaybookSelector } from '@/components/PlaybookSelector'

interface Product {
  id: string
  workspace_id: string
  owner_user_id: string
  name: string
  status: 'draft' | 'running' | 'ready' | 'failed'
  current_version: number
  created_at: string
  updated_at?: string
  /** digital_pdf | scanned_pdf | mixed (from preprocess; not content_type) */
  extraction_type?: string | null
}

export default function EditProductPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  
  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [formData, setFormData] = useState<{
    name: string
    status: 'draft' | 'running' | 'ready' | 'failed'
    playbook_id: string | undefined
    chunking_mode: 'auto' | 'manual'
    chunk_size: number | string
    chunk_overlap: number | string
    min_chunk_size: number | string
    max_chunk_size: number | string
    chunking_strategy: 'fixed_size' | 'semantic' | 'recursive'
    content_type: string
    model_optimized: boolean
    confidence_threshold: number
    embedder_name: string
    embedding_dimension: number
    optimization_mode: 'pattern' | 'hybrid' | 'llm'
    vector_creation_enabled: boolean
  }>({
    name: '',
    status: 'draft',
    playbook_id: undefined,
    // Chunking configuration
    chunking_mode: 'auto',
    chunk_size: 1000,
    chunk_overlap: 200,
    min_chunk_size: 100,
    max_chunk_size: 2000,
    chunking_strategy: 'fixed_size',
    content_type: 'general',
    model_optimized: true,
    confidence_threshold: 0.7,
    // Embedding configuration
    embedder_name: 'minilm',
    embedding_dimension: 384,
    // Optimization mode
    optimization_mode: 'pattern',
    // Vector creation configuration
    vector_creation_enabled: true
  })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [autoConfiguring, setAutoConfiguring] = useState(false)
  const [embeddingModelOptions, setEmbeddingModelOptions] = useState<
    Array<{ value: string; label: string; disabled?: boolean; disabledReason?: string }>
  >([])
  /** null = not loaded yet; false = no workspace/server OpenAI key for paid embeddings */
  const [openaiEmbeddingsAvailable, setOpenaiEmbeddingsAvailable] = useState<boolean | null>(null)

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
      setLoading(true)
      const response = await apiClient.getProduct(productId)
      
      if (response.error) {
        setError(response.error)
      } else {
        const productData = response.data as Product
        setProduct(productData)

        // Derive chunking configuration
        // Priority: Use saved mode and corresponding settings (auto_settings or manual_settings)
        // resolved_settings is only for display/reference, not for editing
        const cfg = (productData as any).chunking_config || {}
        const chunkingMode = cfg.mode || 'auto'

        // Get settings based on mode - prefer saved settings over resolved_settings
        let settings: any = {}
        if (chunkingMode === 'auto') {
          // PRIORITY: Use resolved_settings if available (from actual content analysis)
          if (cfg.resolved_settings && cfg.resolved_settings.content_type) {
            const resolved = cfg.resolved_settings
            settings = {
              content_type: resolved.content_type,
              chunk_size: resolved.chunk_size || 1000,
              chunk_overlap: resolved.chunk_overlap || 200,
              min_chunk_size: resolved.min_chunk_size || 100,
              max_chunk_size: resolved.max_chunk_size || 2000,
              chunking_strategy: resolved.chunking_strategy || 'fixed_size',
              ...cfg.auto_settings, // Preserve other auto_settings like confidence_threshold, model_optimized
            }
          } else {
            // Fallback: Use auto_settings for content_type and get optimal config
            const autoSettings = cfg.auto_settings || {}
            const contentType = autoSettings.content_type || 'general'
            
            // Get optimal configuration based on content type - ADD regulatory and finance_banking
            const optimalConfigs: Record<string, {
              chunk_size: number
              chunk_overlap: number
              min_chunk_size: number
              max_chunk_size: number
              chunking_strategy: string
            }> = {
              'legal': {
                chunk_size: 2000,
                chunk_overlap: 400,
                min_chunk_size: 200,
                max_chunk_size: 3000,
                chunking_strategy: 'semantic'
              },
              'medical': {
                chunk_size: 800,
                chunk_overlap: 160,
                min_chunk_size: 100,
                max_chunk_size: 1200,
                chunking_strategy: 'semantic'
              },
              'regulatory': {
                chunk_size: 1400,
                chunk_overlap: 280,
                min_chunk_size: 200,
                max_chunk_size: 2200,
                chunking_strategy: 'semantic'
              },
              'finance_banking': {
                chunk_size: 1300,
                chunk_overlap: 260,
                min_chunk_size: 200,
                max_chunk_size: 2200,
                chunking_strategy: 'semantic'
              },
              'code': {
                chunk_size: 1500,
                chunk_overlap: 300,
                min_chunk_size: 100,
                max_chunk_size: 2500,
                chunking_strategy: 'recursive'
              },
              'documentation': {
                chunk_size: 1200,
                chunk_overlap: 200,
                min_chunk_size: 100,
                max_chunk_size: 2000,
                chunking_strategy: 'semantic'
              },
              'conversation': {
                chunk_size: 800,
                chunk_overlap: 100,
                min_chunk_size: 50,
                max_chunk_size: 1500,
                chunking_strategy: 'semantic'
              },
              'academic': {
                chunk_size: 1800,
                chunk_overlap: 350,
                min_chunk_size: 150,
                max_chunk_size: 2500,
                chunking_strategy: 'semantic'
              },
              'technical': {
                chunk_size: 1400,
                chunk_overlap: 250,
                min_chunk_size: 100,
                max_chunk_size: 2200,
                chunking_strategy: 'semantic'
              },
              'general': {
                chunk_size: 1000,
                chunk_overlap: 200,
                min_chunk_size: 100,
                max_chunk_size: 2000,
                chunking_strategy: 'fixed_size'
              }
            }
            
            const optimal = optimalConfigs[contentType] || optimalConfigs['general']
            
            // In auto mode, use optimal config based on content_type
            settings = {
              ...autoSettings,
              chunk_size: optimal.chunk_size,
              chunk_overlap: optimal.chunk_overlap,
              min_chunk_size: optimal.min_chunk_size,
              max_chunk_size: optimal.max_chunk_size,
              chunking_strategy: optimal.chunking_strategy,
            }
          }
        } else {
          // In manual mode, ALWAYS use manual_settings if it exists
          // Only fallback to resolved_settings if manual_settings is completely missing
          const manualSettings = cfg.manual_settings
          if (manualSettings && typeof manualSettings === 'object' && Object.keys(manualSettings).length > 0) {
            // manual_settings exists and has values - use it directly (this is the source of truth for manual mode)
            settings = manualSettings
          } else {
            // manual_settings is missing or empty, fallback to resolved_settings or defaults
            console.warn('manual_settings is empty, falling back to resolved_settings')
            settings = cfg.resolved_settings || {}
          }
        }
        
        // Final fallback to defaults if settings are still empty
        if (!settings.chunk_size && !cfg.resolved_settings) {
          settings = {
            chunk_size: 1000,
            chunk_overlap: 200,
            min_chunk_size: 100,
            max_chunk_size: 2000,
            chunking_strategy: 'fixed_size'
          }
        }
        
        // Use nullish coalescing (??) instead of || to avoid falling back on falsy values like 0
        const derivedChunkSize = settings.chunk_size ?? settings.max_tokens ?? 1000
        const derivedChunkOverlap =
          settings.chunk_overlap ??
          (settings.overlap_sentences ? settings.overlap_sentences * 20 : 200)
        const derivedMinChunk = settings.min_chunk_size ?? 100
        const derivedMaxChunk = settings.max_chunk_size ?? 2000
        const derivedStrategy = settings.chunking_strategy ?? settings.strategy ?? 'fixed_size'
        const derivedContentType = settings.content_type || cfg.resolved_settings?.content_type || cfg.auto_settings?.content_type || 'general'
        const derivedModelOptimized = settings.model_optimized ?? cfg.auto_settings?.model_optimized ?? true
        const derivedConfidence = settings.confidence || settings.analysis_confidence || cfg.auto_settings?.confidence_threshold || 0.7
        
        // Get embedding configuration from embedding_config field, not chunking_config
        const embeddingConfig = (productData as any).embedding_config || {}
        const derivedEmbedder = embeddingConfig.embedder_name || 'minilm'
        const derivedDim = embeddingConfig.embedding_dimension || 384
        
        // Get optimization_mode from chunking_config (defaults to 'pattern')
        const optimizationMode = cfg.optimization_mode || 'pattern'

        setFormData({
          name: productData.name,
          status: productData.status,
          playbook_id: (productData as any).playbook_id,
          // Load chunking configuration from product (if available)
          chunking_mode: chunkingMode,
          chunk_size: derivedChunkSize,
          chunk_overlap: derivedChunkOverlap,
          min_chunk_size: derivedMinChunk,
          max_chunk_size: derivedMaxChunk,
          chunking_strategy: derivedStrategy as 'fixed_size' | 'semantic' | 'recursive',
          content_type: derivedContentType,
          model_optimized: derivedModelOptimized,
          confidence_threshold: derivedConfidence,
          embedder_name: derivedEmbedder,
          embedding_dimension: derivedDim,
          optimization_mode: optimizationMode as 'pattern' | 'hybrid' | 'llm',
          // Vector creation configuration
          vector_creation_enabled: (productData as any).vector_creation_enabled !== undefined ? (productData as any).vector_creation_enabled : true
        })

        // Load embedding model list with workspace-scoped provider key checks (paid models disabled when no key)
        const wsId = (productData as Product).workspace_id
        if (wsId) {
          try {
            await preloadEmbeddingModels(wsId)
            const opts = await getEmbeddingModelOptions(true, wsId)
            setEmbeddingModelOptions(opts)
            const settingsRes = await apiClient.getWorkspaceSettings(wsId)
            if (settingsRes.data && typeof (settingsRes.data as any).openai_available_for_embeddings === 'boolean') {
              setOpenaiEmbeddingsAvailable((settingsRes.data as any).openai_available_for_embeddings)
            } else {
              setOpenaiEmbeddingsAvailable(null)
            }
          } catch (err) {
            console.error('Failed to load embedding models:', err)
            setEmbeddingModelOptions(getEmbeddingModelOptionsSync())
            setOpenaiEmbeddingsAvailable(null)
          }
        } else {
          setOpenaiEmbeddingsAvailable(null)
        }
      }
    } catch (err) {
      setError('Failed to load product')
    } finally {
      setLoading(false)
    }
  }

  // Content type to optimal chunking configuration mapping (matches backend ContentAnalyzer)
  const getOptimalChunkingConfig = (contentType: string) => {
    const configs: Record<string, {
      chunk_size: number
      chunk_overlap: number
      min_chunk_size: number
      max_chunk_size: number
      chunking_strategy: string
    }> = {
      'legal': {
        chunk_size: 2000,
        chunk_overlap: 400,
        min_chunk_size: 200,
        max_chunk_size: 3000,
        chunking_strategy: 'semantic'
      },
      'code': {
        chunk_size: 1500,
        chunk_overlap: 300,
        min_chunk_size: 100,
        max_chunk_size: 2500,
        chunking_strategy: 'recursive'
      },
      'documentation': {
        chunk_size: 1200,
        chunk_overlap: 200,
        min_chunk_size: 100,
        max_chunk_size: 2000,
        chunking_strategy: 'semantic' // Backend uses paragraph_boundary, using semantic as closest match
      },
      'conversation': {
        chunk_size: 800,
        chunk_overlap: 100,
        min_chunk_size: 50,
        max_chunk_size: 1500,
        chunking_strategy: 'semantic' // Backend uses sentence_boundary, using semantic as closest match
      },
      'academic': {
        chunk_size: 1800,
        chunk_overlap: 350,
        min_chunk_size: 150,
        max_chunk_size: 2500,
        chunking_strategy: 'semantic'
      },
      'technical': {
        chunk_size: 1400,
        chunk_overlap: 250,
        min_chunk_size: 100,
        max_chunk_size: 2200,
        chunking_strategy: 'semantic'
      },
      'general': {
        chunk_size: 1000,
        chunk_overlap: 200,
        min_chunk_size: 100,
        max_chunk_size: 2000,
        chunking_strategy: 'fixed_size'
      }
    }
    return configs[contentType] || configs['general']
  }

  // Handle number input changes - allow empty string during typing, parse on blur
  const handleNumberInputChange = (field: string, value: string) => {
    // Remove any non-numeric characters except empty string
    const cleaned = value.replace(/[^0-9]/g, '')
    
    // Allow empty string during typing
    if (cleaned === '') {
      setFormData(prev => ({ ...prev, [field]: '' }))
      return
    }
    
    // Parse and set the number
    const numValue = parseInt(cleaned, 10)
    if (!isNaN(numValue) && numValue >= 0) {
      setFormData(prev => ({ ...prev, [field]: numValue }))
    }
  }

  // Handle number input blur - ensure valid number is set
  const handleNumberInputBlur = (field: string, currentValue: string | number, defaultValue: number) => {
    let numValue: number
    if (typeof currentValue === 'string') {
      if (currentValue === '' || currentValue.trim() === '') {
        numValue = defaultValue
      } else {
        const parsed = parseInt(currentValue.replace(/[^0-9]/g, ''), 10)
        numValue = isNaN(parsed) ? defaultValue : parsed
      }
    } else {
      numValue = isNaN(currentValue) || currentValue < 0 ? defaultValue : currentValue
    }
    
    setFormData(prev => ({ ...prev, [field]: numValue }))
  }

  const handleInputChange = (field: string, value: string | number | boolean | undefined) => {
    setFormData(prev => {
      const newData = {
        ...prev,
        [field]: value
      }
      
      // Auto-update embedding dimension based on model selection
      if (field === 'embedder_name') {
        // Use sync version for immediate update (uses cache or fallback)
        const dimension = getEmbeddingDimensionSync(value as string)
        if (dimension !== undefined) {
          newData.embedding_dimension = dimension
        } else {
          // If not found in cache/fallback, try async fetch
          getEmbeddingDimension(value as string).then(dim => {
            if (dim !== undefined) {
              setFormData(prev => ({ ...prev, embedding_dimension: dim }))
            }
          }).catch(err => {
            console.error('Failed to fetch embedding dimension:', err)
          })
        }
      }
      
      // Auto-update chunking parameters when content type changes (only in auto mode)
      if (field === 'content_type' && prev.chunking_mode === 'auto') {
        const optimalConfig = getOptimalChunkingConfig(value as string)
        newData.chunk_size = optimalConfig.chunk_size
        newData.chunk_overlap = optimalConfig.chunk_overlap
        newData.min_chunk_size = optimalConfig.min_chunk_size
        newData.max_chunk_size = optimalConfig.max_chunk_size
        newData.chunking_strategy = optimalConfig.chunking_strategy as 'fixed_size' | 'semantic' | 'recursive'
      }
      
      return newData
    })
    
    // Clear field error when user starts typing
    if (fieldErrors[field]) {
      setFieldErrors(prev => {
        const newErrors = { ...prev }
        delete newErrors[field]
        return newErrors
      })
    }
    
    // Clear general error
    if (error) {
      setError(null)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    // Prevent multiple submissions
    if (saving) {
      return
    }
    
    setSaving(true)
    setError(null)
    setFieldErrors({})
    
    // Validation
    const newFieldErrors: Record<string, string> = {}
    
    if (!formData.name.trim()) {
      newFieldErrors.name = 'Product name is required'
    }
    
    // Validate chunking configuration (ensure values are numbers)
    const chunkSize = typeof formData.chunk_size === 'number' ? formData.chunk_size : parseInt(String(formData.chunk_size || 0), 10)
    const chunkOverlap = typeof formData.chunk_overlap === 'number' ? formData.chunk_overlap : parseInt(String(formData.chunk_overlap || 0), 10)
    const minChunkSize = typeof formData.min_chunk_size === 'number' ? formData.min_chunk_size : parseInt(String(formData.min_chunk_size || 0), 10)
    const maxChunkSize = typeof formData.max_chunk_size === 'number' ? formData.max_chunk_size : parseInt(String(formData.max_chunk_size || 0), 10)
    
    if (isNaN(chunkSize) || chunkSize < 50 || chunkSize > 5000) {
      newFieldErrors.chunk_size = 'Chunk size must be between 50 and 5000 characters'
    }
    
    if (isNaN(chunkOverlap) || chunkOverlap < 0 || chunkOverlap >= chunkSize) {
      newFieldErrors.chunk_overlap = `Chunk overlap must be between 0 and ${chunkSize - 1} (less than chunk size)`
    }
    
    if (isNaN(minChunkSize) || minChunkSize < 10 || minChunkSize > chunkSize) {
      newFieldErrors.min_chunk_size = 'Min chunk size must be between 10 and chunk size'
    }
    
    if (isNaN(maxChunkSize) || maxChunkSize < chunkSize || maxChunkSize > 10000) {
      newFieldErrors.max_chunk_size = 'Max chunk size must be between chunk size and 10000'
    }

    const embeddingChoice = embeddingModelOptions.find((o) => o.value === formData.embedder_name)
    if (embeddingChoice?.disabled) {
      newFieldErrors.embedder_name =
        embeddingChoice.disabledReason ||
        'This embedding model requires a provider API key. Configure Workspace Settings or choose a local model (e.g. MiniLM).'
    }
    
    if (Object.keys(newFieldErrors).length > 0) {
      console.error('❌ Validation failed:', newFieldErrors)
      setFieldErrors(newFieldErrors)
      setSaving(false)
      
      // Focus on the first invalid field
      const firstInvalidField = Object.keys(newFieldErrors)[0]
      setTimeout(() => {
        const element = document.getElementById(firstInvalidField)
        if (element) {
          element.focus()
        }
      }, 100)
      return
    }

    try {
      // Build chunking config based on mode
      const chunkingConfig: any = {
          mode: formData.chunking_mode,
        optimization_mode: formData.optimization_mode  // Add optimization mode
      }
      
      if (formData.chunking_mode === 'auto') {
        // Preserve detected content_type from resolved_settings if available
        const currentConfig = (product as any)?.chunking_config || {}
        const detectedContentType = currentConfig.resolved_settings?.content_type
        const contentTypeToSave = detectedContentType || formData.content_type
        
        chunkingConfig.auto_settings = {
          content_type: contentTypeToSave,  // Use detected type if available
          model_optimized: formData.model_optimized,
          confidence_threshold: formData.confidence_threshold
        }
        // Don't send manual_settings when in auto mode
      } else {
        chunkingConfig.manual_settings = {
          chunk_size: typeof formData.chunk_size === 'number' ? formData.chunk_size : parseInt(String(formData.chunk_size || 0), 10),
          chunk_overlap: typeof formData.chunk_overlap === 'number' ? formData.chunk_overlap : parseInt(String(formData.chunk_overlap || 0), 10),
          min_chunk_size: typeof formData.min_chunk_size === 'number' ? formData.min_chunk_size : parseInt(String(formData.min_chunk_size || 0), 10),
          max_chunk_size: typeof formData.max_chunk_size === 'number' ? formData.max_chunk_size : parseInt(String(formData.max_chunk_size || 0), 10),
            chunking_strategy: formData.chunking_strategy
          }
        // Don't send auto_settings when in manual mode
      }
      
      const response = await apiClient.updateProduct(productId, {
        name: formData.name,
        status: formData.status,
        playbook_id: formData.playbook_id,
        chunking_config: chunkingConfig,
        embedding_config: {
          embedder_name: formData.embedder_name,
          embedding_dimension: formData.embedding_dimension
        },
        vector_creation_enabled: formData.vector_creation_enabled
      })

      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Update Failed',
          message: typeof response.error === 'string' ? response.error : JSON.stringify(response.error, null, 2)
        })
        setSaving(false)
        setShowResultModal(true)
        return
      } else {
        // Verify the saved configuration matches what we sent
        const savedConfig = response.data?.chunking_config
        const savedManual = savedConfig?.manual_settings
        
        if (savedManual && formData.chunking_mode === 'manual') {
          // Check for mismatches
          const mismatches: string[] = []
          if (chunkSize !== savedManual.chunk_size) mismatches.push(`chunk_size: ${chunkSize} → ${savedManual.chunk_size}`)
          if (chunkOverlap !== savedManual.chunk_overlap) mismatches.push(`chunk_overlap: ${chunkOverlap} → ${savedManual.chunk_overlap}`)
          if (minChunkSize !== savedManual.min_chunk_size) mismatches.push(`min_chunk_size: ${minChunkSize} → ${savedManual.min_chunk_size}`)
          if (maxChunkSize !== savedManual.max_chunk_size) mismatches.push(`max_chunk_size: ${maxChunkSize} → ${savedManual.max_chunk_size}`)
          if (formData.chunking_strategy !== savedManual.chunking_strategy) mismatches.push(`strategy: ${formData.chunking_strategy} → ${savedManual.chunking_strategy}`)
        }
        
        // Use the response data directly to update the form immediately
        if (response.data) {
          const updatedProduct = response.data as Product
          setProduct(updatedProduct)
          
          // Update formData with the saved values from the response
          const cfg = (updatedProduct as any).chunking_config || {}
          
          // Update optimization_mode from saved config
          if (cfg.optimization_mode) {
            setFormData(prev => ({
              ...prev,
              optimization_mode: cfg.optimization_mode as 'pattern' | 'hybrid' | 'llm'
            }))
          }
          
          if (cfg.manual_settings && formData.chunking_mode === 'manual') {
            const saved = cfg.manual_settings
            setFormData(prev => ({
              ...prev,
              chunk_size: saved.chunk_size ?? prev.chunk_size,
              chunk_overlap: saved.chunk_overlap ?? prev.chunk_overlap,
              min_chunk_size: saved.min_chunk_size ?? prev.min_chunk_size,
              max_chunk_size: saved.max_chunk_size ?? prev.max_chunk_size,
              chunking_strategy: saved.chunking_strategy ?? prev.chunking_strategy
            }))
          }
        }
        
        setResultModalData({
          type: 'success',
          title: 'Product Updated',
          message: 'Product configuration has been saved successfully! Please re-run the pipeline to apply the new settings.'
        })
        
        // Reload product data after a delay to ensure database has fully committed
        setTimeout(async () => {
          await loadProduct()
        }, 1000)
        
        // Redirect back to product detail page after a short delay
        setTimeout(() => {
          router.push(`/app/products/${productId}`)
        }, 2000)
      }
      setShowResultModal(true)
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Update Failed',
        message: 'An unexpected error occurred.'
      })
      setShowResultModal(true)
    } finally {
      setSaving(false)
    }
  }

  const handleAutoConfigure = async () => {
    if (autoConfiguring) return
    
    setAutoConfiguring(true)
    setError(null)
    
    try {
      const response = await apiClient.autoConfigureChunking(productId)
      
      if (response.error) {
        setResultModalData({
          type: 'error',
          title: 'Auto-Configuration Failed',
          message: response.error
        })
      } else {
        // Update form data with the auto-configured settings
        const data = response.data
        setFormData(prev => ({
          ...prev,
          chunking_mode: 'auto',
          content_type: data.content_type,
          chunk_size: data.recommended_config.chunk_size,
          chunk_overlap: data.recommended_config.chunk_overlap,
          min_chunk_size: data.recommended_config.min_chunk_size,
          max_chunk_size: data.recommended_config.max_chunk_size,
          chunking_strategy: data.recommended_config.strategy
        }))
        
        setResultModalData({
          type: 'success',
          title: 'Auto-Configuration Complete',
          message: `Content type detected: ${data.content_type} (${(data.confidence * 100).toFixed(1)}% confidence). ${data.reasoning}`
        })
      }
      setShowResultModal(true)
    } catch (err) {
      setResultModalData({
        type: 'error',
        title: 'Auto-Configuration Failed',
        message: 'An unexpected error occurred during auto-configuration.'
      })
      setShowResultModal(true)
    } finally {
      setAutoConfiguring(false)
    }
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

  if (status === 'unauthenticated') {
    router.push('/')
    return null
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
      <div className="p-6">
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
          <span className="text-sm font-medium text-gray-900">Edit</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <div className="flex items-center">
            <div className="bg-blue-100 rounded-lg p-2 mr-4">
              <Package className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Edit Product</h1>
              <p className="text-sm text-gray-500 mt-1">Update product settings and configuration</p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <Label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                Product Name
              </Label>
              <Input
                id="name"
                type="text"
                value={formData.name}
                onChange={(e) => handleInputChange('name', e.target.value)}
                className={`${fieldErrors.name ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''}`}
                placeholder="Enter product name"
              />
              {fieldErrors.name && (
                <p className="mt-1 text-sm text-red-600">{fieldErrors.name}</p>
              )}
            </div>

            {/* Preprocessing Playbook Selection */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <Label className="text-sm font-medium text-gray-700">Preprocessing Playbook</Label>
                {(!formData.playbook_id && !(product as any)?.playbook_id) && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                    Auto-Detect
                  </span>
                )}
                {(product as any)?.playbook_selection?.method === 'auto_detected' && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                    Auto-Detected
                  </span>
                )}
              </div>
              <PlaybookSelector
                value={formData.playbook_id || undefined}
                onChange={(playbookId) => handleInputChange('playbook_id', playbookId as string | undefined)}
                disabled={saving}
                workspaceId={product?.workspace_id}
                showCustomizeButton={true}
              />
              <p className="mt-1 text-sm text-gray-500">
                Select a preprocessing playbook or leave empty for auto-detection during pipeline execution.
              </p>
              {product && (product as any).playbook_selection && (
                <div className="mt-2 p-3 bg-green-50 border border-green-200 rounded-md">
                  <p className="text-sm text-green-800">
                    <strong>Detection Method:</strong> {(product as any).playbook_selection.method === 'auto_detected' ? 'Auto-Detected' : 'Manual'}
                  </p>
                  {(product as any).playbook_selection.reason && (
                    <p className="text-xs text-green-700 mt-1">
                      Reason: {(product as any).playbook_selection.reason.replace(/_/g, ' ')}
                    </p>
                  )}
                  {(product as any).playbook_selection.detected_at && (
                    <p className="text-xs text-green-600 mt-1">
                      Detected: {new Date((product as any).playbook_selection.detected_at).toLocaleString()}
                    </p>
                  )}
                  {(product as any).playbook_selection.confidence && (
                    <p className="text-xs text-green-700 mt-1">
                      Confidence: {((product as any).playbook_selection.confidence * 100).toFixed(0)}%
                    </p>
                  )}
                </div>
              )}
              {product && (product as any).playbook_id && (product as any).playbook_selection?.method !== 'auto_detected' && (
                <p className="mt-2 text-sm text-green-600">
                  Current saved playbook: <strong>{(product as any).playbook_id}</strong>
                </p>
              )}
            </div>

            {/* Saved Configuration Display (for verification) */}
            {product && (() => {
              const chunkingConfig = (product as any).chunking_config;
              const mode = chunkingConfig?.mode || 'auto';
              const manual = chunkingConfig?.manual_settings;
              const resolved = chunkingConfig?.resolved_settings;
              const auto = chunkingConfig?.auto_settings;
              const embeddingConfig = (product as any).embedding_config;
              
              // Determine effective settings
              const effective = mode === 'manual' && manual
                ? manual
                : (resolved ?? auto ?? manual);
              
              const usingManual = mode === 'manual' && !!manual;
              const hasResolved = !!resolved;
              
              // Helper to copy JSON to clipboard
              const copyToClipboard = (text: string, label: string) => {
                navigator.clipboard.writeText(text).then(() => {
                  // You could add a toast notification here
                  alert(`Copied ${label} to clipboard`);
                }).catch(err => {
                  console.error('Failed to copy:', err);
                });
              };
              
              return (
                <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
                  <h4 className="text-sm font-medium text-gray-700 mb-3">Configuration Summary</h4>
                  
                  {/* Compact Summary - Always Visible */}
                  <div className="bg-white rounded-md p-3 mb-3 border border-gray-200">
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div>
                        <span className="text-gray-500">Playbook:</span>
                        <span className="ml-2 font-medium">{(product as any).playbook_id || 'Auto-Detect'}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Chunking Mode:</span>
                        <span className="ml-2 font-medium capitalize">{mode}</span>
                      </div>
                      <div>
                        <span className="text-gray-500">Optimization:</span>
                        <span className="ml-2 font-medium">{chunkingConfig?.optimization_mode || formData.optimization_mode || 'pattern'}</span>
                      </div>
                      {embeddingConfig && (
                        <div>
                          <span className="text-gray-500">Embedding:</span>
                          <span className="ml-2 font-medium">{embeddingConfig.embedder_name} ({embeddingConfig.embedding_dimension}D)</span>
                        </div>
                      )}
                    </div>
                    
                    {/* Effective Chunking Settings */}
                    {effective && (
                      <div className="mt-3 pt-3 border-t border-gray-200">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-medium text-gray-700">
                            Effective Chunking (Used by Pipeline)
                          </span>
                          {usingManual && (
                            <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                              Manual Override
                            </span>
                          )}
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
                          <div>Size: <strong>{effective.chunk_size ?? 'N/A'}</strong> {mode === 'manual' ? 'chars' : 'tokens'}</div>
                          <div>Overlap: <strong>{effective.chunk_overlap ?? 'N/A'}</strong> {mode === 'manual' ? 'chars' : 'tokens'}</div>
                          <div>Strategy: <strong>{effective.chunking_strategy ?? 'N/A'}</strong></div>
                          {effective.content_type && (
                            <div className="flex items-center gap-1">
                              Content Type: <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title="Semantic content type">{(effective as any).content_type.replace(/_/g, ' ')}</span>
                            </div>
                          )}
                          {(effective as any).source_quality && (
                            <div className="flex items-center gap-1">
                              Source Quality: <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700" title="How content was obtained (native PDF vs scanned/OCR)">{(effective as any).source_quality.replace(/_/g, ' ')}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                  
                  {/* Expandable Debug Sections */}
                  <details className="mb-2">
                    <summary className="cursor-pointer text-xs font-medium text-gray-600 hover:text-gray-800">
                      📋 Show Manual Settings {manual && `(${Object.keys(manual).length} fields)`}
                    </summary>
                    <div className="mt-2 p-2 bg-white rounded border border-gray-200">
                      {manual ? (
                        <>
                          <div className="flex justify-between items-center mb-2">
                            <span className="text-xs text-gray-600">Manual configuration (overrides detected settings)</span>
                            <button
                              onClick={() => copyToClipboard(JSON.stringify(manual, null, 2), 'Manual Settings')}
                              className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-700"
                            >
                              Copy JSON
                            </button>
                          </div>
                          <pre className="text-xs overflow-auto max-h-40 p-2 bg-gray-50 rounded">
                            {JSON.stringify(manual, null, 2)}
                          </pre>
                        </>
                      ) : (
                        <p className="text-xs text-gray-500 italic">No manual settings configured</p>
                      )}
                    </div>
                  </details>
                  
                  {hasResolved && (
                    <details className="mb-2">
                      <summary className="cursor-pointer text-xs font-medium text-gray-600 hover:text-gray-800">
                        🔍 Show Detected Settings {resolved && `(${usingManual ? 'not used' : 'effective'})`}
                      </summary>
                      <div className="mt-2 p-2 bg-white rounded border border-gray-200">
                        <div className="flex justify-between items-center mb-2">
                          <div>
                            <span className="text-xs text-gray-600">
                              {usingManual 
                                ? 'Auto-detected settings (shown for reference only - manual settings override)'
                                : 'Auto-detected settings (currently used by pipeline)'}
                            </span>
                            {resolved.confidence != null && (
                              <div className="mt-1 text-xs">
                                <span className="text-gray-600">Confidence: </span>
                                <span className={resolved.confidence >= 0.7 ? 'text-green-600 font-medium' : 'text-yellow-600 font-medium'}>
                                  {(resolved.confidence * 100).toFixed(0)}%
                                </span>
                                {resolved.confidence_threshold && (
                                  <span className="text-gray-500"> (threshold: {(resolved.confidence_threshold * 100).toFixed(0)}%)</span>
                                )}
                              </div>
                            )}
                          </div>
                          <button
                            onClick={() => copyToClipboard(JSON.stringify(resolved, null, 2), 'Detected Settings')}
                            className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-700"
                          >
                            Copy JSON
                          </button>
                        </div>
                        
                        {/* Level 1: Summary - two chips: Content Type + Source Quality */}
                        <div className="mb-2 p-2 bg-gray-50 rounded text-xs">
                          <div className="flex flex-wrap gap-2 mb-2">
                            <span className="inline-flex items-center gap-1">Content Type: <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title="Semantic type (medical, academic, etc.)">{(resolved as any).content_type?.replace(/_/g, ' ') || 'N/A'}</span></span>
                            <span className="inline-flex items-center gap-1">Source Quality: <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700" title="native_pdf | scanned_ocr | mixed">{(resolved as any).source_quality?.replace(/_/g, ' ') ?? ((product as any)?.extraction_type === 'scanned_pdf' ? 'scanned ocr' : (product as any)?.extraction_type === 'mixed' ? 'mixed' : 'native pdf')}</span></span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 mb-2">
                            <div>Chunk Size: <strong>{resolved.chunk_size ?? 'N/A'}</strong> tokens</div>
                            <div>Chunk Overlap: <strong>{resolved.chunk_overlap ?? 'N/A'}</strong> tokens</div>
                            <div>Strategy: <strong>{resolved.chunking_strategy ?? 'N/A'}</strong></div>
                          </div>
                          {resolved.reasoning && (
                            <p className="text-gray-600 italic border-t border-gray-200 pt-2 mt-2">
                              {resolved.reasoning}
                            </p>
                          )}
                        </div>
                        
                        {/* Level 2: Evidence (collapsible) */}
                        {resolved.evidence && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-xs font-medium text-gray-600 hover:text-gray-800">
                              📊 Show Evidence Details
                            </summary>
                            <div className="mt-2 p-2 bg-gray-50 rounded text-xs">
                              {resolved.evidence.all_scores && (
                                <div className="mb-2">
                                  <strong className="text-gray-700">Content Type Scores:</strong>
                                  <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1">
                                    {Object.entries(resolved.evidence.all_scores).map(([type, score]: [string, any]) => (
                                      <div key={type} className="flex items-center gap-2">
                                        <span className="capitalize text-gray-600">{type}:</span>
                                        <span className={type === resolved.evidence.final_type ? 'font-bold text-blue-600' : 'text-gray-900'}>
                                          {(score * 100).toFixed(1)}%
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              {resolved.evidence.matched_patterns && resolved.evidence.matched_patterns.length > 0 && (
                                <div className="mb-2">
                                  <strong className="text-gray-700">Matched Patterns:</strong>
                                  <div className="mt-1 flex flex-wrap gap-1">
                                    {resolved.evidence.matched_patterns.slice(0, 10).map((pattern: string, idx: number) => (
                                      <span key={idx} className="px-1.5 py-0.5 bg-blue-100 text-blue-800 rounded text-xs">
                                        {pattern}
                                      </span>
                                    ))}
                                    {resolved.evidence.matched_patterns.length > 10 && (
                                      <span className="text-gray-500 text-xs">
                                        +{resolved.evidence.matched_patterns.length - 10} more
                                      </span>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          </details>
                        )}
                        
                        {/* Level 3: Full JSON (collapsible) */}
                        <details className="mt-2">
                          <summary className="cursor-pointer text-xs font-medium text-gray-600 hover:text-gray-800">
                            📄 Show Raw JSON
                          </summary>
                          <pre className="mt-2 text-xs overflow-auto max-h-60 p-2 bg-gray-50 rounded border border-gray-200">
                            {JSON.stringify(resolved, null, 2)}
                          </pre>
                        </details>
                      </div>
                    </details>
                  )}
                  
                  {auto && !resolved && (
                    <details className="mb-2">
                      <summary className="cursor-pointer text-xs font-medium text-gray-600 hover:text-gray-800">
                        ⚙️ Show Auto Settings
                      </summary>
                      <div className="mt-2 p-2 bg-white rounded border border-gray-200">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-xs text-gray-600">Auto-detection configuration</span>
                          <button
                            onClick={() => copyToClipboard(JSON.stringify(auto, null, 2), 'Auto Settings')}
                            className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-700"
                          >
                            Copy JSON
                          </button>
                        </div>
                        <pre className="text-xs overflow-auto max-h-40 p-2 bg-gray-50 rounded">
                          {JSON.stringify(auto, null, 2)}
                        </pre>
                      </div>
                    </details>
                  )}
                  
                  {embeddingConfig && (
                    <details className="mb-2">
                      <summary className="cursor-pointer text-xs font-medium text-gray-600 hover:text-gray-800">
                        🤖 Show Embedding Config
                      </summary>
                      <div className="mt-2 p-2 bg-white rounded border border-gray-200">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-xs text-gray-600">Embedding model configuration</span>
                          <button
                            onClick={() => copyToClipboard(JSON.stringify(embeddingConfig, null, 2), 'Embedding Config')}
                            className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded text-gray-700"
                          >
                            Copy JSON
                          </button>
                        </div>
                        <pre className="text-xs overflow-auto p-2 bg-gray-50 rounded">
                          {JSON.stringify(embeddingConfig, null, 2)}
                        </pre>
                      </div>
                    </details>
                  )}
                  
                  <p className="mt-3 text-xs text-gray-500 italic">
                    {usingManual 
                      ? 'Manual settings override detected settings. Detected settings are shown for reference only.'
                      : hasResolved
                      ? 'Detected settings are currently used by the pipeline.'
                      : 'Configuration will be detected during the next pipeline run.'}
                  </p>
                </div>
              );
            })()}

            {/* Text Optimization Mode Section */}
            <div className="border-t border-gray-200 pt-6">
              <div className="flex items-center mb-4">
                <div className="bg-purple-100 rounded-lg p-2 mr-3">
                  <Sparkles className="h-5 w-5 text-purple-600" />
                </div>
                <div>
                  <h3 className="text-lg font-medium text-gray-900">Text Optimization Mode</h3>
                  <p className="text-sm text-gray-500">Choose how text is optimized for AI processing</p>
                </div>
              </div>

              <div className="space-y-4 mb-6">
                {/* Standard (Pattern-Based) */}
                <label className="flex items-start p-4 border-2 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                  style={{ borderColor: formData.optimization_mode === 'pattern' ? '#3b82f6' : '#e5e7eb' }}>
                  <input
                    type="radio"
                    name="optimization_mode"
                    value="pattern"
                    checked={formData.optimization_mode === 'pattern'}
                    onChange={(e) => handleInputChange('optimization_mode', e.target.value)}
                    className="mt-1 mr-3"
                  />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">Standard (Pattern-Based)</span>
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">Free, Fast</span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      Fast, free optimization using pattern matching. Handles 90% of common issues.
                    </p>
                    <div className="flex flex-wrap items-center gap-3 mt-2">
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                        <span>Recommended for most documents</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                        <span>No API costs</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                        <span>Instant processing</span>
                      </div>
                    </div>
                  </div>
                </label>

                {/* Hybrid (Auto) */}
                <label className="flex items-start p-4 border-2 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                  style={{ borderColor: formData.optimization_mode === 'hybrid' ? '#3b82f6' : '#e5e7eb' }}>
                  <input
                    type="radio"
                    name="optimization_mode"
                    value="hybrid"
                    checked={formData.optimization_mode === 'hybrid'}
                    onChange={(e) => handleInputChange('optimization_mode', e.target.value)}
                    className="mt-1 mr-3"
                  />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">Hybrid (Auto)</span>
                      <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">~$0.01/doc</span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      Pattern-based first, then AI enhancement when quality &lt; 75%. Best balance of speed, cost, and quality.
                    </p>
                    <div className="flex flex-wrap items-center gap-3 mt-2">
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                        <span>Pattern-based for most docs</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                        <span>AI only when needed</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                        <span>Cost-optimized</span>
                      </div>
                    </div>
                  </div>
                </label>

                {/* AI Enhancement (LLM) */}
                <label className="flex items-start p-4 border-2 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                  style={{ borderColor: formData.optimization_mode === 'llm' ? '#3b82f6' : '#e5e7eb' }}>
                  <input
                    type="radio"
                    name="optimization_mode"
                    value="llm"
                    checked={formData.optimization_mode === 'llm'}
                    onChange={(e) => handleInputChange('optimization_mode', e.target.value)}
                    className="mt-1 mr-3"
                  />
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">AI Enhancement (LLM)</span>
                      <span className="text-xs bg-purple-100 text-purple-800 px-2 py-1 rounded">~$0.02/doc</span>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      Best quality with semantic understanding. Uses OpenAI to enhance all documents.
                    </p>
                    <div className="flex flex-wrap items-center gap-3 mt-2">
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                        <span>Best quality</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <DollarSign className="h-3.5 w-3.5 text-amber-600" />
                        <span>Higher cost</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-600">
                        <Target className="h-3.5 w-3.5 text-purple-600" />
                        <span>For complex documents</span>
                      </div>
                    </div>
                  </div>
                </label>
              </div>

              {formData.optimization_mode !== 'pattern' && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
                  <div className="flex items-start">
                    <AlertCircle className="h-5 w-5 text-blue-600 mt-0.5 mr-2 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-blue-900 mb-1">
                        OpenAI API Key Required
                      </p>
                      <p className="text-sm text-blue-700">
                        {formData.optimization_mode === 'hybrid' 
                          ? 'Hybrid mode requires an OpenAI API key configured in Workspace Settings. AI enhancement will be used automatically when quality score is below 75%.'
                          : 'LLM mode requires an OpenAI API key configured in Workspace Settings. All documents will be enhanced using AI.'}
                      </p>
                      <p className="text-xs text-blue-600 mt-2 flex items-center gap-1.5">
                        <Sparkles className="h-3.5 w-3.5" />
                        <span>Go to <Link href="/app/settings" className="underline font-medium">Settings</Link> → Workspace Settings to configure your OpenAI API key.</span>
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Chunking Configuration Section */}
            <div className="border-t border-gray-200 pt-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center">
                  <div className="bg-green-100 rounded-lg p-2 mr-3">
                    <FileText className="h-5 w-5 text-green-600" />
                  </div>
                  <div>
                    <h3 className="text-lg font-medium text-gray-900">Chunking Configuration</h3>
                    <p className="text-sm text-gray-500">Configure how documents are split into chunks for processing</p>
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleAutoConfigure}
                  disabled={autoConfiguring}
                  className="ml-4"
                >
                  {autoConfiguring ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                      Analyzing...
                    </>
                  ) : (
                    <>
                      <Settings className="h-4 w-4 mr-2" />
                      Auto-Configure
                    </>
                  )}
                </Button>
              </div>

              {/* Chunking Mode Selection */}
              <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                  <Label htmlFor="chunking_mode" className="block text-sm font-medium text-gray-700">
                    Chunking Mode
                  </Label>
                  {formData.chunking_mode === 'auto' && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                      Auto-Detect
                    </span>
                  )}
                  {formData.chunking_mode === 'auto' && (product as any)?.chunking_config?.resolved_settings && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      Auto-Detected
                    </span>
                  )}
                </div>
                <div className="flex space-x-4">
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="chunking_mode"
                      value="auto"
                      checked={formData.chunking_mode === 'auto'}
                      onChange={(e) => handleInputChange('chunking_mode', e.target.value)}
                      className="mr-2"
                    />
                    <span className="text-sm">Auto (AI-Optimized)</span>
                  </label>
                  <label className="flex items-center">
                    <input
                      type="radio"
                      name="chunking_mode"
                      value="manual"
                      checked={formData.chunking_mode === 'manual'}
                      onChange={(e) => handleInputChange('chunking_mode', e.target.value)}
                      className="mr-2"
                    />
                    <span className="text-sm">Manual (Expert Control)</span>
                  </label>
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  {formData.chunking_mode === 'auto' 
                    ? 'AI will analyze your content and optimize chunking settings automatically during pipeline execution'
                    : 'You have full control over chunking parameters for fine-tuning'
                  }
                </p>
              </div>

              {/* Auto Mode Settings */}
              {formData.chunking_mode === 'auto' && (
                <div className="mb-6 p-4 bg-blue-50 rounded-lg">
                  <h4 className="text-sm font-medium text-blue-900 mb-3">Auto Configuration Settings</h4>
                  {(product as any)?.chunking_config?.resolved_settings ? (
                    <div className="mb-3 p-3 bg-green-50 border border-green-200 rounded-md">
                      <div className="flex items-start">
                        <Sparkles className="h-4 w-4 text-green-600 mt-0.5 mr-2 flex-shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-green-900 mb-2">
                            <span className="inline-flex items-center gap-2 flex-wrap">
                              <span>Content Type: <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800" title="Semantic content type">{(product as any).chunking_config.resolved_settings.content_type?.replace(/_/g, ' ') ?? 'N/A'}</span></span>
                              <span>Source Quality: <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-slate-200 text-slate-800" title="native_pdf | scanned_ocr | mixed">{((product as any).chunking_config.resolved_settings.source_quality ?? ((product as any)?.extraction_type === 'scanned_pdf' ? 'scanned_ocr' : (product as any)?.extraction_type === 'mixed' ? 'mixed' : 'native_pdf')).replace(/_/g, ' ')}</span></span>
                              {(product as any).chunking_config.resolved_settings.confidence != null && (
                                <span className="text-xs text-green-700">
                                  ({(Math.round((product as any).chunking_config.resolved_settings.confidence * 100))}% confidence)
                                </span>
                              )}
                            </span>
                          </p>
                          <div className="text-xs text-green-800 space-y-1 mt-2">
                            <p><strong>Detected Settings:</strong></p>
                            <ul className="list-disc list-inside ml-2 space-y-0.5">
                              <li>Chunk Size: {(product as any).chunking_config.resolved_settings.chunk_size} tokens</li>
                              <li>Chunk Overlap: {(product as any).chunking_config.resolved_settings.chunk_overlap} tokens</li>
                              <li>Strategy: {(product as any).chunking_config.resolved_settings.chunking_strategy}</li>
                              <li>Min Size: {(product as any).chunking_config.resolved_settings.min_chunk_size} tokens</li>
                              <li>Max Size: {(product as any).chunking_config.resolved_settings.max_chunk_size} tokens</li>
                            </ul>
                            {(product as any).chunking_config.resolved_settings.reasoning && (
                              <p className="mt-2 italic text-green-700">
                                {(product as any).chunking_config.resolved_settings.reasoning}
                              </p>
                            )}
                          </div>
                          <p className="text-xs text-green-700 mt-2">
                            These values were automatically detected from your content analysis. The settings below can be used to override defaults if needed.
                          </p>
                          {(product as any).chunking_config?.last_analyzed && (
                            <p className="text-xs text-green-600 mt-1">
                              Last analyzed: {new Date((product as any).chunking_config.last_analyzed).toLocaleString()}
                            </p>
                          )}
                          {(product as any).chunking_config?.sample_files_analyzed && (product as any).chunking_config.sample_files_analyzed.length > 0 && (
                            <p className="text-xs text-green-600 mt-1">
                              Analyzed {((product as any).chunking_config.sample_files_analyzed as any[]).length} sample file{((product as any).chunking_config.sample_files_analyzed as any[]).length !== 1 ? 's' : ''}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="mb-3 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                      <div className="flex items-start">
                        <AlertCircle className="h-4 w-4 text-yellow-600 mt-0.5 mr-2 flex-shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-yellow-900">
                            Auto-Detection Pending
                          </p>
                          <p className="text-xs text-yellow-700 mt-1">
                            Chunking configuration will be automatically detected during the next pipeline run by analyzing sample files from your data sources.
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="content_type" className="block text-sm font-medium text-gray-700 mb-2">
                        Content Type (semantic)
                      </Label>
                      <select
                        id="content_type"
                        value={formData.content_type}
                        onChange={(e) => handleInputChange('content_type', e.target.value)}
                        className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                      >
                        <option value="general">General</option>
                        <option value="medical">Medical/Clinical</option>
                        <option value="legal">Legal Documents</option>
                        <option value="regulatory">Regulatory/Compliance</option>
                        <option value="finance_banking">Finance/Banking</option>
                        <option value="code">Code</option>
                        <option value="documentation">Documentation</option>
                        <option value="conversation">Conversations</option>
                        <option value="academic">Academic Papers</option>
                        <option value="technical">Technical Content</option>
                      </select>
                    </div>
                    <div>
                      <Label htmlFor="confidence_threshold" className="block text-sm font-medium text-gray-700 mb-2">
                        Confidence Threshold
                      </Label>
                      <Input
                        id="confidence_threshold"
                        type="number"
                        value={formData.confidence_threshold}
                        onChange={(e) => handleInputChange('confidence_threshold', parseFloat(e.target.value) || 0.7)}
                        min="0.1"
                        max="1.0"
                        step="0.1"
                        className="mt-1"
                      />
                      <p className="mt-1 text-sm text-gray-500">
                        Minimum confidence level for auto-configuration (0.1 - 1.0)
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Chunking Parameters - Always visible but styled differently based on mode */}
              <div className={`grid grid-cols-1 md:grid-cols-2 gap-6 ${formData.chunking_mode === 'auto' ? 'opacity-60' : ''}`}>
                <div>
                  <Label htmlFor="chunking_strategy" className="block text-sm font-medium text-gray-700 mb-2">
                    Chunking Strategy
                    {formData.chunking_mode === 'auto' && <span className="text-xs text-gray-500 ml-2">(Auto-configured)</span>}
                  </Label>
                  <select
                    id="chunking_strategy"
                    value={formData.chunking_strategy}
                    onChange={(e) => handleInputChange('chunking_strategy', e.target.value)}
                    disabled={formData.chunking_mode === 'auto'}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm disabled:bg-gray-100 disabled:cursor-not-allowed"
                  >
                    <option value="fixed_size">Fixed Size</option>
                    <option value="semantic">Semantic</option>
                    <option value="recursive">Recursive</option>
                  </select>
                  <p className="mt-1 text-sm text-gray-500">
                    Fixed Size: Split by character count. Semantic: Split by meaning. Recursive: Hierarchical splitting.
                  </p>
                </div>

                <div>
                  <Label htmlFor="chunk_size" className="block text-sm font-medium text-gray-700 mb-2">
                    Chunk Size (characters)
                    {formData.chunking_mode === 'auto' && <span className="text-xs text-gray-500 ml-2">(Auto-configured)</span>}
                  </Label>
                  <Input
                    id="chunk_size"
                    type="text"
                    inputMode="numeric"
                    value={formData.chunk_size || ''}
                    onChange={(e) => handleNumberInputChange('chunk_size', e.target.value)}
                    onBlur={(e) => handleNumberInputBlur('chunk_size', e.target.value, 1000)}
                    disabled={formData.chunking_mode === 'auto'}
                    className={`${fieldErrors.chunk_size ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''} disabled:bg-gray-100 disabled:cursor-not-allowed`}
                    placeholder="1000"
                  />
                  {fieldErrors.chunk_size && (
                    <p className="mt-1 text-sm text-red-600">{fieldErrors.chunk_size}</p>
                  )}
                  <p className="mt-1 text-sm text-gray-500">
                    Target size for each chunk (50-5000 characters)
                  </p>
                </div>

                <div>
                  <Label htmlFor="chunk_overlap" className="block text-sm font-medium text-gray-700 mb-2">
                    Chunk Overlap (characters)
                    {formData.chunking_mode === 'auto' && <span className="text-xs text-gray-500 ml-2">(Auto-configured)</span>}
                  </Label>
                  <Input
                    id="chunk_overlap"
                    type="text"
                    inputMode="numeric"
                    value={formData.chunk_overlap || ''}
                    onChange={(e) => handleNumberInputChange('chunk_overlap', e.target.value)}
                    onBlur={(e) => handleNumberInputBlur('chunk_overlap', e.target.value, 200)}
                    disabled={formData.chunking_mode === 'auto'}
                    className={`${fieldErrors.chunk_overlap ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''} disabled:bg-gray-100 disabled:cursor-not-allowed`}
                    placeholder="200"
                  />
                  {fieldErrors.chunk_overlap && (
                    <p className="mt-1 text-sm text-red-600">{fieldErrors.chunk_overlap}</p>
                  )}
                  <p className="mt-1 text-sm text-gray-500">
                    Overlap between consecutive chunks (0 to chunk size - 1)
                  </p>
                </div>

                <div>
                  <Label htmlFor="min_chunk_size" className="block text-sm font-medium text-gray-700 mb-2">
                    Minimum Chunk Size (characters)
                    {formData.chunking_mode === 'auto' && <span className="text-xs text-gray-500 ml-2">(Auto-configured)</span>}
                  </Label>
                  <Input
                    id="min_chunk_size"
                    type="text"
                    inputMode="numeric"
                    value={formData.min_chunk_size || ''}
                    onChange={(e) => handleNumberInputChange('min_chunk_size', e.target.value)}
                    onBlur={(e) => handleNumberInputBlur('min_chunk_size', e.target.value, 100)}
                    disabled={formData.chunking_mode === 'auto'}
                    className={`${fieldErrors.min_chunk_size ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''} disabled:bg-gray-100 disabled:cursor-not-allowed`}
                    placeholder="100"
                  />
                  {fieldErrors.min_chunk_size && (
                    <p className="mt-1 text-sm text-red-600">{fieldErrors.min_chunk_size}</p>
                  )}
                  <p className="mt-1 text-sm text-gray-500">
                    Minimum acceptable chunk size (10 to chunk size)
                  </p>
                </div>

                <div>
                  <Label htmlFor="max_chunk_size" className="block text-sm font-medium text-gray-700 mb-2">
                    Maximum Chunk Size (characters)
                    {formData.chunking_mode === 'auto' && <span className="text-xs text-gray-500 ml-2">(Auto-configured)</span>}
                  </Label>
                  <Input
                    id="max_chunk_size"
                    type="text"
                    inputMode="numeric"
                    value={formData.max_chunk_size || ''}
                    onChange={(e) => handleNumberInputChange('max_chunk_size', e.target.value)}
                    onBlur={(e) => handleNumberInputBlur('max_chunk_size', e.target.value, 2000)}
                    disabled={formData.chunking_mode === 'auto'}
                    className={`${fieldErrors.max_chunk_size ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''} disabled:bg-gray-100 disabled:cursor-not-allowed`}
                    placeholder="2000"
                  />
                  {fieldErrors.max_chunk_size && (
                    <p className="mt-1 text-sm text-red-600">{fieldErrors.max_chunk_size}</p>
                  )}
                  <p className="mt-1 text-sm text-gray-500">
                    Maximum acceptable chunk size (chunk size to 10000)
                  </p>
                </div>
              </div>
            </div>

            {/* Embedding Configuration Section */}
            <div className="border-t border-gray-200 pt-6">
              <div className="flex items-center mb-4">
                <div className="bg-purple-100 rounded-lg p-2 mr-3">
                  <Settings className="h-5 w-5 text-purple-600" />
                </div>
                <div>
                  <h3 className="text-lg font-medium text-gray-900">Embedding Configuration</h3>
                  <p className="text-sm text-gray-500">Configure how text is converted to vector embeddings</p>
                </div>
              </div>

              {openaiEmbeddingsAvailable === false && (
                <div className="mb-4 text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
                  <strong>Local default mode:</strong> No OpenAI API key is configured for this workspace (and none on the
                  server). Paid OpenAI embedding models are disabled; use a local model such as MiniLM, or add a key in{' '}
                  <Link href="/app/settings" className="underline font-medium text-amber-950">
                    Workspace Settings
                  </Link>
                  .
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <Label htmlFor="embedder_name" className="block text-sm font-medium text-gray-700 mb-2">
                    Embedding Model
                  </Label>
                  <select
                    id="embedder_name"
                    value={formData.embedder_name}
                    onChange={(e) => handleInputChange('embedder_name', e.target.value)}
                    className={`mt-1 block w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm ${
                      fieldErrors.embedder_name ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : 'border-gray-300'
                    }`}
                  >
                    {embeddingModelOptions.length > 0 ? (
                      embeddingModelOptions.map((option) => (
                        <option key={option.value} value={option.value} disabled={option.disabled}>
                          {option.disabled ? `${option.label} (unavailable)` : option.label}
                        </option>
                      ))
                    ) : (
                      // Fallback while loading
                      getEmbeddingModelOptionsSync().map((option) => (
                        <option key={option.value} value={option.value} disabled={option.disabled}>
                          {option.disabled ? `${option.label} (unavailable)` : option.label}
                        </option>
                      ))
                    )}
                  </select>
                  {fieldErrors.embedder_name && (
                    <p className="mt-1 text-sm text-red-600">{fieldErrors.embedder_name}</p>
                  )}
                  {embeddingModelOptions.find((o) => o.value === formData.embedder_name)?.disabled && (
                    <p className="mt-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                      This model is not available without a configured API key.{' '}
                      <Link href="/app/settings" className="underline font-medium">
                        Open Workspace Settings
                      </Link>{' '}
                      to add your OpenAI key, or select a local model such as MiniLM.
                    </p>
                  )}
                  <p className="mt-1 text-sm text-gray-500">
                    Choose the embedding model for vector generation
                  </p>
                </div>

                <div>
                  <Label htmlFor="embedding_dimension" className="block text-sm font-medium text-gray-700 mb-2">
                    Embedding Dimension
                  </Label>
                  <Input
                    id="embedding_dimension"
                    type="number"
                    value={formData.embedding_dimension}
                    onChange={(e) => handleInputChange('embedding_dimension', parseInt(e.target.value) || 0)}
                    placeholder="384"
                    min="128"
                    max="2048"
                    disabled
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Vector dimension (automatically set based on model)
                  </p>
                </div>
              </div>
            </div>

            {/* Vector Creation Configuration Section */}
            <div className="border-t border-gray-200 pt-6">
              <div className="flex items-center mb-4">
                <div className="bg-green-100 rounded-lg p-2 mr-3">
                  <Sparkles className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <h3 className="text-lg font-medium text-gray-900">Vector Creation</h3>
                  <p className="text-sm text-gray-500">Control whether vectors/embeddings are created and indexed</p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <Label htmlFor="vector_creation_enabled" className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      id="vector_creation_enabled"
                      checked={formData.vector_creation_enabled}
                      onChange={(e) => handleInputChange('vector_creation_enabled', e.target.checked)}
                      disabled={saving}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="font-medium">Enable Vector Creation</span>
                  </Label>
                  <p className="mt-1 ml-6 text-sm text-gray-500">
                    When enabled, vectors/embeddings will be created and indexed in the vector database during pipeline runs. 
                    When disabled, the indexing stage will be skipped.
                  </p>
                </div>

                {product && (product as any).use_case_description && (
                  <div className="bg-gray-50 rounded-md p-3 border border-gray-200">
                    <Label className="block text-sm font-medium text-gray-700 mb-2">
                      Use Case Description (Read-only)
                    </Label>
                    <p className="text-sm text-gray-600 whitespace-pre-wrap">
                      {(product as any).use_case_description}
                    </p>
                    <p className="mt-2 text-xs text-gray-500">
                      This field can only be set during product creation.
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-end space-x-3 pt-6 border-t border-gray-200">
              <Link href={`/app/products/${productId}`}>
                <Button type="button" variant="outline" disabled={saving}>
                  <X className="h-4 w-4 mr-2" />
                  Cancel
                </Button>
              </Link>
              <Button type="submit" disabled={saving}>
                {saving ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Changes
                  </>
                )}
              </Button>
            </div>
          </form>
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
    </AppLayout>
  )
}
