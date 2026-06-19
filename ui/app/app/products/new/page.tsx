'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { ArrowLeft, Package, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { PlaybookSelector } from '@/components/PlaybookSelector'
import { useToast } from '@/components/ui/toast'

export default function NewProductPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [name, setName] = useState('')
  const [playbookId, setPlaybookId] = useState<string | undefined>(undefined)
  const [documentType, setDocumentType] = useState<string>('auto')
  const [chunkingMode, setChunkingMode] = useState<'auto' | 'manual'>('auto')
  const [chunkingStrategy, setChunkingStrategy] = useState('sentence')
  const [chunkSize, setChunkSize] = useState(1000)
  const [chunkOverlap, setChunkOverlap] = useState(200)
  const [vectorCreationEnabled, setVectorCreationEnabled] = useState(true)
  const [useCaseDescription, setUseCaseDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [loadingWorkspace, setLoadingWorkspace] = useState(true)

  // Get user's default workspace
  useEffect(() => {
    const getUserWorkspace = async () => {
      try {
        setLoadingWorkspace(true)
        setError(null)
        
        // First, try to get workspaces from the API
        const workspacesResponse = await apiClient.getWorkspaces()
        
        if (workspacesResponse.data && workspacesResponse.data.length > 0) {
          // Use the first workspace
          setWorkspaceId(workspacesResponse.data[0].id)
          setLoadingWorkspace(false)
          return
        }
        
        // If no workspaces, create a new one
        try {
          const createResponse = await apiClient.createWorkspace()
          if (createResponse.data && createResponse.data.id) {
            setWorkspaceId(createResponse.data.id)
            setLoadingWorkspace(false)
            return
          }
        } catch (createErr) {
          console.error('Failed to create workspace:', createErr)
          // Continue to show error below
        }
        
        // If we still don't have a workspace ID, show error
        setError('No workspace found. Please contact support.')
        setLoadingWorkspace(false)
      } catch (err) {
        console.error('Error fetching workspace:', err)
        setError('Failed to load workspace. Please refresh the page.')
        setLoadingWorkspace(false)
      }
    }

    if (status === 'authenticated') {
      getUserWorkspace()
    }
  }, [status])

  // Map document type to playbook (semantic content types only; extraction_type is set by pipeline)
  const getPlaybookFromDocumentType = (docType: string): string | undefined => {
    const mapping: Record<string, string> = {
      'structured': 'TECH',
      'regulatory': 'REGULATORY',
      'healthcare': 'HEALTHCARE',
      'financial': 'FINANCIAL',
      'academic': 'ACADEMIC',
      'legal': 'LEGAL',
      'ecommerce': 'ECOMMERCE'
    }
    return mapping[docType]
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!name.trim()) {
      setError('Product name is required')
      return
    }

    if (!workspaceId) {
      setError('Workspace not found. Please try again.')
      return
    }

    try {
      setLoading(true)
      setError(null)
      
      // Determine final playbook ID
      const finalPlaybookId = documentType !== 'auto' 
        ? getPlaybookFromDocumentType(documentType)
        : playbookId
      
      // Build chunking config
      const chunkingConfig = chunkingMode === 'manual' ? {
        mode: 'manual',
        manual_settings: {
          chunking_strategy: chunkingStrategy, // Preserve: 'semantic', 'fixed_size', or 'sentence'
          chunk_size: typeof chunkSize === 'number' ? chunkSize : parseInt(String(chunkSize || 1000), 10),
          chunk_overlap: typeof chunkOverlap === 'number' ? chunkOverlap : parseInt(String(chunkOverlap || 200), 10),
          min_chunk_size: 100,
          max_chunk_size: 2000
        }
      } : {
        mode: 'auto',
        auto_settings: {
          content_type: 'general',  // Default, playbook will determine actual settings
          model_optimized: true,
          confidence_threshold: 0.7
        }
      }
      
      const response = await apiClient.createProduct({
        workspace_id: workspaceId,
        name: name.trim(),
        playbook_id: finalPlaybookId || null,
        chunking_config: chunkingConfig || null,
        vector_creation_enabled: vectorCreationEnabled,
        use_case_description: useCaseDescription.trim() || null,
      })
      
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to create product: ${response.error}`,
        })
      } else {
        // Invalidate products cache to refresh the list
        queryClient.invalidateQueries({ queryKey: ['products'] })
        // Also emit event for immediate update (if products page is open)
        window.dispatchEvent(new CustomEvent('productCreated'))
        
        addToast({
          type: 'success',
          message: `Product "${name.trim()}" created successfully${playbookId ? ` with playbook ${playbookId}` : ''}`,
        })
        // Redirect to the new product page
        const product = response.data as any
        router.push(`/app/products/${product?.id}`)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to create product'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: `Failed to create product: ${errorMessage}`,
      })
    } finally {
      setLoading(false)
    }
  }

  if (status === 'loading' || loadingWorkspace) {
    return (
      <AppLayout>
        <div className="p-6 flex items-center justify-center min-h-96">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-600">Loading...</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (status === 'unauthenticated') {
    router.push('/')
    return null
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
          <span className="text-sm font-semibold text-gray-900">Create New</span>
        </div>

        {/* Enhanced Page Header */}
        <div className="mb-8">
          <div>
            <h1 className="text-4xl font-bold text-gray-900 mb-2 tracking-tight">Create New Product</h1>
            <p className="text-lg text-gray-600">Set up a new data product in your workspace</p>
          </div>
        </div>

        {/* Enhanced Content */}
        <div className="max-w-2xl">
        <div className="bg-white rounded-xl shadow-md border border-gray-100 p-8">
          <div className="flex items-center mb-8">
            <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-3 mr-4 shadow-sm">
              <Package className="h-6 w-6 text-white" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-gray-900">Product Details</h2>
              <p className="text-sm text-gray-600">Give your product a name to get started</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <Label htmlFor="name">Product Name</Label>
              <Input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Customer Analytics Pipeline"
                className="mt-1"
                required
              />
              <p className="mt-1 text-sm text-gray-500">
                Choose a descriptive name for your data product
              </p>
            </div>

            <div>
              <Label htmlFor="use-case-description">Use Case Description (Optional)</Label>
              <textarea
                id="use-case-description"
                value={useCaseDescription}
                onChange={(e) => setUseCaseDescription(e.target.value)}
                placeholder="Describe the use case for this product..."
                className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-white min-h-[100px]"
                disabled={loading}
                rows={4}
              />
              <p className="mt-1 text-sm text-gray-500">
                Optional description of the use case for this product. This can only be set during creation.
              </p>
            </div>

            <div>
              <Label htmlFor="vector-creation-enabled" className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  id="vector-creation-enabled"
                  checked={vectorCreationEnabled}
                  onChange={(e) => setVectorCreationEnabled(e.target.checked)}
                  disabled={loading}
                  className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                />
                <span className="font-medium">Enable Vector Creation</span>
              </Label>
              <p className="mt-1 ml-6 text-sm text-gray-500">
                Enable vector/embedding creation and indexing in the vector database during pipeline runs. Uncheck to skip vector creation.
              </p>
            </div>

            <div>
              <Label htmlFor="document-type">Document Type</Label>
              <select
                id="document-type"
                value={documentType}
                onChange={(e) => {
                  setDocumentType(e.target.value)
                  // Auto-select playbook when document type changes (unless auto-detect)
                  if (e.target.value !== 'auto') {
                    const mappedPlaybook = getPlaybookFromDocumentType(e.target.value)
                    setPlaybookId(mappedPlaybook)
                  } else {
                    setPlaybookId(undefined)
                  }
                }}
                className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-white"
                disabled={loading}
              >
                <option value="auto">Auto-detect (Recommended)</option>
                <option value="structured">Structured Document</option>
                <option value="regulatory">Regulatory/Formal</option>
                <option value="healthcare">Medical/Healthcare</option>
                <option value="financial">Financial</option>
                <option value="academic">Academic/Research</option>
                <option value="legal">Legal</option>
                <option value="ecommerce">E-commerce</option>
              </select>
              <p className="mt-1 text-sm text-gray-500">
                Select document type to auto-select appropriate preprocessing playbook. Leave as Auto-detect to analyze content automatically.
              </p>
            </div>

            {documentType === 'auto' && (
              <PlaybookSelector
                value={playbookId}
                onChange={setPlaybookId}
                disabled={loading}
              />
            )}
            {documentType !== 'auto' && playbookId && (
              <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
                <p className="text-sm text-blue-800">
                  <strong>Selected Playbook:</strong> {playbookId}
                </p>
                <p className="text-xs text-blue-600 mt-1">
                  Playbook automatically selected based on document type. You can switch to "Auto-detect" to manually select a playbook.
                </p>
              </div>
            )}

            <div className="space-y-4 pt-4 border-t border-gray-200">
              <div>
                <Label>Chunking Configuration</Label>
                <div className="mt-2 space-y-3">
                  <div className="flex items-center space-x-2">
                    <input
                      type="radio"
                      id="chunking-auto"
                      value="auto"
                      checked={chunkingMode === 'auto'}
                      onChange={(e) => setChunkingMode(e.target.value as 'auto' | 'manual')}
                      disabled={loading}
                      className="w-4 h-4 text-blue-600"
                    />
                    <Label htmlFor="chunking-auto" className="font-normal cursor-pointer">Auto (Recommended)</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <input
                      type="radio"
                      id="chunking-manual"
                      value="manual"
                      checked={chunkingMode === 'manual'}
                      onChange={(e) => setChunkingMode(e.target.value as 'auto' | 'manual')}
                      disabled={loading}
                      className="w-4 h-4 text-blue-600"
                    />
                    <Label htmlFor="chunking-manual" className="font-normal cursor-pointer">Manual Configuration</Label>
                  </div>
                </div>
              </div>

              {chunkingMode === 'auto' && (
                <div className="ml-6 space-y-4 border-l-2 border-gray-200 pl-4">
                  <div className="bg-gray-50 rounded-md p-3">
                    <p className="text-sm text-gray-700">
                      <strong>Auto-chunking mode:</strong> Chunking settings will be automatically determined by the selected playbook.
                    </p>
                    <p className="text-xs text-gray-600 mt-1">
                      Each playbook has optimized chunking settings for its document type. Switch to Manual mode to customize.
                    </p>
                  </div>
                </div>
              )}

              {chunkingMode === 'manual' && (
                <div className="ml-6 space-y-4 border-l-2 border-gray-200 pl-4">
                  <div>
                    <Label htmlFor="chunking-strategy">Chunking Strategy</Label>
                    <select
                      id="chunking-strategy"
                      value={chunkingStrategy}
                      onChange={(e) => setChunkingStrategy(e.target.value)}
                      className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-white"
                      disabled={loading}
                    >
                      <option value="sentence">Sentence-based (Recommended)</option>
                      <option value="fixed_size">Fixed Size</option>
                      <option value="semantic">Semantic (Advanced)</option>
                    </select>
                    <p className="mt-1 text-sm text-gray-500">
                      Sentence-based preserves context better for most documents
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="chunk-size">Chunk Size (tokens)</Label>
                      <Input
                        id="chunk-size"
                        type="text"
                        inputMode="numeric"
                        value={chunkSize || ''}
                        onChange={(e) => {
                          const cleaned = e.target.value.replace(/[^0-9]/g, '')
                          if (cleaned === '') {
                            setChunkSize('' as any)
                          } else {
                            const numValue = parseInt(cleaned, 10)
                            if (!isNaN(numValue) && numValue >= 0) {
                              setChunkSize(numValue)
                            }
                          }
                        }}
                        onBlur={(e) => {
                          if (e.target.value === '' || parseInt(e.target.value) < 100) {
                            setChunkSize(1000)
                          }
                        }}
                        className="mt-1"
                        disabled={loading}
                        placeholder="1000"
                      />
                      <p className="mt-1 text-sm text-gray-500">
                        Recommended: 800-1200 for most documents
                      </p>
                    </div>

                    <div>
                      <Label htmlFor="chunk-overlap">Overlap (tokens)</Label>
                      <Input
                        id="chunk-overlap"
                        type="text"
                        inputMode="numeric"
                        value={chunkOverlap || ''}
                        onChange={(e) => {
                          const cleaned = e.target.value.replace(/[^0-9]/g, '')
                          if (cleaned === '') {
                            setChunkOverlap('' as any)
                          } else {
                            const numValue = parseInt(cleaned, 10)
                            if (!isNaN(numValue) && numValue >= 0) {
                              setChunkOverlap(numValue)
                            }
                          }
                        }}
                        onBlur={(e) => {
                          if (e.target.value === '' || parseInt(e.target.value) < 0) {
                            setChunkOverlap(200)
                          }
                        }}
                        min={0}
                        max={500}
                        className="mt-1"
                        disabled={loading}
                      />
                      <p className="mt-1 text-sm text-gray-500">
                        Recommended: 150-300 for better context
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {error && (
              <div className="bg-red-50 border-2 border-red-200 rounded-xl p-4 shadow-sm">
                <p className="text-sm font-medium text-red-600">{error}</p>
              </div>
            )}

            <div className="flex justify-end space-x-3 pt-6 border-t border-gray-200">
              <Link href="/app/products">
                <Button type="button" variant="outline" className="border-2 hover:border-gray-300 hover:bg-gray-50">
                  Cancel
                </Button>
              </Link>
              <Button 
                type="submit" 
                disabled={loading || !name.trim() || !workspaceId}
                className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Product'
                )}
              </Button>
            </div>
          </form>
        </div>
        </div>
      </div>
    </AppLayout>
  )
}
