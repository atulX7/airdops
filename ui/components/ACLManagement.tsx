'use client'

import { useState, useEffect } from 'react'
import { Loader2, AlertCircle, Plus, Trash2, Shield, User, Package, Tag } from 'lucide-react'
import { apiClient, ACL } from '@/lib/api-client'
import { useToast } from './ui/toast'
import { Button } from './ui/button'

interface ACLManagementProps {
  productId: string
  showTitle?: boolean
}

interface ACLFormData {
  user_id: string
  access_type: 'FULL' | 'INDEX' | 'DOCUMENT' | 'FIELD'
  index_scope: string
  doc_scope: string
  field_scope: string
}

export function ACLManagement({ productId, showTitle = true }: ACLManagementProps) {
  const [acls, setAcls] = useState<ACL[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const { addToast } = useToast()

  const [formData, setFormData] = useState<ACLFormData>({
    user_id: '',
    access_type: 'FULL',
    index_scope: '',
    doc_scope: '',
    field_scope: '',
  })

  useEffect(() => {
    loadACLs()
  }, [productId])

  const loadACLs = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.listACLs({ product_id: productId })
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load ACLs: ${response.error}`,
        })
      } else if (response.data) {
        setAcls(response.data)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load ACLs'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const response = await apiClient.createACL({
        user_id: formData.user_id,
        product_id: productId,
        access_type: formData.access_type,
        index_scope: formData.index_scope || undefined,
        doc_scope: formData.doc_scope || undefined,
        field_scope: formData.field_scope || undefined,
      })

      if (response.error) {
        addToast({
          type: 'error',
          message: `Failed to create ACL: ${response.error}`,
        })
      } else {
        addToast({
          type: 'success',
          message: 'ACL created successfully',
        })
        setShowCreateForm(false)
        setFormData({
          user_id: '',
          access_type: 'FULL',
          index_scope: '',
          doc_scope: '',
          field_scope: '',
        })
        loadACLs()
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to create ACL',
      })
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (aclId: string) => {
    if (!confirm('Are you sure you want to delete this ACL entry?')) {
      return
    }

    setDeleting(aclId)
    try {
      const response = await apiClient.deleteACLs({ acl_id: aclId })

      if (response.error) {
        addToast({
          type: 'error',
          message: `Failed to delete ACL: ${response.error}`,
        })
      } else {
        addToast({
          type: 'success',
          message: `Deleted ${response.data?.deleted || 1} ACL entry(ies)`,
        })
        loadACLs()
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to delete ACL',
      })
    } finally {
      setDeleting(null)
    }
  }

  const getAccessTypeColor = (type: string) => {
    switch (type) {
      case 'FULL':
        return 'bg-green-100 text-green-800'
      case 'INDEX':
        return 'bg-blue-100 text-blue-800'
      case 'DOCUMENT':
        return 'bg-purple-100 text-purple-800'
      case 'FIELD':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  if (loading && acls.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Access Control Lists</h2>}
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 text-gray-400 animate-spin mr-2" />
          <p className="text-gray-600">Loading ACLs...</p>
        </div>
      </div>
    )
  }

  if (error && acls.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {showTitle && <h2 className="text-lg font-semibold text-gray-900 mb-4">Access Control Lists</h2>}
        <div className="flex items-center justify-center py-8">
          <AlertCircle className="h-6 w-6 text-red-500 mr-2" />
          <p className="text-red-600">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      {showTitle && (
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Access Control Lists</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Add ACL
          </Button>
        </div>
      )}

      {/* Create Form */}
      {showCreateForm && (
        <div className="mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
          <h3 className="text-md font-medium text-gray-900 mb-4">Create New ACL Entry</h3>
          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                User ID <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.user_id}
                onChange={(e) => setFormData({ ...formData, user_id: e.target.value })}
                required
                placeholder="Enter user UUID"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Access Type <span className="text-red-500">*</span>
              </label>
              <select
                value={formData.access_type}
                onChange={(e) => setFormData({ ...formData, access_type: e.target.value as any })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="FULL">Full Access</option>
                <option value="INDEX">Index Scope</option>
                <option value="DOCUMENT">Document Scope</option>
                <option value="FIELD">Field Scope</option>
              </select>
            </div>
            {formData.access_type === 'INDEX' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Index Scope (comma-separated)
                </label>
                <input
                  type="text"
                  value={formData.index_scope}
                  onChange={(e) => setFormData({ ...formData, index_scope: e.target.value })}
                  placeholder="e.g., collection1, collection2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
            {formData.access_type === 'DOCUMENT' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Document Scope (comma-separated)
                </label>
                <input
                  type="text"
                  value={formData.doc_scope}
                  onChange={(e) => setFormData({ ...formData, doc_scope: e.target.value })}
                  placeholder="e.g., doc1, doc2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
            {formData.access_type === 'FIELD' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Field Scope (comma-separated)
                </label>
                <input
                  type="text"
                  value={formData.field_scope}
                  onChange={(e) => setFormData({ ...formData, field_scope: e.target.value })}
                  placeholder="e.g., field1, field2"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
            <div className="flex gap-2">
              <Button type="submit" disabled={creating}>
                {creating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Creating...
                  </>
                ) : (
                  'Create ACL'
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowCreateForm(false)}
                disabled={creating}
              >
                Cancel
              </Button>
            </div>
          </form>
        </div>
      )}

      {/* ACL List */}
      {acls.length === 0 ? (
        <div className="text-center py-8">
          <Shield className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No ACL entries</h3>
          <p className="text-gray-600 mb-4">Create an ACL entry to control access to this product.</p>
          {!showCreateForm && (
            <Button variant="outline" onClick={() => setShowCreateForm(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Add ACL
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  User ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Access Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Scope
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {acls.map((acl) => (
                <tr key={acl.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-gray-900">
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-gray-400" />
                      <span className="truncate max-w-xs">{acl.user_id}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getAccessTypeColor(acl.access_type || 'FULL')}`}>
                      {acl.access_type || 'FULL'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    <div className="space-y-1">
                      {acl.index_scope && (
                        <div className="flex items-center gap-1 text-xs">
                          <Package className="h-3 w-3 text-blue-500" />
                          <span className="text-gray-600">Index: {acl.index_scope}</span>
                        </div>
                      )}
                      {acl.doc_scope && (
                        <div className="flex items-center gap-1 text-xs">
                          <Package className="h-3 w-3 text-purple-500" />
                          <span className="text-gray-600">Doc: {acl.doc_scope}</span>
                        </div>
                      )}
                      {acl.field_scope && (
                        <div className="flex items-center gap-1 text-xs">
                          <Tag className="h-3 w-3 text-yellow-500" />
                          <span className="text-gray-600">Field: {acl.field_scope}</span>
                        </div>
                      )}
                      {!acl.index_scope && !acl.doc_scope && !acl.field_scope && (
                        <span className="text-gray-400 text-xs">No scope restrictions</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                    {acl.created_at ? new Date(acl.created_at).toLocaleDateString() : 'N/A'}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-sm">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => acl.id && handleDelete(acl.id)}
                      disabled={deleting === acl.id || !acl.id}
                      className="text-red-600 hover:text-red-800"
                    >
                      {deleting === acl.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}




