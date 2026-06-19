'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, CheckCircle, XCircle, AlertCircle, RefreshCw, Activity, Database, Search, HardDrive, BarChart3, GitBranch, Cloud, Clock } from 'lucide-react'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient, HealthCheckResponse } from '@/lib/api-client'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { CardSkeleton, StatCardSkeleton } from '@/components/ui/skeleton'

export default function SystemHealthPage() {
  const router = useRouter()
  const [health, setHealth] = useState<HealthCheckResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const { addToast } = useToast()

  const loadHealth = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.getHealthCheck()
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load system health: ${response.error}`,
        })
      } else if (response.data) {
        setHealth(response.data)
        setLastChecked(new Date())
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load system health'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadHealth()
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  const getServiceIcon = (serviceName: string) => {
    switch (serviceName.toLowerCase()) {
      case 'database':
        return <Database className="h-5 w-5" />
      case 'qdrant':
        return <Search className="h-5 w-5" />
      case 'minio':
        return <HardDrive className="h-5 w-5" />
      case 'airflow':
        return <GitBranch className="h-5 w-5" />
      default:
        return <Activity className="h-5 w-5" />
    }
  }

  const getServiceName = (serviceName: string) => {
    switch (serviceName.toLowerCase()) {
      case 'database':
        return 'PostgreSQL Database'
      case 'qdrant':
        return 'Qdrant Vector DB'
      case 'minio':
        return 'MinIO Object Storage'
      case 'airflow':
        return 'Apache Airflow'
      default:
        return serviceName
    }
  }

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        <div className="max-w-7xl mx-auto">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link href="/app" className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Dashboard
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">System Health</span>
        </div>

        {/* Page Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center">
            <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-3 mr-4 shadow-lg">
              <Activity className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">System Health</h1>
              <p className="text-gray-600 mt-1">
                Monitor the health and status of all AIRDOps services and dependencies.
              </p>
            </div>
          </div>
          <Button
            onClick={loadHealth}
            disabled={loading}
            className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-md"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        {/* Overall Status */}
        {health && (
          <div className={`mb-8 rounded-xl shadow-lg border-2 p-8 relative overflow-hidden ${
            health.status === 'healthy'
              ? 'bg-white border-green-200'
              : 'bg-white border-yellow-200'
          }`}>
            <div className={`absolute top-0 right-0 -mr-4 -mt-4 ${
              health.status === 'healthy' 
                ? 'bg-gradient-to-br from-green-500 to-emerald-600' 
                : 'bg-gradient-to-br from-yellow-500 to-orange-600'
            } rounded-full h-32 w-32 opacity-20`}></div>
            <div className="relative">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  {health.status === 'healthy' ? (
                    <CheckCircle className="h-10 w-10 text-green-600" />
                  ) : (
                    <AlertCircle className="h-10 w-10 text-yellow-600" />
                  )}
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900 mb-1">
                      System Status: {health.status === 'healthy' ? 'All Systems Operational' : 'Degraded'}
                    </h2>
                    <p className="text-sm text-gray-600">
                      Service: {health.service} v{health.version}
                      {lastChecked && (
                        <span className="ml-2 flex items-center">
                          <Clock className="h-3 w-3 mr-1" />
                          Last checked: {lastChecked.toLocaleTimeString()}
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <div className={`flex items-center px-6 py-3 rounded-full text-lg font-bold shadow-md ${
                  health.status === 'healthy' 
                    ? 'bg-gradient-to-r from-green-500 to-emerald-600 text-white' 
                    : 'bg-gradient-to-r from-yellow-500 to-orange-600 text-white'
                }`}>
                  {health.status === 'healthy' ? (
                    <CheckCircle className="h-5 w-5 mr-2" />
                  ) : (
                    <AlertCircle className="h-5 w-5 mr-2" />
                  )}
                  <span className="capitalize">{health.status}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && !health && (
          <div className="space-y-6">
            <CardSkeleton />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[1, 2, 3, 4, 5].map((i) => (
                <StatCardSkeleton key={i} />
              ))}
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !health && (
          <div className="bg-white rounded-lg shadow-sm border border-red-200 p-6">
            <div className="flex items-center gap-3">
              <XCircle className="h-6 w-6 text-red-500" />
              <div>
                <h3 className="text-lg font-semibold text-red-900">Failed to Load Health Status</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Services Status */}
        {health && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Object.entries(health.services).map(([serviceName, serviceStatus]) => {
              const status = (serviceStatus as any).status
              const isHealthy = status === 'healthy'
              return (
                <div
                  key={serviceName}
                  className={`bg-white rounded-xl shadow-md border-2 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5 ${
                    isHealthy
                      ? 'border-green-200'
                      : 'border-red-200'
                  }`}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className={`rounded-xl p-3 shadow-sm ${
                        isHealthy
                          ? 'bg-gradient-to-br from-green-500 to-emerald-600'
                          : 'bg-gradient-to-br from-red-500 to-rose-600'
                      }`}>
                        <div className="text-white">
                          {getServiceIcon(serviceName)}
                        </div>
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900">
                          {getServiceName(serviceName)}
                        </h3>
                        <p className="text-xs text-gray-500 mt-0.5">{serviceName}</p>
                      </div>
                    </div>
                    {isHealthy ? (
                      <CheckCircle className="h-6 w-6 text-green-600 flex-shrink-0" />
                    ) : (
                      <XCircle className="h-6 w-6 text-red-600 flex-shrink-0" />
                    )}
                  </div>
                  <div className={`mt-3 p-4 rounded-xl border ${
                    isHealthy
                      ? 'bg-gradient-to-br from-green-50 to-emerald-50 border-green-200'
                      : 'bg-gradient-to-br from-red-50 to-rose-50 border-red-200'
                  }`}>
                    <p className={`text-sm font-bold mb-2 ${
                      isHealthy
                        ? 'text-green-800'
                        : 'text-red-800'
                    }`}>
                      {isHealthy ? 'Operational' : 'Unavailable'}
                    </p>
                    <p className={`text-xs ${
                      isHealthy
                        ? 'text-green-700'
                        : 'text-red-700'
                    }`}>
                      {(serviceStatus as any).message}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Additional Information */}
        {health && (
          <div className="mt-8 bg-white rounded-xl shadow-lg border-2 border-gray-100 p-6">
            <h3 className="text-md font-semibold text-gray-900 mb-3">System Information</h3>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <dt className="text-sm font-medium text-gray-500">Service Name</dt>
                <dd className="mt-1 text-sm text-gray-900">{health.service}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Version</dt>
                <dd className="mt-1 text-sm text-gray-900">{health.version}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Overall Status</dt>
                <dd className="mt-1">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    health.status === 'healthy'
                      ? 'bg-green-100 text-green-800'
                      : 'bg-yellow-100 text-yellow-800'
                  }`}>
                    {health.status}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Last Check</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {lastChecked ? lastChecked.toLocaleString() : 'Never'}
                </dd>
              </div>
            </dl>
          </div>
        )}
        </div>
      </div>
    </AppLayout>
  )
}




