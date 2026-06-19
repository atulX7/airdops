'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { StatCardSkeleton } from '@/components/ui/skeleton'
import { 
  CreditCard, 
  CheckCircle, 
  XCircle, 
  TrendingUp, 
  Package, 
  Database, 
  Zap, 
  ArrowUp,
  Crown,
  Sparkles
} from 'lucide-react'
import { apiClient, BillingLimitsResponse } from '@/lib/api-client'
import AppLayout from '@/components/layout/AppLayout'
import { useSession } from 'next-auth/react'

interface UsageMeterProps {
  label: string
  current: number
  limit: number
  icon: React.ElementType
  color: string
}

function UsageMeter({ label, current, limit, icon: Icon, color }: UsageMeterProps) {
  const percentage = limit === -1 ? 0 : Math.min((current / limit) * 100, 100)
  const isUnlimited = limit === -1
  const isNearLimit = !isUnlimited && percentage >= 80
  const isOverLimit = !isUnlimited && current > limit

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-3">
          <div className={`${color} rounded-lg p-2`}>
            <Icon className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-700">{label}</p>
            <p className="text-xs text-gray-500">Current usage</p>
          </div>
        </div>
        <div className="text-right">
          <p className={`text-2xl font-bold ${isOverLimit ? 'text-red-600' : isNearLimit ? 'text-yellow-600' : 'text-gray-900'}`}>
            {isUnlimited ? '∞' : current.toLocaleString()}
          </p>
          {!isUnlimited && (
            <p className="text-xs text-gray-500">of {limit.toLocaleString()}</p>
          )}
        </div>
      </div>
      {!isUnlimited && (
        <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
          <div 
            className={`h-2.5 rounded-full transition-all ${
              isOverLimit ? 'bg-gradient-to-r from-red-500 to-rose-600' :
              isNearLimit ? 'bg-gradient-to-r from-yellow-500 to-amber-600' :
              'bg-gradient-to-r from-blue-500 to-indigo-600'
            }`}
            style={{ width: `${percentage}%` }}
          ></div>
        </div>
      )}
      {isOverLimit && (
        <p className="text-xs text-red-600 font-medium">⚠️ Over limit - upgrade required</p>
      )}
      {isNearLimit && !isOverLimit && (
        <p className="text-xs text-yellow-600 font-medium">⚠️ Approaching limit</p>
      )}
    </div>
  )
}

export default function BillingPage() {
  const { data: session } = useSession()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [billingData, setBillingData] = useState<BillingLimitsResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)

  useEffect(() => {
    const getWorkspaceId = async () => {
      // Try to get from session first
      const sessionWorkspaceId = session?.user?.workspace_ids?.[0]
      if (sessionWorkspaceId) {
        setWorkspaceId(sessionWorkspaceId)
        return
      }

      // If not in session, fetch from API
      try {
        const workspacesResponse = await apiClient.getWorkspaces()
        if (workspacesResponse.data && workspacesResponse.data.length > 0) {
          setWorkspaceId(workspacesResponse.data[0].id)
        } else {
          setError('No workspace found. Please create a workspace first.')
        }
      } catch (err) {
        console.error('Failed to fetch workspaces:', err)
        setError('Failed to load workspace information')
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
      setError(null)
      const response = await apiClient.getBillingLimits(workspaceId)
      
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setBillingData(response.data)
      }
    } catch (err: unknown) {
      console.error('Failed to load billing limits:', err)
      setError('Failed to load billing information')
    } finally {
      setLoading(false)
    }
  }

  const handleUpgrade = async (plan: string) => {
    if (!workspaceId) {
      setMessage('No workspace available')
      return
    }
    
    try {
      const response = await apiClient.createCheckoutSession(workspaceId, plan)
      if (response.error) {
        // Check if it's a beta/explore message
        if (response.error.includes('beta') || response.error.includes('explore') || response.error.includes('try') || response.error.includes('free')) {
          setMessage(response.error)
        } else {
          setMessage(`Error: ${response.error}`)
        }
        setTimeout(() => setMessage(null), 12000) // Longer timeout for longer message
      } else if (response.data?.checkout_url) {
        // Redirect to Stripe checkout
        window.location.href = response.data.checkout_url
      }
    } catch (err: any) {
      console.error('Failed to create checkout session:', err)
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to create checkout session'
      if (errorMessage.includes('beta') || errorMessage.includes('explore') || errorMessage.includes('try') || errorMessage.includes('free')) {
        setMessage(errorMessage)
      } else {
        setMessage(`Error: ${errorMessage}`)
      }
      setTimeout(() => setMessage(null), 12000)
    }
  }

  const handleManageBilling = async () => {
    if (!workspaceId) {
      setMessage('No workspace available')
      return
    }
    
    try {
      const response = await apiClient.getCustomerPortal(workspaceId)
      if (response.error) {
        // Check if it's a beta/explore message
        if (response.error.includes('beta') || response.error.includes('explore') || response.error.includes('try') || response.error.includes('free')) {
          setMessage(response.error)
        } else {
          setMessage(`Error: ${response.error}`)
        }
        setTimeout(() => setMessage(null), 12000)
      } else if (response.data?.portal_url) {
        window.location.href = response.data.portal_url
      }
    } catch (err: any) {
      console.error('Failed to get customer portal:', err)
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to open billing portal'
      if (errorMessage.includes('beta') || errorMessage.includes('explore') || errorMessage.includes('try') || errorMessage.includes('free')) {
        setMessage(errorMessage)
      } else {
        setMessage(`Error: ${errorMessage}`)
      }
      setTimeout(() => setMessage(null), 12000)
    }
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
          <div className="max-w-7xl mx-auto">
            <div className="mb-8">
              <div className="h-10 bg-gray-200 rounded-xl w-1/3 mb-2 animate-pulse"></div>
              <div className="h-6 bg-gray-200 rounded w-1/2 animate-pulse"></div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              {[...Array(3)].map((_, i) => (
                <StatCardSkeleton key={i} />
              ))}
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (!workspaceId) {
    return (
      <AppLayout>
        <ErrorState
          title="No Workspace"
          message="Please create a workspace to manage billing."
          variant="info"
        />
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout>
        <ErrorState
          title="Failed to load billing information"
          message={error}
          onRetry={loadBillingLimits}
          variant="error"
        />
      </AppLayout>
    )
  }

  const currentPlan = billingData?.plan || 'free'
  const usage = billingData?.usage || { products: 0, data_sources: 0, pipeline_runs_this_month: 0 }
  const limits = billingData?.limits || {
    max_products: 3,
    max_data_sources_per_product: 5,
    max_pipeline_runs_per_month: 10,
    schedule_frequency: 'manual'
  }

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-2 tracking-tight">Billing & Usage</h1>
            <p className="text-lg text-gray-600">Manage your subscription and monitor usage</p>
          </div>

          {/* Message Display */}
          {message && (
            <div className={`mb-6 p-5 rounded-xl border-2 ${
              message.includes('beta') || message.includes('explore') || message.includes('try') || message.includes('free') || message.includes('🚀')
                ? 'bg-gradient-to-r from-emerald-50 via-teal-50 to-cyan-50 border-emerald-200'
                : message.includes('Error')
                ? 'bg-gradient-to-r from-red-50 to-rose-50 border-red-200'
                : 'bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200'
            }`}>
              <div className="flex items-start">
                {message.includes('beta') || message.includes('explore') || message.includes('try') || message.includes('free') || message.includes('🚀') ? (
                  <>
                    <Sparkles className="h-6 w-6 text-emerald-600 mr-4 mt-0.5 flex-shrink-0" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        <p className="text-base font-bold text-emerald-900">Explore All Features Free!</p>
                        <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          <TrendingUp className="h-3 w-3 mr-1" />
                          Beta Access
                        </span>
                      </div>
                      <p className="text-sm text-emerald-800 leading-relaxed">{message}</p>
                    </div>
                  </>
                ) : message.includes('Error') ? (
                  <>
                    <XCircle className="h-5 w-5 text-red-500 mr-3 flex-shrink-0" />
                    <p className="text-sm font-medium text-red-800">{message}</p>
                  </>
                ) : (
                  <>
                    <CheckCircle className="h-5 w-5 text-blue-500 mr-3 flex-shrink-0" />
                    <p className="text-sm font-medium text-blue-800">{message}</p>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Usage Meters */}
          <div className="mb-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Current Usage</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <UsageMeter
                label="Products"
                current={usage.products}
                limit={limits.max_products}
                icon={Package}
                color="bg-gradient-to-br from-blue-500 to-indigo-600"
              />
              <UsageMeter
                label="Data Sources"
                current={usage.data_sources}
                limit={limits.max_data_sources_per_product}
                icon={Database}
                color="bg-gradient-to-br from-green-500 to-emerald-600"
              />
              <UsageMeter
                label="Pipeline Runs"
                current={usage.pipeline_runs_this_month}
                limit={limits.max_pipeline_runs_per_month}
                icon={Zap}
                color="bg-gradient-to-br from-purple-500 to-pink-600"
              />
            </div>
          </div>

          {/* Plan Comparison */}
          <div className="mb-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Subscription Plans</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Free Plan */}
              <div className={`bg-white rounded-xl shadow-md border-2 transition-all duration-200 ${
                currentPlan === 'free' 
                  ? 'border-blue-500 shadow-lg scale-105' 
                  : 'border-gray-200 hover:shadow-lg hover:-translate-y-0.5'
              }`}>
                <div className="px-6 py-4 border-b-2 border-gray-100 bg-gradient-to-r from-gray-50 to-blue-50/30">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">Free</h3>
                      <p className="text-sm text-gray-600 mt-1">Perfect for getting started</p>
                    </div>
                    {currentPlan === 'free' && (
                      <span className="bg-blue-100 text-blue-800 text-xs font-semibold px-2.5 py-1 rounded-full">
                        Current
                      </span>
                    )}
                  </div>
                </div>
                <div className="px-6 py-6">
                  <div className="text-3xl font-bold text-gray-900 mb-6">
                    $0<span className="text-lg font-normal text-gray-600">/month</span>
                  </div>
                  <ul className="space-y-3 text-sm mb-6">
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>Up to {limits.max_products === -1 ? 'unlimited' : limits.max_products} products</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>{limits.max_data_sources_per_product === -1 ? 'Unlimited' : limits.max_data_sources_per_product} data sources per product</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>{limits.max_pipeline_runs_per_month === -1 ? 'Unlimited' : limits.max_pipeline_runs_per_month} pipeline runs per month</span>
                    </li>
                  </ul>
                  <Button 
                    className={`w-full ${
                      currentPlan === 'free' 
                        ? 'bg-gray-100 text-gray-600 cursor-not-allowed' 
                        : 'bg-gradient-to-r from-gray-600 to-slate-700 hover:from-gray-700 hover:to-slate-800'
                    }`}
                    disabled={currentPlan === 'free'}
                  >
                    {currentPlan === 'free' ? 'Current Plan' : 'Downgrade to Free'}
                  </Button>
                </div>
              </div>

              {/* Pro Plan */}
              <div className={`bg-white rounded-xl shadow-md border-2 transition-all duration-200 relative ${
                currentPlan === 'pro' 
                  ? 'border-blue-500 shadow-lg scale-105' 
                  : 'border-gray-200 hover:shadow-lg hover:-translate-y-0.5'
              }`}>
                {currentPlan !== 'pro' && (
                  <div className="absolute -top-3 right-4">
                    <span className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-xs font-bold px-3 py-1 rounded-full flex items-center space-x-1">
                      <Sparkles className="h-3 w-3" />
                      <span>POPULAR</span>
                    </span>
                  </div>
                )}
                <div className="px-6 py-4 border-b-2 border-gray-100 bg-gradient-to-r from-blue-50 to-indigo-50/30">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">Pro</h3>
                      <p className="text-sm text-gray-600 mt-1">For growing teams</p>
                    </div>
                    {currentPlan === 'pro' && (
                      <span className="bg-blue-100 text-blue-800 text-xs font-semibold px-2.5 py-1 rounded-full">
                        Current
                      </span>
                    )}
                  </div>
                </div>
                <div className="px-6 py-6">
                  <div className="text-3xl font-bold text-gray-900 mb-6">
                    $99<span className="text-lg font-normal text-gray-600">/month</span>
                  </div>
                  <ul className="space-y-3 text-sm mb-6">
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>Up to 25 products</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>50 data sources per product</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>1,000 pipeline runs per month</span>
                    </li>
                  </ul>
                  <Button 
                    className={`w-full ${
                      currentPlan === 'pro' 
                        ? 'bg-gray-100 text-gray-600 cursor-not-allowed' 
                        : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg'
                    }`}
                    onClick={() => handleUpgrade('pro')}
                    disabled={currentPlan === 'pro'}
                  >
                    {currentPlan === 'pro' ? 'Current Plan' : 'Upgrade to Pro'}
                  </Button>
                </div>
              </div>

              {/* Enterprise Plan */}
              <div className={`bg-white rounded-xl shadow-md border-2 transition-all duration-200 relative ${
                currentPlan === 'enterprise' 
                  ? 'border-purple-500 shadow-lg scale-105' 
                  : 'border-gray-200 hover:shadow-lg hover:-translate-y-0.5'
              }`}>
                {currentPlan !== 'enterprise' && (
                  <div className="absolute -top-3 right-4">
                    <span className="bg-gradient-to-r from-purple-600 to-pink-600 text-white text-xs font-bold px-3 py-1 rounded-full flex items-center space-x-1">
                      <Crown className="h-3 w-3" />
                      <span>ENTERPRISE</span>
                    </span>
                  </div>
                )}
                <div className="px-6 py-4 border-b-2 border-gray-100 bg-gradient-to-r from-purple-50 to-pink-50/30">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">Enterprise</h3>
                      <p className="text-sm text-gray-600 mt-1">For large organizations</p>
                    </div>
                    {currentPlan === 'enterprise' && (
                      <span className="bg-purple-100 text-purple-800 text-xs font-semibold px-2.5 py-1 rounded-full">
                        Current
                      </span>
                    )}
                  </div>
                </div>
                <div className="px-6 py-6">
                  <div className="text-3xl font-bold text-gray-900 mb-6">
                    $299<span className="text-lg font-normal text-gray-600">/month</span>
                  </div>
                  <ul className="space-y-3 text-sm mb-6">
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>Unlimited products</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>Unlimited data sources</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                      <span>Unlimited pipeline runs</span>
                    </li>
                  </ul>
                  <Button 
                    className={`w-full ${
                      currentPlan === 'enterprise' 
                        ? 'bg-gray-100 text-gray-600 cursor-not-allowed' 
                        : 'bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 shadow-md hover:shadow-lg'
                    }`}
                    onClick={() => handleUpgrade('enterprise')}
                    disabled={currentPlan === 'enterprise'}
                  >
                    {currentPlan === 'enterprise' ? 'Current Plan' : 'Upgrade to Enterprise'}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Manage Billing Section */}
          {currentPlan !== 'free' && (
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg p-3">
                    <CreditCard className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">Manage Billing</h3>
                    <p className="text-sm text-gray-600">Update payment methods, view invoices, and manage your subscription</p>
                  </div>
                </div>
                <Button
                  onClick={handleManageBilling}
                  className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"
                >
                  Open Billing Portal
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  )
}
