'use client'

import { useState, useEffect } from 'react'
import { 
  BarChart3, 
  TrendingUp, 
  Activity, 
  Users, 
  Database, 
  Zap, 
  Clock,
  CheckCircle,
  AlertTriangle,
  ArrowUp,
  ArrowDown
} from 'lucide-react'
import AppLayout from '@/components/layout/AppLayout'
import { StatCardSkeleton } from '@/components/ui/skeleton'
import { apiClient } from '@/lib/api-client'
import { useSession } from 'next-auth/react'

interface AnalyticsData {
  totalProducts: number
  totalDataSources: number
  totalPipelineRuns: number
  successRate: number
  avgProcessingTime: number
  dataQualityScore: number
  recentActivity: Array<{
    id: string
    type: string
    message: string
    timestamp: string
    status: 'success' | 'warning' | 'error'
  }>
  monthlyStats: Array<{
    month: string
    pipeline_runs: number
    products: number
    data_sources: number
    data_processed: number
    success_rate: number
  }>
}

export default function AnalyticsPage() {
  const { data: session } = useSession()
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAnalytics()
  }, [])

  const loadAnalytics = async () => {
    try {
      setLoading(true)
      
      // Get workspace ID from session or fetch from API
      let workspaceId = session?.user?.workspace_ids?.[0]
      
      if (!workspaceId) {
        // Fetch workspaces from API
        const workspacesResponse = await apiClient.getWorkspaces()
        if (workspacesResponse.data && workspacesResponse.data.length > 0) {
          workspaceId = workspacesResponse.data[0].id
        } else {
          setLoading(false)
          return // No workspace available
        }
      }
      
      const response = await apiClient.get(`/api/v1/analytics/metrics?workspace_id=${workspaceId}`)
      const data = response.data
      
      // Transform snake_case to camelCase
      setAnalytics({
        totalProducts: data.total_products || 0,
        totalDataSources: data.total_data_sources || 0,
        totalPipelineRuns: data.total_pipeline_runs || 0,
        successRate: data.success_rate || 0,
        avgProcessingTime: data.avg_processing_time || 0,
        dataQualityScore: data.data_quality_score || 0,
        recentActivity: data.recent_activity || [],
        monthlyStats: (data.monthly_stats || []).map((stat: any) => ({
          month: stat.month,
          pipeline_runs: stat.pipeline_runs || 0,
          products: stat.products || 0,
          data_sources: stat.data_sources || 0,
          data_processed: stat.data_processed || 0,
          success_rate: stat.success_rate || 0
        }))
      })
    } catch (err) {
      console.error('Failed to load analytics:', err)
      // Fallback to mock data if API fails
      const mockData: AnalyticsData = {
        totalProducts: 0,
        totalDataSources: 0,
        totalPipelineRuns: 0,
        successRate: 0,
        avgProcessingTime: 0,
        dataQualityScore: 0,
        recentActivity: [],
        monthlyStats: []
      }
      setAnalytics(mockData)
    } finally {
      setLoading(false)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />
      case 'error':
        return <AlertTriangle className="h-4 w-4 text-red-500" />
      default:
        return <Activity className="h-4 w-4 text-gray-500" />
    }
  }

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString()
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
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
              {[...Array(4)].map((_, i) => (
                <StatCardSkeleton key={i} />
              ))}
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        <div className="max-w-7xl mx-auto">
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-2 tracking-tight">Analytics Dashboard</h1>
            <p className="text-lg text-gray-600">Monitor your data pipeline performance and insights</p>
          </div>

          {/* Enhanced Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
              <div className="flex items-center">
                <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-3 mr-4 shadow-sm">
                  <Database className="h-6 w-6 text-white" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600 mb-1">Total Products</p>
                  <p className="text-3xl font-bold text-gray-900">{analytics?.totalProducts || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
              <div className="flex items-center">
                <div className="bg-gradient-to-br from-green-500 to-emerald-600 rounded-xl p-3 mr-4 shadow-sm">
                  <BarChart3 className="h-6 w-6 text-white" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600 mb-1">Data Sources</p>
                  <p className="text-3xl font-bold text-gray-900">{analytics?.totalDataSources || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
              <div className="flex items-center">
                <div className="bg-gradient-to-br from-purple-500 to-pink-600 rounded-xl p-3 mr-4 shadow-sm">
                  <Zap className="h-6 w-6 text-white" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600 mb-1">Pipeline Runs</p>
                  <p className="text-3xl font-bold text-gray-900">{analytics?.totalPipelineRuns || 0}</p>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
              <div className="flex items-center">
                <div className="bg-gradient-to-br from-orange-500 to-amber-600 rounded-xl p-3 mr-4 shadow-sm">
                  <TrendingUp className="h-6 w-6 text-white" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-600 mb-1">Success Rate</p>
                  <p className="text-3xl font-bold text-gray-900">{analytics?.successRate || 0}%</p>
                </div>
              </div>
            </div>
          </div>

        {/* Enhanced Performance Metrics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-6">Performance Overview</h3>
            <div className="space-y-6">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">Average Processing Time</span>
                  <span className="text-lg font-bold text-gray-900">{analytics?.avgProcessingTime || 0} min</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div 
                    className="bg-gradient-to-r from-blue-500 to-indigo-600 h-2.5 rounded-full transition-all"
                    style={{ width: `${Math.min((analytics?.avgProcessingTime || 0) / 60 * 100, 100)}%` }}
                  ></div>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-700">Data Quality Score</span>
                  <div className="flex items-center">
                    <span className="text-lg font-bold text-gray-900 mr-2">{analytics?.dataQualityScore || 0}%</span>
                    <ArrowUp className="h-4 w-4 text-green-500" />
                  </div>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2.5">
                  <div 
                    className="bg-gradient-to-r from-green-500 to-emerald-600 h-2.5 rounded-full transition-all"
                    style={{ width: `${analytics?.dataQualityScore || 0}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-md border border-gray-100 p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-6">Monthly Trends</h3>
            <div className="space-y-4 max-h-[600px] overflow-y-auto">
              {analytics?.monthlyStats && analytics.monthlyStats.length > 0 ? (
                analytics.monthlyStats.map((stat, index) => (
                  <div key={stat.month} className="border-2 border-gray-100 rounded-lg p-4 hover:border-blue-300 transition-colors">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-base font-semibold text-gray-900">{stat.month}</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      <div className="bg-blue-50 rounded-md p-3 text-center">
                        <div className="font-bold text-blue-700 text-lg">{stat.pipeline_runs || 0}</div>
                        <div className="text-blue-600 text-xs font-medium mt-1">Pipeline Runs</div>
                      </div>
                      <div className="bg-indigo-50 rounded-md p-3 text-center">
                        <div className="font-bold text-indigo-700 text-lg">{stat.products || 0}</div>
                        <div className="text-indigo-600 text-xs font-medium mt-1">Products</div>
                      </div>
                      <div className="bg-teal-50 rounded-md p-3 text-center">
                        <div className="font-bold text-teal-700 text-lg">{stat.data_sources || 0}</div>
                        <div className="text-teal-600 text-xs font-medium mt-1">Data Sources</div>
                      </div>
                      <div className="bg-green-50 rounded-md p-3 text-center">
                        <div className="font-bold text-green-700 text-lg">
                          {stat.data_processed >= 1 
                            ? `${stat.data_processed.toFixed(2)}TB`
                            : stat.data_processed >= 0.001
                            ? `${(stat.data_processed * 1024).toFixed(2)}GB`
                            : `${(stat.data_processed * 1024 * 1024).toFixed(2)}MB`}
                        </div>
                        <div className="text-green-600 text-xs font-medium mt-1">Data Size</div>
                      </div>
                      <div className="bg-purple-50 rounded-md p-3 text-center">
                        <div className="font-bold text-purple-700 text-lg">{stat.success_rate?.toFixed(1) || 0}%</div>
                        <div className="text-purple-600 text-xs font-medium mt-1">Success Rate</div>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <BarChart3 className="h-12 w-12 mx-auto mb-2 text-gray-400" />
                  <p>No monthly data available</p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Enhanced Recent Activity */}
        <div className="bg-white rounded-xl shadow-md border border-gray-100">
          <div className="px-6 py-4 border-b-2 border-gray-100 bg-gradient-to-r from-gray-50 to-blue-50/30">
            <h3 className="text-lg font-semibold text-gray-900">Recent Activity</h3>
          </div>
          <div className="divide-y divide-gray-100">
            {analytics?.recentActivity?.map((activity) => (
              <div key={activity.id} className="px-6 py-4 hover:bg-blue-50/30 transition-colors">
                <div className="flex items-start">
                  <div className="flex-shrink-0 mt-0.5">
                    {getStatusIcon(activity.status)}
                  </div>
                  <div className="ml-4 flex-1">
                    <p className="text-sm font-medium text-gray-900">{activity.message}</p>
                    <p className="text-xs text-gray-500 mt-1">{formatTimestamp(activity.timestamp)}</p>
                  </div>
                </div>
              </div>
            )) || (
              <div className="px-6 py-8 text-center">
                <Activity className="h-12 w-12 text-gray-400 mx-auto mb-2" />
                <p className="text-sm text-gray-500">No recent activity</p>
              </div>
            )}
          </div>
        </div>
        </div>
      </div>
    </AppLayout>
  )
}
