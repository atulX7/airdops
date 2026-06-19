'use client'

import { useState } from 'react'
import { X, Eye, Download, FileJson, FileSpreadsheet, FileText, Layers, Package, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getApiUrl } from '@/lib/config'

interface Artifact {
  id: string
  artifact_name: string
  display_name?: string
  artifact_type: string
  file_size?: number
  download_url?: string
  stage_name?: string
}

interface ArtifactsModalProps {
  isOpen: boolean
  onClose: () => void
  artifacts: Artifact[]
  loading?: boolean
}

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

export default function ArtifactsModal({
  isOpen,
  onClose,
  artifacts,
  loading = false,
}: ArtifactsModalProps) {
  const [viewingArtifact, setViewingArtifact] = useState<Artifact | null>(null)
  const [artifactContent, setArtifactContent] = useState<string | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)

  const handleDownload = async (artifact: Artifact) => {
    if (!artifact.download_url) return
    
    // For GCS signed URLs, use direct download (skip fetch to avoid CORS issues)
    // GCS signed URLs with response-content-disposition=attachment work better with direct links
    if (artifact.download_url.includes('storage.googleapis.com') || 
        artifact.download_url.includes('X-Goog-Signature')) {
      // Direct download for GCS URLs
      const a = document.createElement('a')
      a.href = artifact.download_url
      a.download = artifact.display_name || artifact.artifact_name || 'artifact'
      a.target = '_blank' // Open in new tab as fallback if download attribute doesn't work
      a.style.display = 'none'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      return
    }
    
    try {
      // For non-GCS URLs (MinIO), use fetch approach
      const response = await fetch(artifact.download_url)
      
      if (!response.ok) {
        throw new Error('Download failed')
      }
      
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = artifact.display_name || artifact.artifact_name || 'artifact'
      a.style.display = 'none'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      console.error('Download failed:', err)
      // Fallback: try direct link (may open in new tab for cross-origin URLs)
      const a = document.createElement('a')
      a.href = artifact.download_url
      a.download = artifact.display_name || artifact.artifact_name || 'artifact'
      a.target = '_blank'
      a.style.display = 'none'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }

  const handleView = async (artifact: Artifact) => {
    if (artifact.artifact_type?.toLowerCase() === 'vector') {
      setArtifactContent('Vector artifacts are stored in the vector database. Use the Playground to query them.')
      setViewingArtifact(artifact)
      return
    }

    if (!artifact.id) {
      setArtifactContent('Artifact ID is missing.')
      setViewingArtifact(artifact)
      return
    }

    setLoadingContent(true)
    setViewingArtifact(artifact)
    setArtifactContent(null)

    try {
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
      
      const response = await fetch(`${apiUrl}/api/v1/pipeline/artifacts/${artifact.id}/content`, {
        method: 'GET',
        headers,
        // Removed credentials: 'include' - using Authorization header only
      })

      if (!response.ok) {
        // Try to get error message from response
        let errorMessage = `Failed to fetch artifact (${response.status})`
        try {
          const errorData = await response.json()
          if (errorData.detail) {
            errorMessage = errorData.detail
          } else if (errorData.message) {
            errorMessage = errorData.message
          }
        } catch {
          // If JSON parsing fails, try text
          try {
            const errorText = await response.text()
            if (errorText) {
              errorMessage = errorText
            }
          } catch {
            // Use default error message
          }
        }
        throw new Error(errorMessage)
      }

      const contentType = response.headers.get('content-type') || ''
      
      if (contentType.includes('application/json') || artifact.artifact_type?.toLowerCase() === 'json') {
        const json = await response.json()
        setArtifactContent(JSON.stringify(json, null, 2))
      } else if (contentType.includes('text/csv') || artifact.artifact_type?.toLowerCase() === 'csv') {
        const text = await response.text()
        setArtifactContent(text)
      } else if (contentType.includes('application/pdf') || artifact.artifact_type?.toLowerCase() === 'pdf') {
        setArtifactContent('PDF files cannot be displayed inline. Please download to view.')
      } else {
        const text = await response.text()
        setArtifactContent(text)
      }
    } catch (err) {
      console.error('Failed to fetch artifact:', err)
      const errorMessage = err instanceof Error ? err.message : 'Failed to load artifact content.'
      setArtifactContent(`Error: ${errorMessage}`)
    } finally {
      setLoadingContent(false)
    }
  }

  if (!isOpen) return null

  return (
    <div>
      <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
        <div className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onClick={onClose} />
        
        <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Package className="h-5 w-5 text-white" />
              <h3 className="text-lg font-semibold text-white">Pipeline Artifacts</h3>
              {artifacts.length > 0 && (
                <span className="px-2 py-0.5 text-xs font-medium bg-white/20 rounded-full text-white">
                  {artifacts.length} {artifacts.length === 1 ? 'artifact' : 'artifacts'}
                </span>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-white hover:text-gray-200 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          
          <div className="px-6 py-4 max-h-[70vh] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
              </div>
            ) : artifacts.length === 0 ? (
              <div className="text-center py-12">
                <Package className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600">No artifacts available</p>
              </div>
            ) : (
              <div className="space-y-2">
                {artifacts.map((artifact) => (
                  <div
                    key={artifact.id}
                    className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      {getArtifactIcon(artifact.artifact_type)}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {artifact.display_name || artifact.artifact_name?.replace(/_/g, ' ') || 'Unknown'}
                        </p>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-800">
                            {artifact.artifact_type?.toUpperCase() || 'UNKNOWN'}
                          </span>
                          {artifact.file_size && (
                            <span className="text-xs text-gray-500">
                              {formatFileSize(artifact.file_size)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        onClick={() => handleView(artifact)}
                        title="View artifact"
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      {artifact.download_url && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={() => handleDownload(artifact)}
                          title="Download artifact"
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          <div className="bg-gray-50 px-6 py-3 flex justify-end">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </div>
      </div>

      {/* View Artifact Content Modal */}
      {viewingArtifact && (
        <div className="fixed inset-0 z-[60] overflow-y-auto">
          <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
            <div className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onClick={() => setViewingArtifact(null)} />
            
            <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-4xl sm:w-full">
              <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {getArtifactIcon(viewingArtifact.artifact_type)}
                  <h3 className="text-lg font-semibold text-white">
                    {viewingArtifact.display_name || viewingArtifact.artifact_name?.replace(/_/g, ' ') || 'Artifact'}
                  </h3>
                </div>
                <button
                  onClick={() => setViewingArtifact(null)}
                  className="text-white hover:text-gray-200 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              
              <div className="px-6 py-4 max-h-[70vh] overflow-y-auto">
                {loadingContent ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
                  </div>
                ) : artifactContent ? (
                  <pre className="bg-gray-50 p-4 rounded-lg overflow-x-auto text-sm font-mono">
                    {artifactContent}
                  </pre>
                ) : (
                  <p className="text-gray-600">No content available</p>
                )}
              </div>
              
              <div className="bg-gray-50 px-6 py-3 flex justify-end gap-2">
                {viewingArtifact.download_url && (
                  <Button
                    variant="outline"
                    onClick={() => handleDownload(viewingArtifact)}
                  >
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </Button>
                )}
                <Button variant="outline" onClick={() => setViewingArtifact(null)}>
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

