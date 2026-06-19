'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { 
  CreditCard, 
  CheckCircle, 
  XCircle, 
  ExternalLink,
  Settings,
  Zap,
  Shield,
  Infinity
} from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import AppLayout from '@/components/layout/AppLayout'
import { useSession } from 'next-auth/react'

export default function BillingPageTest() {
  const { data: session } = useSession()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [workspaceId, setWorkspaceId] = useState<string | null>(null)

  useEffect(() => {
    const getWorkspaceId = async () => {
      const sessionWorkspaceId = session?.user?.workspace_ids?.[0]
      if (sessionWorkspaceId) {
        setWorkspaceId(sessionWorkspaceId)
        return
      }
      try {
        const workspacesResponse = await apiClient.getWorkspaces()
        if (workspacesResponse.data && workspacesResponse.data.length > 0) {
          setWorkspaceId(workspacesResponse.data[0].id)
        }
      } catch (err) {
        console.error('Failed to fetch workspaces:', err)
      }
    }
    if (session) {
      getWorkspaceId()
    }
  }, [session])

  useEffect(() => {
    if (workspaceId) {
      loadBillingLimits()
    }
  }, [workspaceId])

  const loadBillingLimits = async () => {
    if (!workspaceId) {
      setError('No workspace available')
      setLoading(false)
      return
    }
    
    try {
      setLoading(true)
      const response = await apiClient.get(`/api/v1/billing/limits?workspace_id=${workspaceId}`)
    } catch (err) {
      console.error('Failed to load billing limits:', err)
      setError('Failed to load billing information')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </AppLayout>
    )
  }

  if (!workspaceId) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-gray-900 mb-2">No Workspace</h2>
            <p className="text-gray-600 mb-4">Please create a workspace to manage billing.</p>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Error</h2>
            <p className="text-gray-600 mb-4">{error}</p>
            <Button onClick={loadBillingLimits}>Try Again</Button>
          </div>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-3xl font-bold text-gray-900">Billing & Usage</h1>
        <p className="text-gray-600 mt-2">Manage your subscription and monitor usage</p>
        
        <div className="mt-8">
          <Button>Test Button</Button>
        </div>
      </div>
    </AppLayout>
  )
}
