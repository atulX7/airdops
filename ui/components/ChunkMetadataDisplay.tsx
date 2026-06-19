'use client'

import { useState, useEffect } from 'react'
import { Loader2, AlertCircle, Search, Filter, X, FileText, Hash, Tag, Calendar } from 'lucide-react'
import { apiClient, ChunkMetadata } from '@/lib/api-client'
import { useToast } from './ui/toast'
import { Button } from './ui/button'

interface ChunkMetadataDisplayProps {
  productId: string
  productVersion?: number
  showTitle?: boolean
}

export function ChunkMetadataDisplay({ productId, productVersion, showTitle = true }: ChunkMetadataDisplayProps) {
  const [metadata, setMetadata] = useState<ChunkMetadata[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [totalCount, setTotalCount] = useState(0)
  const { addToast } = useToast()

  // Filter state
  const [filters, setFilters] = useState({
    version: productVersion,
    section: '',
    field_name: '',
    limit: 100,
    offset: 0,
  })
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    loadMetadata()
  }, [productId, filters.version, filters.section, filters.field_name, filters.limit, filters.offset])

  const loadMetadata = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.getChunkMetadata(productId, {
        version: filters.version,
        section: filters.section || undefined,
        field_name: filters.field_name || undefined,
        limit: filters.limit,
        offset: filters.offset,
      })
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load chunk metadata: ${response.error}`,
        })
      } else if (response.data) {
        setMetadata(response.data)
        // Estimate total count (if we got fewer results than limit, that's the total)
        if (response.data.length < filters.limit) {
          setTotalCount(filters.offset + response.data.length)
        } else {
          // We might have more, but we don't know the exact count
          setTotalCount(filters.offset + response.data.length + 1) // +1 to indicate there might be more
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load chunk metadata'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = (key: string, value: string | number) => {
    setFilters(prev => ({
      ...prev,
      [key]: value,
      offset: 0, // Reset offset when filters change
    }))
  }

  const clearFilters = () => {
    setFilters({
      version: productVersion,
      section: '',
      field_name: '',
      limit: 100,
      offset: 0,
    })
  }

  const hasActiveFilters = filters.section || filters.field_name

  const handlePreviousPage = () => {
    if (filters.offset > 0) {
      setFilters(prev => ({
        ...prev,
        offset: Math.max(0, prev.offset - prev.limit),
      }))
    }
  }

  const handleNextPage = () => {
    if (metadata.length === filters.limit) {
      setFilters(prev => ({
        ...prev,
        offset: prev.offset + prev.limit,
      }))
    }
  }

  const getScoreColor = (score?: number) => {
    if (score === undefined || score === null) return 'text-gray-600'
    if (score >= 0.8) return 'text-green-600'
    if (score >= 0.6) return 'text-yellow-600'
    return 'text-red-600'
  }

  if (loading && metadata.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Chunk Metadata</h2>}
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 text-gray-400 animate-spin mr-2" />
          <p className="text-gray-600">Loading chunk metadata...</p>
        </div>
      </div>
    )
  }

  if (error && metadata.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Chunk Metadata</h2>}
        <div className="flex items-center justify-center py-8">
          <AlertCircle className="h-6 w-6 text-red-500 mr-2" />
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      {showTitle && (
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Chunk Metadata</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-2"
          >
            <Filter className="h-4 w-4" />
            Filters
            {hasActiveFilters && (
              <span className="ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-100 text-blue-800 text-xs">
                {[filters.section, filters.field_name].filter(Boolean).length}
              </span>
            )}
          </Button>
        </div>
      )}

      {/* Filters */}
      {showFilters && (
        <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-gray-900">Filter Options</h3>
            {hasActiveFilters && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearFilters}
                className="text-xs"
              >
                <X className="h-3 w-3 mr-1" />
                Clear
              </Button>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Section
              </label>
              <input
                type="text"
                value={filters.section}
                onChange={(e) => handleFilterChange('section', e.target.value)}
                placeholder="Filter by section..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Field Name
              </label>
              <input
                type="text"
                value={filters.field_name}
                onChange={(e) => handleFilterChange('field_name', e.target.value)}
                placeholder="Filter by field name..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Results per Page
              </label>
              <select
                value={filters.limit}
                onChange={(e) => handleFilterChange('limit', parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Metadata Table */}
      {metadata.length === 0 ? (
        <div className="text-center py-8">
          <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No chunk metadata found</h3>
          <p className="text-gray-600">
            {hasActiveFilters
              ? 'Try adjusting your filters or run a pipeline to generate metadata.'
              : 'Run a pipeline to generate chunk metadata.'}
          </p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Chunk ID
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Score
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Source File
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Page
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Section
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Field
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {metadata.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-gray-900">
                      <div className="flex items-center gap-2">
                        <Hash className="h-4 w-4 text-gray-400" />
                        <span className="truncate max-w-xs">{item.chunk_id}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm">
                      {item.score !== undefined && item.score !== null ? (() => {
                        // Handle both 0-1 (decimal) and 0-100 (percentage) formats
                        const score = item.score
                        const percentage = score > 1 ? score : score * 100
                        const normalizedScore = score > 1 ? score / 100 : score
                        return (
                          <span className={`font-semibold ${getScoreColor(normalizedScore)}`}>
                            {percentage.toFixed(1)}%
                          </span>
                        )
                      })() : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {item.source_file ? (
                        <div className="flex items-center gap-2 max-w-xs">
                          <FileText className="h-4 w-4 text-gray-400 flex-shrink-0" />
                          <span className="truncate">{item.source_file}</span>
                        </div>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                      {item.page_number !== undefined && item.page_number !== null ? (
                        item.page_number
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {item.section ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                          {item.section}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {item.field_name ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                          <Tag className="h-3 w-3 mr-1" />
                          {item.field_name}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="mt-4 flex items-center justify-between">
            <div className="text-sm text-gray-600">
              Showing {filters.offset + 1} to {filters.offset + metadata.length}
              {totalCount > filters.offset + metadata.length && ` of ${totalCount}+`}
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePreviousPage}
                disabled={filters.offset === 0 || loading}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleNextPage}
                disabled={metadata.length < filters.limit || loading}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}




