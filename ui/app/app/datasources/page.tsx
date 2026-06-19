'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Plus, Database, Globe, Folder, Server, FileText, Share } from 'lucide-react'
import { Button } from '@/components/ui/button'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'

interface DataSource {
  id: string
  workspace_id: string
  product_id: string
  type: 'web' | 'db' | 'confluence' | 'sharepoint' | 'folder'
  config: any
  last_cursor?: any
  created_at: string
  updated_at?: string
}

interface Product {
  id: string
  name: string
}

export default function DataSourcesPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [dataSources, setDataSources] = useState<DataSource[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/')
      return
    }

    if (status === 'authenticated') {
      loadData()
    }
  }, [status, router])

  const loadData = async () => {
    try {
      setLoading(true)
      
      // Load products first
      const productsResponse = await apiClient.getProducts()
      if (productsResponse.data) {
        setProducts(productsResponse.data as Product[])
        
        // Load data sources for each product
        const allDataSources: DataSource[] = []
        for (const product of productsResponse.data as Product[]) {
          const dataSourcesResponse = await apiClient.getDataSources(product.id)
          if (dataSourcesResponse.data) {
            allDataSources.push(...(dataSourcesResponse.data as DataSource[]))
          }
        }
        setDataSources(allDataSources)
      }
    } catch (err) {
      setError('Failed to load data sources')
    } finally {
      setLoading(false)
    }
  }

  const getDataSourceTypeIcon = (type: string) => {
    switch (type) {
      case 'web': return <Globe className="h-5 w-5 text-blue-600" />
      case 'db': return <Server className="h-5 w-5 text-green-600" />
      case 'confluence': return <FileText className="h-5 w-5 text-purple-600" />
      case 'sharepoint': return <Share className="h-5 w-5 text-orange-600" />
      case 'folder': return <Folder className="h-5 w-5 text-gray-600" />
      default: return <Database className="h-5 w-5 text-gray-600" />
    }
  }

  const getDataSourceTypeName = (type: string) => {
    switch (type) {
      case 'web': return 'Web URL'
      case 'db': return 'Database'
      case 'confluence': return 'Confluence'
      case 'sharepoint': return 'SharePoint'
      case 'folder': return 'Local Folder'
      default: return type
    }
  }

  const getProductName = (productId: string) => {
    const product = products.find(p => p.id === productId)
    return product ? product.name : 'Unknown Product'
  }

  if (status === 'loading' || loading) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="animate-pulse">
            <div className="h-8 bg-gray-200 rounded w-1/4 mb-6"></div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="bg-white p-6 rounded-lg shadow-sm border">
                  <div className="h-4 bg-gray-200 rounded w-1/2 mb-2"></div>
                  <div className="h-4 bg-gray-200 rounded w-3/4 mb-4"></div>
                  <div className="h-3 bg-gray-200 rounded w-1/3"></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="text-center py-12">
            <p className="text-red-600 mb-4">Error: {error}</p>
            <Button onClick={loadData}>Try Again</Button>
          </div>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        {/* Header */}
        <div className="mb-8">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-4xl font-bold text-gray-900 mb-2 tracking-tight">Data Sources</h1>
              <p className="text-lg text-gray-600">Manage all your data sources across products</p>
            </div>
            <div className="flex space-x-3">
              <Button 
                variant="outline" 
                className="border-2 hover:border-blue-300 hover:bg-blue-50"
                onClick={() => router.push('/app/products')}
              >
                <Database className="h-4 w-4 mr-2" />
                Import Data Source
              </Button>
              <Button 
                className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"
                onClick={() => router.push('/app/products')}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Data Source
              </Button>
            </div>
          </div>
        </div>

        {/* Enhanced Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white p-6 rounded-xl shadow-md border border-gray-100 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
            <div className="flex items-center">
              <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-3 mr-4 shadow-sm">
                <Database className="h-6 w-6 text-white" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600 mb-1">Total Sources</p>
                <p className="text-3xl font-bold text-gray-900">{dataSources.length}</p>
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-xl shadow-md border border-gray-100 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
            <div className="flex items-center">
              <div className="bg-gradient-to-br from-green-500 to-emerald-600 rounded-xl p-3 mr-4 shadow-sm">
                <Globe className="h-6 w-6 text-white" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600 mb-1">Web Sources</p>
                <p className="text-3xl font-bold text-gray-900">
                  {dataSources.filter(ds => ds.type === 'web').length}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-xl shadow-md border border-gray-100 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
            <div className="flex items-center">
              <div className="bg-gradient-to-br from-purple-500 to-pink-600 rounded-xl p-3 mr-4 shadow-sm">
                <Server className="h-6 w-6 text-white" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600 mb-1">Database Sources</p>
                <p className="text-3xl font-bold text-gray-900">
                  {dataSources.filter(ds => ds.type === 'db').length}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-xl shadow-md border border-gray-100 hover:shadow-lg transition-all duration-200 hover:-translate-y-0.5">
            <div className="flex items-center">
              <div className="bg-gradient-to-br from-orange-500 to-amber-600 rounded-xl p-3 mr-4 shadow-sm">
                <Folder className="h-6 w-6 text-white" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600 mb-1">File Sources</p>
                <p className="text-3xl font-bold text-gray-900">
                  {dataSources.filter(ds => ds.type === 'folder').length}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Data Sources List */}
        <div className="bg-white rounded-xl shadow-md border border-gray-100">
          <div className="p-6 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">All Data Sources</h3>
          </div>
          <div className="p-6">
            {dataSources.length === 0 ? (
              <div className="text-center py-12">
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-4">
                  <Database className="h-10 w-10 text-blue-600" />
                </div>
                <h4 className="text-xl font-semibold text-gray-900 mb-2">No data sources yet</h4>
                <p className="text-gray-600 mb-6 max-w-md mx-auto">Get started by adding your first data source to a product.</p>
                <Link href="/app/products">
                  <Button className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg">
                    <Plus className="h-4 w-4 mr-2" />
                    Go to Products
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {dataSources.map((dataSource) => (
                  <div key={dataSource.id} className="border-2 border-gray-200 rounded-xl p-5 hover:bg-blue-50/50 hover:border-blue-300 transition-all duration-200 hover:shadow-md group">
                    <div className="flex items-start mb-4">
                      <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl p-2.5 mr-3 flex-shrink-0 shadow-sm group-hover:scale-110 transition-transform">
                        {getDataSourceTypeIcon(dataSource.type)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <h4 className="font-semibold text-gray-900 text-sm mb-1 group-hover:text-blue-600 transition-colors">
                          {getDataSourceTypeName(dataSource.type)}
                        </h4>
                        <p className="text-xs text-gray-600 truncate mb-1">
                          Product: {getProductName(dataSource.product_id)}
                        </p>
                        <p className="text-xs text-gray-500">
                          Created {new Date(dataSource.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                      <div className="flex items-center bg-green-50 px-2 py-1 rounded-md border border-green-200">
                        <div className="w-2 h-2 bg-green-500 rounded-full mr-1.5 animate-pulse"></div>
                        <span className="text-xs font-medium text-green-700">Active</span>
                      </div>
                      <Link href={`/app/products/${dataSource.product_id}`}>
                        <Button variant="outline" size="sm" className="border-2 hover:border-blue-300 hover:bg-blue-50">
                          View Product
                        </Button>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  )
}