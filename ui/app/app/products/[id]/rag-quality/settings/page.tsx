'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Save, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { CardSkeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/toast'

interface Product {
  id: string
  name: string
  rag_quality_thresholds?: Record<string, number>
}

const DEFAULT_THRESHOLDS = {
  groundedness_min: 0.80,
  hallucination_rate_max: 0.05,
  acl_leakage_max: 0.0,
  citation_coverage_min: 0.90,
  refusal_correctness_min: 0.95,
  context_relevance_min: 0.75,
  answer_relevance_min: 0.80,
}

export default function QualitySettingsPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const params = useParams()
  const productId = params.id as string
  const { addToast } = useToast()

  const [product, setProduct] = useState<Product | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [thresholds, setThresholds] = useState(DEFAULT_THRESHOLDS)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/')
      return
    }

    if (status === 'authenticated' && productId) {
      loadData()
    }
  }, [status, router, productId])

  const loadData = async () => {
    setLoading(true)
    try {
      const response = await apiClient.getProduct(productId)
      if (!response.error && response.data) {
        const productData = response.data as Product
        setProduct(productData)
        if (productData.rag_quality_thresholds) {
          setThresholds({ ...DEFAULT_THRESHOLDS, ...productData.rag_quality_thresholds })
        }
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to load product'
      })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const response = await apiClient.updateRAGQualityThresholds(productId, thresholds)
      if (response.error) {
        addToast({
          type: 'error',
          message: response.error
        })
      } else {
        addToast({
          type: 'success',
          message: 'Thresholds updated successfully'
        })
        loadData()
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: 'Failed to update thresholds'
      })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6">
          <CardSkeleton />
        </div>
      </AppLayout>
    )
  }

  if (!product) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800">Product not found</p>
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
          <Link href={`/app/products/${productId}/rag-quality`} className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Retrieval Evaluation
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Settings</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Quality Thresholds</h1>
          <p className="text-gray-600 mt-1">
            Configure quality gate thresholds for retrieval evaluation. These thresholds determine whether your retrieval system passes quality gates.
          </p>
        </div>

        {/* Thresholds Form */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 max-w-3xl">
          <div className="space-y-6">
            <div>
              <Label htmlFor="groundedness_min">Groundedness (Minimum)</Label>
              <div className="mt-1 flex items-center gap-3">
                <Input
                  id="groundedness_min"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={thresholds.groundedness_min}
                  onChange={(e) => setThresholds({ ...thresholds, groundedness_min: parseFloat(e.target.value) || 0 })}
                  className="w-32"
                />
                <span className="text-sm text-gray-500">
                  {(thresholds.groundedness_min * 100).toFixed(0)}% - Minimum score for answer to be considered grounded
                </span>
              </div>
            </div>

            <div>
              <Label htmlFor="hallucination_rate_max">Hallucination Rate (Maximum)</Label>
              <div className="mt-1 flex items-center gap-3">
                <Input
                  id="hallucination_rate_max"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={thresholds.hallucination_rate_max}
                  onChange={(e) => setThresholds({ ...thresholds, hallucination_rate_max: parseFloat(e.target.value) || 0 })}
                  className="w-32"
                />
                <span className="text-sm text-gray-500">
                  {(thresholds.hallucination_rate_max * 100).toFixed(0)}% - Maximum allowed hallucination rate
                </span>
              </div>
            </div>

            <div>
              <Label htmlFor="acl_leakage_max">ACL Leakage (Maximum)</Label>
              <div className="mt-1 flex items-center gap-3">
                <Input
                  id="acl_leakage_max"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={thresholds.acl_leakage_max}
                  onChange={(e) => setThresholds({ ...thresholds, acl_leakage_max: parseFloat(e.target.value) || 0 })}
                  className="w-32"
                />
                <span className="text-sm text-gray-500">
                  {(thresholds.acl_leakage_max * 100).toFixed(0)}% - Maximum allowed ACL violations (should be 0)
                </span>
              </div>
            </div>

            <div>
              <Label htmlFor="citation_coverage_min">Citation Coverage (Minimum)</Label>
              <div className="mt-1 flex items-center gap-3">
                <Input
                  id="citation_coverage_min"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={thresholds.citation_coverage_min}
                  onChange={(e) => setThresholds({ ...thresholds, citation_coverage_min: parseFloat(e.target.value) || 0 })}
                  className="w-32"
                />
                <span className="text-sm text-gray-500">
                  {(thresholds.citation_coverage_min * 100).toFixed(0)}% - Minimum percentage of claims that must have citations
                </span>
              </div>
            </div>

            <div>
              <Label htmlFor="refusal_correctness_min">Refusal Correctness (Minimum)</Label>
              <div className="mt-1 flex items-center gap-3">
                <Input
                  id="refusal_correctness_min"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={thresholds.refusal_correctness_min}
                  onChange={(e) => setThresholds({ ...thresholds, refusal_correctness_min: parseFloat(e.target.value) || 0 })}
                  className="w-32"
                />
                <span className="text-sm text-gray-500">
                  {(thresholds.refusal_correctness_min * 100).toFixed(0)}% - Minimum score for correct refusal handling
                </span>
              </div>
            </div>

            <div>
              <Label htmlFor="context_relevance_min">Context Relevance (Minimum)</Label>
              <div className="mt-1 flex items-center gap-3">
                <Input
                  id="context_relevance_min"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={thresholds.context_relevance_min}
                  onChange={(e) => setThresholds({ ...thresholds, context_relevance_min: parseFloat(e.target.value) || 0 })}
                  className="w-32"
                />
                <span className="text-sm text-gray-500">
                  {(thresholds.context_relevance_min * 100).toFixed(0)}% - Minimum relevance score for retrieved chunks
                </span>
              </div>
            </div>

            <div>
              <Label htmlFor="answer_relevance_min">Answer Relevance (Minimum)</Label>
              <div className="mt-1 flex items-center gap-3">
                <Input
                  id="answer_relevance_min"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={thresholds.answer_relevance_min}
                  onChange={(e) => setThresholds({ ...thresholds, answer_relevance_min: parseFloat(e.target.value) || 0 })}
                  className="w-32"
                />
                <span className="text-sm text-gray-500">
                  {(thresholds.answer_relevance_min * 100).toFixed(0)}% - Minimum relevance score for generated answers
                </span>
              </div>
            </div>

            <div className="pt-4 border-t flex items-center justify-end gap-3">
              <Link href={`/app/products/${productId}/rag-quality`}>
                <Button variant="outline">Cancel</Button>
              </Link>
              <Button
                onClick={handleSave}
                disabled={saving}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Thresholds
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}



