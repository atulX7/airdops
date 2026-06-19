'use client'

import { useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Save, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { useToast } from '@/components/ui/toast'

export default function NewDatasetPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  const { addToast } = useToast()

  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    dataset_type: 'golden_qa' as 'golden_qa' | 'golden_retrieval' | 'adversarial',
    version: '' as string | number
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      const response = await apiClient.createEvaluationDataset(productId, {
        name: formData.name,
        description: formData.description || undefined,
        dataset_type: formData.dataset_type,
        version: formData.version ? parseInt(formData.version as string) : undefined
      })

      if (response.error) {
        addToast({
          type: 'error',
          message: response.error
        })
      } else {
        addToast({
          type: 'success',
          message: 'Dataset created successfully'
        })
        router.push(`/app/products/${productId}/rag-quality/datasets`)
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to create dataset'
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppLayout>
      <div className="p-6">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href={`/app/products/${productId}/rag-quality/datasets`} className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Datasets
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">New Dataset</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Create Evaluation Dataset</h1>
          <p className="text-gray-600 mt-1">
            Create a new evaluation dataset for retrieval evaluation.
          </p>
        </div>

        {/* Form */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 max-w-2xl">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <Label htmlFor="name">Dataset Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                placeholder="e.g., Product Knowledge Base Q&A"
                className="mt-1"
              />
            </div>

            <div>
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Optional description of the dataset"
                rows={3}
                className="mt-1"
              />
            </div>

            <div>
              <Label htmlFor="dataset_type">Dataset Type *</Label>
              <select
                id="dataset_type"
                value={formData.dataset_type}
                onChange={(e) => setFormData({ ...formData, dataset_type: e.target.value as any })}
                required
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
              >
                <option value="golden_qa">Golden Q/A - Expected questions and answers</option>
                <option value="golden_retrieval">Golden Retrieval - Expected retrieval results</option>
                <option value="adversarial">Adversarial - Test cases for edge cases</option>
              </select>
            </div>

            <div>
              <Label htmlFor="version">Product Version (Optional)</Label>
              <Input
                id="version"
                type="number"
                value={formData.version}
                onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                placeholder="Leave empty for all versions"
                className="mt-1"
              />
              <p className="mt-1 text-xs text-gray-500">Leave empty to use this dataset for all product versions</p>
            </div>

            <div className="flex items-center justify-end gap-3 pt-4 border-t">
              <Link href={`/app/products/${productId}/rag-quality/datasets`}>
                <Button type="button" variant="outline">Cancel</Button>
              </Link>
              <Button type="submit" disabled={loading} className="bg-blue-600 hover:bg-blue-700 text-white">
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Create Dataset
                  </>
                )}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </AppLayout>
  )
}

