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

interface BillingLimits {
  plan: string
  limits: {
    max_products: number
    max_data_sources_per_product: number
    max_pipeline_runs_per_month: number
    max_vectors: number
    schedule_frequency: string
  }
  usage: {
    products?: number
    data_sources?: number
    pipeline_runs?: number
    vectors?: number
  }
}

interface CheckoutResponse {
  checkout_url: string
  session_id: string
}

interface PortalResponse {
  portal_url: string
}

export default function BillingPage() {
  const { data: session } = useSession()
  const [limits, setLimits] = useState<BillingLimits | null>(null)
  const [loading, setLoading] = useState(true)
  const [creatingCheckout, setCreatingCheckout] = useState(false)
  const [openingPortal, setOpeningPortal] = useState(false)
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
      setLimits(response.data as BillingLimits)
    } catch (err) {
      console.error('Failed to load billing limits:', err)
      setError('Failed to load billing information')
    } finally {
      setLoading(false)
    }
  }

  const handleUpgrade = async (plan: 'pro' | 'enterprise') => {
    try {
      setCreatingCheckout(true)
      const response = await apiClient.post<CheckoutResponse>('/api/v1/billing/checkout-session', {
        workspace_id: workspaceId,
        plan: plan
      })
      
      // Redirect to Stripe checkout
      if (response.data?.checkout_url) {
        window.location.href = response.data.checkout_url
      }
    } catch (err) {
      console.error('Failed to create checkout session:', err)
      setError('Failed to start upgrade process')
    } finally {
      setCreatingCheckout(false)
    }
  }

  const handleManageBilling = async () => {
    if (!workspaceId) {
      setError('No workspace available')
      return
    }
    
    try {
      setOpeningPortal(true)
      const response = await apiClient.get<PortalResponse>(`/api/v1/billing/portal?workspace_id=${workspaceId}`)
      
      // Open Stripe customer portal
      if (response.data?.portal_url) {
        window.open(response.data.portal_url, '_blank')
      }
    } catch (err) {
      console.error('Failed to open billing portal:', err)
      setError('Failed to open billing portal')
    } finally {
      setOpeningPortal(false)
    }
  }

  const formatNumber = (num: number) => {
    if (num === -1) return 'Unlimited'
    return num.toLocaleString()
  }

  const getUsagePercentage = (used: number, limit: number) => {
    if (limit === -1) return 0
    return Math.min((used / limit) * 100, 100)
  }

  const getPlanIcon = (plan: string) => {
    switch (plan) {
      case 'free':
        return <Zap className="h-5 w-5 text-gray-500" />
      case 'pro':
        return <Shield className="h-5 w-5 text-blue-500" />
      case 'enterprise':
        return <Infinity className="h-5 w-5 text-purple-500" />
      default:
        return <Zap className="h-5 w-5 text-gray-500" />
    }
  }

  const getPlanColor = (plan: string) => {
    switch (plan) {
      case 'free':
        return 'bg-gray-100 text-gray-800'
      case 'pro':
        return 'bg-blue-100 text-blue-800'
      case 'enterprise':
        return 'bg-purple-100 text-purple-800'
      default:
        return 'bg-gray-100 text-gray-800'
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
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Billing & Usage</h1>
          <p className="text-gray-600 mt-2">Manage your subscription and monitor usage</p>
        </div>

        {/* Current Plan */}
        <div className="bg-white shadow rounded-lg mb-8">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                {getPlanIcon(limits?.plan || 'free')}
                <div>
                  <h2 className="text-xl font-semibold text-gray-900">
                    {limits?.plan ? limits.plan.charAt(0).toUpperCase() + limits.plan.slice(1) : 'Free'} Plan
                  </h2>
                  <p className="text-sm text-gray-600">Current subscription plan</p>
                </div>
              </div>
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getPlanColor(limits?.plan || 'free')}`}>
                {limits?.plan?.toUpperCase() || 'FREE'}
              </span>
            </div>
          </div>
          <div className="px-6 py-4">
            <div className="flex space-x-4">
              <Button
                onClick={() => handleUpgrade('pro')}
                disabled={creatingCheckout || limits?.plan === 'pro' || limits?.plan === 'enterprise'}
                className="flex items-center space-x-2"
              >
                <CreditCard className="h-4 w-4" />
                <span>Upgrade to Pro</span>
              </Button>
              <Button
                onClick={() => handleUpgrade('enterprise')}
                disabled={creatingCheckout || limits?.plan === 'enterprise'}
                variant="outline"
                className="flex items-center space-x-2"
              >
                <Shield className="h-4 w-4" />
                <span>Upgrade to Enterprise</span>
              </Button>
              {limits?.plan !== 'free' && (
                <Button
                  onClick={handleManageBilling}
                  disabled={openingPortal}
                  variant="outline"
                  className="flex items-center space-x-2"
                >
                  <Settings className="h-4 w-4" />
                  <span>Manage Billing</span>
                  <ExternalLink className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Usage Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white shadow rounded-lg p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-8 h-8 bg-blue-100 rounded-md flex items-center justify-center">
                  <span className="text-blue-600 font-semibold text-sm">P</span>
                </div>
              </div>
              <div className="ml-4 flex-1">
                <p className="text-sm font-medium text-gray-600">Products</p>
                <p className="text-2xl font-semibold text-gray-900">
                  {limits?.usage?.products || 0} / {formatNumber(limits?.limits?.max_products || 0)}
                </p>
                <div className="mt-2">
                  <div className="bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${getUsagePercentage(limits?.usage?.products || 0, limits?.limits?.max_products || 0)}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white shadow rounded-lg p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-8 h-8 bg-green-100 rounded-md flex items-center justify-center">
                  <span className="text-green-600 font-semibold text-sm">D</span>
                </div>
              </div>
              <div className="ml-4 flex-1">
                <p className="text-sm font-medium text-gray-600">Data Sources</p>
                <p className="text-2xl font-semibold text-gray-900">
                  {limits?.usage?.data_sources || 0} / {formatNumber(limits?.limits?.max_data_sources_per_product || 0)}
                </p>
                <div className="mt-2">
                  <div className="bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-green-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${getUsagePercentage(limits?.usage?.data_sources || 0, limits?.limits?.max_data_sources_per_product || 0)}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white shadow rounded-lg p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-8 h-8 bg-purple-100 rounded-md flex items-center justify-center">
                  <span className="text-purple-600 font-semibold text-sm">R</span>
                </div>
              </div>
              <div className="ml-4 flex-1">
                <p className="text-sm font-medium text-gray-600">Pipeline Runs</p>
                <p className="text-2xl font-semibold text-gray-900">
                  {limits?.usage?.pipeline_runs || 0} / {formatNumber(limits?.limits?.max_pipeline_runs_per_month || 0)}
                </p>
                <div className="mt-2">
                  <div className="bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-purple-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${getUsagePercentage(limits?.usage?.pipeline_runs || 0, limits?.limits?.max_pipeline_runs_per_month || 0)}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white shadow rounded-lg p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="w-8 h-8 bg-orange-100 rounded-md flex items-center justify-center">
                  <span className="text-orange-600 font-semibold text-sm">V</span>
                </div>
              </div>
              <div className="ml-4 flex-1">
                <p className="text-sm font-medium text-gray-600">Vectors</p>
                <p className="text-2xl font-semibold text-gray-900">
                  {limits?.usage?.vectors || 0} / {formatNumber(limits?.limits?.max_vectors || 0)}
                </p>
                <div className="mt-2">
                  <div className="bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-orange-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${getUsagePercentage(limits?.usage?.vectors || 0, limits?.limits?.max_vectors || 0)}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Plan Comparison */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className={`bg-white shadow rounded-lg ${limits?.plan === 'free' ? 'ring-2 ring-gray-300' : ''}`}>
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center space-x-2">
                <Zap className="h-5 w-5 text-gray-500" />
                <h3 className="text-lg font-semibold text-gray-900">Free</h3>
              </div>
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
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Manual scheduling</span>
                </li>
              </ul>
            </div>
          </div>

          <div className={`bg-white shadow rounded-lg ${limits?.plan === 'pro' ? 'ring-2 ring-blue-300' : ''}`}>
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center space-x-2">
                <Shield className="h-5 w-5 text-blue-500" />
                <h3 className="text-lg font-semibold text-gray-900">Pro</h3>
              </div>
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
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Hourly scheduling</span>
                </li>
              </ul>
            </div>
          </div>

          <div className={`bg-white shadow rounded-lg ${limits?.plan === 'enterprise' ? 'ring-2 ring-purple-300' : ''}`}>
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center space-x-2">
                <Infinity className="h-5 w-5 text-purple-500" />
                <h3 className="text-lg font-semibold text-gray-900">Enterprise</h3>
              </div>
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
                <li className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <span>Real-time scheduling</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  )
}