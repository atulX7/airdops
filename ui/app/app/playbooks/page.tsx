'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, BookOpen, Loader2, AlertCircle, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient, PlaybookInfo, PlaybookResponse } from '@/lib/api-client'
import { useToast } from '@/components/ui/toast'

export default function PlaybooksPage() {
  const router = useRouter()
  const { addToast } = useToast()
  const [playbooks, setPlaybooks] = useState<PlaybookInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedPlaybook, setSelectedPlaybook] = useState<PlaybookResponse | null>(null)
  const [loadingDetails, setLoadingDetails] = useState<string | null>(null)

  useEffect(() => {
    loadPlaybooks()
  }, [])

  const loadPlaybooks = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.listPlaybooks()
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load playbooks: ${response.error}`,
        })
      } else if (response.data) {
        setPlaybooks(response.data)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load playbooks'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const loadPlaybookDetails = async (playbookId: string) => {
    if (selectedPlaybook?.id === playbookId) {
      setSelectedPlaybook(null)
      return
    }

    setLoadingDetails(playbookId)
    try {
      const response = await apiClient.getPlaybook(playbookId)
      if (response.error) {
        addToast({
          type: 'error',
          message: `Failed to load playbook details: ${response.error}`,
        })
      } else if (response.data) {
        setSelectedPlaybook(response.data)
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to load playbook details',
      })
    } finally {
      setLoadingDetails(null)
    }
  }

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-6">
          <Link
            href="/app/products"
            className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900 mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Products
          </Link>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Preprocessing Playbooks</h1>
              <p className="mt-2 text-sm text-gray-600">
                View and manage preprocessing playbooks for different document types
              </p>
            </div>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-center">
              <AlertCircle className="h-5 w-5 text-red-600 mr-2" />
              <p className="text-sm text-red-800">{error}</p>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <Loader2 className="h-8 w-8 text-gray-400 animate-spin mx-auto mb-4" />
            <p className="text-gray-600">Loading playbooks...</p>
          </div>
        ) : playbooks.length === 0 ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
            <BookOpen className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No playbooks available</h3>
            <p className="text-gray-600">
              No preprocessing playbooks are currently configured.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Playbooks List */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">Available Playbooks</h2>
              </div>
              <div className="divide-y divide-gray-200">
                {playbooks.map((playbook) => (
                  <button
                    key={playbook.id}
                    onClick={() => loadPlaybookDetails(playbook.id)}
                    className="w-full px-6 py-4 text-left hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <BookOpen className="h-5 w-5 text-blue-600" />
                          <h3 className="text-sm font-medium text-gray-900">{playbook.id}</h3>
                        </div>
                        <p className="mt-1 text-sm text-gray-600">{playbook.description}</p>
                      </div>
                      {loadingDetails === playbook.id ? (
                        <Loader2 className="h-5 w-5 text-gray-400 animate-spin" />
                      ) : (
                        <ChevronRight
                          className={`h-5 w-5 text-gray-400 transition-transform ${
                            selectedPlaybook?.id === playbook.id ? 'rotate-90' : ''
                          }`}
                        />
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Playbook Details */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">Playbook Details</h2>
              </div>
              <div className="p-6">
                {selectedPlaybook ? (
                  <div className="space-y-6">
                    <div>
                      <h3 className="text-sm font-medium text-gray-500">ID</h3>
                      <p className="mt-1 text-lg font-semibold text-gray-900">{selectedPlaybook.id}</p>
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-gray-500">Description</h3>
                      <p className="mt-1 text-sm text-gray-900">{selectedPlaybook.description}</p>
                    </div>
                    <div>
                      <h3 className="text-sm font-medium text-gray-500 mb-2">Configuration</h3>
                      <pre className="bg-gray-50 rounded-lg p-4 overflow-x-auto text-xs">
                        {JSON.stringify(selectedPlaybook.config, null, 2)}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <BookOpen className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-600">Select a playbook to view its configuration</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}




