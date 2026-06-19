'use client'

import { useState, useEffect } from 'react'
import { Users, UserPlus, Shield, Mail, MoreVertical, Trash2, Edit, Search, CheckCircle, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Modal, ConfirmModal } from '@/components/ui/modal'
import { ErrorState } from '@/components/ui/error-state'
import { ListSkeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/ui/status-badge'
import AppLayout from '@/components/layout/AppLayout'
import { apiClient } from '@/lib/api-client'
import { useSession } from 'next-auth/react'
interface TeamMember {
  id: string
  user_id: string
  email: string
  name: string
  role: 'owner' | 'admin' | 'editor' | 'viewer'
  created_at: string
}

export default function TeamPage() {
  const { data: session } = useSession()
  const [members, setMembers] = useState<TeamMember[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<'admin' | 'editor' | 'viewer'>('viewer')
  const [inviting, setInviting] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [memberToDelete, setMemberToDelete] = useState<TeamMember | null>(null)
  const [removing, setRemoving] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
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
      loadTeamMembers()
    }
  }, [workspaceId])

  const loadTeamMembers = async () => {
    if (!workspaceId) {
      setError('No workspace available')
      setLoading(false)
      return
    }
    
    try {
      setLoading(true)
      setError(null)
      const response = await apiClient.getWorkspaceMembers(workspaceId)
      
      if (response.error) {
        setError(response.error)
        setMessage({ type: 'error', text: `Failed to load team members: ${response.error}` })
      } else if (response.data) {
        setMembers(response.data as TeamMember[])
      }
    } catch (err: unknown) {
      console.error('Failed to load team members:', err)
      setError('Failed to load team members')
      setMessage({ type: 'error', text: 'Failed to load team members' })
    } finally {
      setLoading(false)
    }
  }

  const handleInviteMember = async () => {
    if (!inviteEmail || !inviteRole) {
      setMessage({ type: 'error', text: 'Please provide email and role' })
      setTimeout(() => setMessage(null), 5000)
      return
    }
    
    if (!workspaceId) {
      setMessage({ type: 'error', text: 'No workspace available' })
      setTimeout(() => setMessage(null), 5000)
      return
    }
    
    try {
      setInviting(true)
      const response = await apiClient.inviteWorkspaceMember(workspaceId, inviteEmail, inviteRole)
      
      if (response.error) {
        setMessage({ type: 'error', text: `Failed to invite member: ${response.error}` })
      } else {
        setMessage({ type: 'success', text: `Invitation sent to ${inviteEmail}` })
        setShowInviteModal(false)
        setInviteEmail('')
        setInviteRole('viewer')
        loadTeamMembers()
      }
      setTimeout(() => setMessage(null), 5000)
    } catch (err: unknown) {
      console.error('Failed to invite member:', err)
      setMessage({ type: 'error', text: 'Failed to invite member' })
      setTimeout(() => setMessage(null), 5000)
    } finally {
      setInviting(false)
    }
  }

  const handleRemoveMember = (member: TeamMember) => {
    setMemberToDelete(member)
    setShowDeleteModal(true)
  }

  const confirmRemoveMember = async () => {
    if (!memberToDelete) return
    
    if (!workspaceId) {
      setMessage({ type: 'error', text: 'No workspace available' })
      setTimeout(() => setMessage(null), 5000)
      return
    }
    
    try {
      setRemoving(true)
      const response = await apiClient.removeWorkspaceMember(workspaceId, memberToDelete.id)
      
      if (response.error) {
        setMessage({ type: 'error', text: `Failed to remove member: ${response.error}` })
      } else {
        setMessage({ type: 'success', text: `${memberToDelete.name} has been removed from the workspace` })
        setMembers(members.filter(m => m.id !== memberToDelete.id))
        setShowDeleteModal(false)
        setMemberToDelete(null)
      }
      setTimeout(() => setMessage(null), 5000)
    } catch (err: unknown) {
      console.error('Failed to remove member:', err)
      setMessage({ type: 'error', text: 'Failed to remove member' })
      setTimeout(() => setMessage(null), 5000)
    } finally {
      setRemoving(false)
    }
  }

  const cancelRemoveMember = () => {
    setShowDeleteModal(false)
    setMemberToDelete(null)
  }

  const getRoleBadgeColor = (role: string) => {
    switch (role) {
      case 'owner': return 'bg-gradient-to-r from-purple-500 to-pink-600 text-white'
      case 'admin': return 'bg-gradient-to-r from-red-500 to-rose-600 text-white'
      case 'editor': return 'bg-gradient-to-r from-blue-500 to-indigo-600 text-white'
      case 'viewer': return 'bg-gradient-to-r from-gray-500 to-slate-600 text-white'
      default: return 'bg-gradient-to-r from-gray-500 to-slate-600 text-white'
    }
  }

  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'owner': return <Shield className="h-4 w-4" />
      case 'admin': return <Shield className="h-4 w-4" />
      case 'editor': return <Edit className="h-4 w-4" />
      case 'viewer': return <Users className="h-4 w-4" />
      default: return <Users className="h-4 w-4" />
    }
  }

  // Filter members based on search query
  const filteredMembers = members.filter(member =>
    member.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    member.email.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
          <div className="max-w-7xl mx-auto">
            <div className="mb-8">
              <div className="h-10 bg-gray-200 rounded-xl w-1/3 mb-2 animate-pulse"></div>
              <div className="h-6 bg-gray-200 rounded w-1/2 animate-pulse"></div>
            </div>
            <ListSkeleton items={5} />
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout>
        <ErrorState
          title="Failed to load team members"
          message={error}
          onRetry={loadTeamMembers}
          variant="error"
        />
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-2 tracking-tight">Team Management</h1>
            <p className="text-lg text-gray-600">Manage team members and their access to workspaces</p>
          </div>

          {/* Message Display */}
          {message && (
            <div className={`mb-6 p-4 rounded-xl border-2 ${
              message.type === 'success' 
                ? 'bg-gradient-to-r from-green-50 to-emerald-50 text-green-800 border-green-200' 
                : 'bg-gradient-to-r from-red-50 to-rose-50 text-red-800 border-red-200'
            }`}>
              <div className="flex items-center">
                {message.type === 'success' ? (
                  <CheckCircle className="h-5 w-5 text-green-600 mr-2" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-600 mr-2" />
                )}
                <p className="font-medium">{message.text}</p>
              </div>
            </div>
          )}

          {/* Header with Invite Button and Search */}
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">Team Members</h2>
              <p className="text-sm text-gray-600">{members.length} member{members.length !== 1 ? 's' : ''}</p>
            </div>
            <div className="flex items-center gap-3 w-full sm:w-auto">
              <div className="relative flex-1 sm:flex-initial sm:w-64">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  type="text"
                  placeholder="Search members..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 border-2"
                />
              </div>
              <Button 
                onClick={() => setShowInviteModal(true)}
                className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg whitespace-nowrap"
              >
                <UserPlus className="h-4 w-4 mr-2" />
                Invite Member
              </Button>
            </div>
          </div>

          {/* Team Members List */}
          <div className="bg-white rounded-xl shadow-md border border-gray-200 overflow-hidden">
            {filteredMembers.length === 0 ? (
              <div className="p-12 text-center">
                <Users className="h-16 w-16 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600 font-medium">
                  {searchQuery ? 'No members found matching your search' : 'No team members yet'}
                </p>
                {!searchQuery && (
                  <Button
                    onClick={() => setShowInviteModal(true)}
                    className="mt-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700"
                  >
                    <UserPlus className="h-4 w-4 mr-2" />
                    Invite Your First Member
                  </Button>
                )}
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {filteredMembers.map((member) => (
                  <div key={member.id} className="px-6 py-4 hover:bg-blue-50/30 transition-colors">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-4 flex-1">
                        <div className="flex-shrink-0">
                          <div className="h-12 w-12 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center ring-2 ring-gray-200">
                            <span className="text-white font-semibold text-lg">
                              {member.name.charAt(0).toUpperCase()}
                            </span>
                          </div>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center space-x-3 mb-1">
                            <h3 className="text-base font-semibold text-gray-900">{member.name}</h3>
                            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${getRoleBadgeColor(member.role)}`}>
                              {getRoleIcon(member.role)}
                              <span className="ml-1 capitalize">{member.role}</span>
                            </span>
                          </div>
                          <p className="text-sm text-gray-600 truncate">{member.email}</p>
                          <p className="text-xs text-gray-400 mt-1">
                            Joined {new Date(member.created_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        {member.role !== 'owner' && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleRemoveMember(member)}
                            className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Role Permissions Info */}
          <div className="mt-8 bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-200 rounded-xl p-6">
            <h3 className="text-lg font-semibold text-blue-900 mb-4">Role Permissions</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white rounded-lg p-4 shadow-sm border border-gray-200">
                <div className="flex items-center space-x-2 mb-2">
                  <div className="bg-gradient-to-br from-purple-500 to-pink-600 rounded-lg p-2">
                    <Shield className="h-5 w-5 text-white" />
                  </div>
                  <span className="font-semibold text-gray-900">Owner</span>
                </div>
                <p className="text-sm text-gray-600">Full access to all features, billing, and team management</p>
              </div>
              <div className="bg-white rounded-lg p-4 shadow-sm border border-gray-200">
                <div className="flex items-center space-x-2 mb-2">
                  <div className="bg-gradient-to-br from-red-500 to-rose-600 rounded-lg p-2">
                    <Shield className="h-5 w-5 text-white" />
                  </div>
                  <span className="font-semibold text-gray-900">Admin</span>
                </div>
                <p className="text-sm text-gray-600">Manage products, data sources, and team members</p>
              </div>
              <div className="bg-white rounded-lg p-4 shadow-sm border border-gray-200">
                <div className="flex items-center space-x-2 mb-2">
                  <div className="bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg p-2">
                    <Edit className="h-5 w-5 text-white" />
                  </div>
                  <span className="font-semibold text-gray-900">Editor</span>
                </div>
                <p className="text-sm text-gray-600">Create and edit products and data sources</p>
              </div>
              <div className="bg-white rounded-lg p-4 shadow-sm border border-gray-200">
                <div className="flex items-center space-x-2 mb-2">
                  <div className="bg-gradient-to-br from-gray-500 to-slate-600 rounded-lg p-2">
                    <Users className="h-5 w-5 text-white" />
                  </div>
                  <span className="font-semibold text-gray-900">Viewer</span>
                </div>
                <p className="text-sm text-gray-600">View products, data sources, and analytics</p>
              </div>
            </div>
          </div>

          {/* Invite Modal */}
          <Modal
            isOpen={showInviteModal}
            onClose={() => {
              setShowInviteModal(false)
              setInviteEmail('')
              setInviteRole('viewer')
            }}
            title="Invite Team Member"
            size="md"
          >
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Email Address</label>
                <Input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="colleague@company.com"
                  className="border-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Role</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as 'admin' | 'editor' | 'viewer')}
                  className="w-full px-4 py-2.5 border-2 border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all bg-white"
                >
                  <option value="viewer">Viewer - View only access</option>
                  <option value="editor">Editor - Create and edit access</option>
                  <option value="admin">Admin - Full management access</option>
                </select>
              </div>
              <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
                <Button 
                  variant="outline" 
                  onClick={() => {
                    setShowInviteModal(false)
                    setInviteEmail('')
                    setInviteRole('viewer')
                  }}
                  className="border-2 hover:border-gray-300 hover:bg-gray-50"
                >
                  Cancel
                </Button>
                <Button 
                  onClick={handleInviteMember}
                  disabled={inviting || !inviteEmail}
                  className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"
                >
                  {inviting ? 'Sending...' : 'Send Invite'}
                </Button>
              </div>
            </div>
          </Modal>

          {/* Delete Confirmation Modal */}
          <ConfirmModal
            isOpen={showDeleteModal}
            onClose={cancelRemoveMember}
            onConfirm={confirmRemoveMember}
            title="Remove Team Member"
            message={
              memberToDelete
                ? `Are you sure you want to remove ${memberToDelete.name} from the team? They will lose access to this workspace and all its data.`
                : ''
            }
            confirmText={removing ? 'Removing...' : 'Remove Member'}
            cancelText="Cancel"
            variant="danger"
          />
        </div>
      </div>
    </AppLayout>
  )
}
