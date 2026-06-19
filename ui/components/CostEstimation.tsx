'use client'

import { useState } from 'react'
import { Loader2, AlertCircle, Upload, DollarSign, FileText, Calculator } from 'lucide-react'
import { apiClient, CostEstimate } from '@/lib/api-client'
import { useToast } from './ui/toast'
import { Button } from './ui/button'
import { PlaybookSelector } from './PlaybookSelector'

interface CostEstimationProps {
  showTitle?: boolean
}

export function CostEstimation({ showTitle = true }: CostEstimationProps) {
  const [file, setFile] = useState<File | null>(null)
  const [playbookId, setPlaybookId] = useState<string | undefined>(undefined)
  const [estimate, setEstimate] = useState<CostEstimate | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { addToast } = useToast()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setEstimate(null)
      setError(null)
    }
  }

  const handleEstimate = async () => {
    if (!file) {
      addToast({
        type: 'error',
        message: 'Please select a file first',
      })
      return
    }

    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.estimateCost(file, playbookId)
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to estimate cost: ${response.error}`,
        })
      } else if (response.data) {
        setEstimate(response.data)
        addToast({
          type: 'success',
          message: 'Cost estimate generated successfully',
        })
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to estimate cost'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 6,
      maximumFractionDigits: 6,
    }).format(amount)
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Cost Estimation</h2>}
      
      <div className="space-y-6">
        {/* File Upload */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Upload File for Cost Estimation
          </label>
          <div className="flex items-center gap-4">
            <label className="flex-1 cursor-pointer">
              <input
                type="file"
                onChange={handleFileChange}
                accept=".txt,.pdf"
                className="hidden"
              />
              <div className="flex items-center justify-center px-4 py-3 border-2 border-dashed border-gray-300 rounded-lg hover:border-blue-500 transition-colors">
                {file ? (
                  <div className="flex items-center gap-2 text-sm text-gray-700">
                    <FileText className="h-5 w-5 text-blue-600" />
                    <span className="font-medium">{file.name}</span>
                    <span className="text-gray-500">
                      ({(file.size / 1024).toFixed(1)} KB)
                    </span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2 text-sm text-gray-600">
                    <Upload className="h-8 w-8 text-gray-400" />
                    <span>Click to select a file</span>
                    <span className="text-xs text-gray-500">Supports .txt and .pdf files</span>
                  </div>
                )}
              </div>
            </label>
          </div>
        </div>

        {/* Playbook Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Preprocessing Playbook (Optional)
          </label>
          <PlaybookSelector
            value={playbookId}
            onChange={setPlaybookId}
          />
          <p className="mt-1 text-sm text-gray-500">
            Select a playbook to use for cost estimation, or leave blank for auto-detection.
          </p>
        </div>

        {/* Estimate Button */}
        <Button
          onClick={handleEstimate}
          disabled={!file || loading}
          className="w-full"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
              Estimating...
            </>
          ) : (
            <>
              <Calculator className="h-4 w-4 mr-2" />
              Estimate Cost
            </>
          )}
        </Button>

        {/* Error Display */}
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Estimate Results */}
        {estimate && (
          <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <h3 className="text-md font-semibold text-gray-900 mb-4 flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-blue-600" />
              Cost Estimate Results
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium text-gray-700">File</p>
                <p className="text-sm text-gray-900">{estimate.filename}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700">Playbook</p>
                <p className="text-sm text-gray-900">{estimate.playbook}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700">Estimated Tokens</p>
                <p className="text-lg font-semibold text-gray-900">
                  {estimate.estimated_tokens.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700">Estimated Chunks</p>
                <p className="text-lg font-semibold text-gray-900">
                  {estimate.estimated_chunks.toLocaleString()}
                </p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-sm font-medium text-gray-700 mb-2">Estimated Cost</p>
                <p className="text-3xl font-bold text-blue-600">
                  {formatCurrency(estimate.estimated_cost_usd)}
                </p>
              </div>
              {estimate.price_model && Object.keys(estimate.price_model).length > 0 && (
                <div className="sm:col-span-2">
                  <p className="text-sm font-medium text-gray-700 mb-2">Price Model</p>
                  <div className="bg-white rounded border border-gray-200 p-3">
                    <dl className="grid grid-cols-2 gap-2">
                      {Object.entries(estimate.price_model).map(([key, value]) => (
                        <div key={key}>
                          <dt className="text-xs text-gray-500">{key}</dt>
                          <dd className="text-sm font-medium text-gray-900">
                            {formatCurrency(typeof value === 'number' ? value : 0)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}



