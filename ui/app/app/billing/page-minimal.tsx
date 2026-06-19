'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { CreditCard, CheckCircle, XCircle } from 'lucide-react'
import { apiClient } from '@/lib/api-client'
import AppLayout from '@/components/layout/AppLayout'
import { useSession } from 'next-auth/react'

export default function BillingPage() {
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
      setError('Failed to load billing information')
    } finally {
      setLoading(false)
    }
  }

  const handleUpgrade = async (plan: string) => {
    alert(`Upgrading to ${plan} plan - This would redirect to Stripe checkout`)
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
        
        {/* Plan Comparison */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
          {/* Free Plan */}
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">Free</h3>
              <p className="text-sm text-gray-600 mt-1">Perfect for getting started</p>
            </div>
            <div className="px-6 py-4">
              <div className="text-2xl font-bold text-gray-900 mb-4">$0<span className="text-sm font-normal text-gray-600">/month</span></div>
              <ul className="space-y-3 text-sm">
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Up to 3 products</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>5 data sources per product</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>10 pipeline runs per month</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>10,000 vectors</span>
                </li>
              </ul>
              <div className="mt-6">
                <Button className="w-full" variant="secondary">
                  Current Plan
                </Button>
              </div>
            </div>
          </div>

          {/* Pro Plan */}
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">Pro</h3>
              <p className="text-sm text-gray-600 mt-1">For growing teams</p>
            </div>
            <div className="px-6 py-4">
              <div className="text-2xl font-bold text-gray-900 mb-4">$99<span className="text-sm font-normal text-gray-600">/month</span></div>
              <ul className="space-y-3 text-sm">
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Up to 25 products</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>50 data sources per product</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>1,000 pipeline runs per month</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>1,000,000 vectors</span>
                </li>
              </ul>
              <div className="mt-6">
                <Button 
                  className="w-full" 
                  onClick={() => handleUpgrade('pro')}
                >
                  Upgrade to Pro
                </Button>
              </div>
            </div>
          </div>

          {/* Enterprise Plan */}
          <div className="bg-white shadow rounded-lg">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">Enterprise</h3>
              <p className="text-sm text-gray-600 mt-1">For large organizations</p>
            </div>
            <div className="px-6 py-4">
              <div className="text-2xl font-bold text-gray-900 mb-4">Custom<span className="text-sm font-normal text-gray-600">/month</span></div>
              <ul className="space-y-3 text-sm">
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Unlimited products</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Unlimited data sources</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Unlimited pipeline runs</span>
                </li>
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Unlimited vectors</span>
                </li>
              </ul>
              <div className="mt-6">
                <Button 
                  className="w-full" 
                  onClick={() => handleUpgrade('enterprise')}
                >
                  Contact Sales
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
