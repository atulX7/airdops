'use client'

import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ChunkingConfigModalProps {
  isOpen: boolean
  onClose: () => void
  config: {
    chunk_size?: number
    chunk_overlap?: number
    min_chunk_size?: number
    max_chunk_size?: number
    chunking_strategy?: string
    content_type?: string
    mode?: string
    source?: string
  } | null
}

export default function ChunkingConfigModal({
  isOpen,
  onClose,
  config,
}: ChunkingConfigModalProps) {
  if (!isOpen) return null

  // Check if config is empty (no properties)
  const hasConfig = config && Object.keys(config).length > 0

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20 text-center sm:block sm:p-0">
        <div className="fixed inset-0 transition-opacity bg-gray-500 bg-opacity-75" onClick={onClose} />
        
        <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-2xl sm:w-full">
          <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4 flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white">Chunking Configuration</h3>
            <button
              onClick={onClose}
              className="text-white hover:text-gray-200 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          
          <div className="px-6 py-4">
            {hasConfig ? (
              <dl className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
              {config.chunk_size && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Chunk Size</dt>
                  <dd className="mt-1 text-sm text-gray-900">{config.chunk_size}</dd>
                </div>
              )}
              {config.chunk_overlap !== undefined && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Chunk Overlap</dt>
                  <dd className="mt-1 text-sm text-gray-900">{config.chunk_overlap}</dd>
                </div>
              )}
              {config.min_chunk_size && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Min Chunk Size</dt>
                  <dd className="mt-1 text-sm text-gray-900">{config.min_chunk_size}</dd>
                </div>
              )}
              {config.max_chunk_size && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Max Chunk Size</dt>
                  <dd className="mt-1 text-sm text-gray-900">{config.max_chunk_size}</dd>
                </div>
              )}
              {config.chunking_strategy && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Strategy</dt>
                  <dd className="mt-1">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {config.chunking_strategy.replace(/_/g, ' ')}
                    </span>
                  </dd>
                </div>
              )}
              {config.content_type && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Content Type</dt>
                  <dd className="mt-1">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800 capitalize">
                      {config.content_type}
                    </span>
                  </dd>
                </div>
              )}
              {config.mode && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Mode</dt>
                  <dd className="mt-1 text-sm text-gray-900 capitalize">{config.mode}</dd>
                </div>
              )}
              {config.source && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">Source</dt>
                  <dd className="mt-1 text-sm text-gray-900 capitalize">{config.source.replace(/_/g, ' ')}</dd>
                </div>
              )}
              </dl>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <p>Chunking configuration is not available for this pipeline run.</p>
              </div>
            )}
          </div>
          
          <div className="bg-gray-50 px-6 py-3 flex justify-end">
            <Button
              variant="outline"
              onClick={onClose}
            >
              Close
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

