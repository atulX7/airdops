'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { AlertCircle } from 'lucide-react'

type Overview = {
  chunk_count?: number
  vector_count?: number
  dq_failures?: number
}

export default function LineagePage() {
  const params = useParams()
  const productId = params.id as string
  const [overview, setOverview] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(`/api/v1/lineage/${productId}/overview`, { cache: 'no-store' })
        if (!res.ok) {
          throw new Error(`Failed to fetch lineage overview (${res.status})`)
        }
        const data = await res.json()
        setOverview(data)
      } catch (e: any) {
        setError(e?.message || 'Failed to load lineage overview')
      }
    }
    if (productId) {
      load()
    }
  }, [productId])

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
        <div className="border-b p-4">
          <h2 className="text-base font-semibold">Lineage Overview</h2>
        </div>
        <div className="p-4">
          {error && (
            <div className="flex items-center gap-2 text-red-600 text-sm">
              <AlertCircle size={16} /> {error}
            </div>
          )}
          {!error && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
              <div className="p-3 rounded border">
                <div className="text-muted-foreground">Chunks</div>
                <div className="text-lg font-semibold">{overview?.chunk_count ?? 0}</div>
              </div>
              <div className="p-3 rounded border">
                <div className="text-muted-foreground">Vectors</div>
                <div className="text-lg font-semibold">{overview?.vector_count ?? 0}</div>
              </div>
              <div className="p-3 rounded border">
                <div className="text-muted-foreground">DQ Findings</div>
                <div className="text-lg font-semibold">{overview?.dq_failures ?? 0}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
