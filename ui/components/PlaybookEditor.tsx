'use client'

import { useState, useEffect } from 'react'
import { Button } from './ui/button'
import { Label } from './ui/label'
import { apiClient } from '@/lib/api-client'
import { useToast } from './ui/toast'
import { Save, X, Copy, Eye, Edit2, Loader2, AlertCircle } from 'lucide-react'

interface PlaybookEditorProps {
  playbookId?: string
  workspaceId: string
  basePlaybookId?: string
  isOpen: boolean
  onClose: () => void
  onSave?: (playbookId: string) => void
}

export function PlaybookEditor({
  playbookId,
  workspaceId,
  basePlaybookId,
  isOpen,
  onClose,
  onSave
}: PlaybookEditorProps) {
  const [yamlContent, setYamlContent] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [customPlaybookId, setCustomPlaybookId] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isReadOnly, setIsReadOnly] = useState(false)
  const { addToast } = useToast()

  useEffect(() => {
    if (isOpen) {
      loadPlaybook()
    } else {
      // Reset state when closed
      setYamlContent('')
      setName('')
      setDescription('')
      setCustomPlaybookId('')
      setError(null)
      setIsReadOnly(false)
    }
  }, [isOpen, playbookId, basePlaybookId, workspaceId])

  const loadPlaybook = async () => {
    if (!playbookId) {
      // Creating new custom playbook based on base
      if (basePlaybookId) {
        setLoading(true)
        try {
          const response = await apiClient.getPlaybookYaml(basePlaybookId)
          if (response.error) {
            setError(response.error)
          } else {
            setYamlContent(response.data.yaml || '')
            setName(`Custom ${basePlaybookId}`)
            setCustomPlaybookId(`CUSTOM_${basePlaybookId}`)
            setIsReadOnly(false)
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to load playbook')
        } finally {
          setLoading(false)
        }
      } else {
        // New empty playbook
        setYamlContent(`id: CUSTOM_PLAYBOOK
description: Custom preprocessing playbook

probes:
  must_match: []
  nice_to_have: []

pre_normalizers: []

page_fences: []

headers: []

section_aliases: {}

audience_rules: []

chunking:
  strategy: sentence
  max_tokens: 1000
  overlap_sentences: 2
  hard_overlap_chars: 250

quality_gates:
  min_sections: 3
  max_mid_sentence_boundary_rate: 0.2
`)
        setName('Custom Playbook')
        setCustomPlaybookId('CUSTOM_PLAYBOOK')
        setIsReadOnly(false)
      }
    } else {
      // Loading existing playbook
      setLoading(true)
      try {
        // Check if it's a custom playbook
        const customResponse = await apiClient.getCustomPlaybook(playbookId, workspaceId)
        if (!customResponse.error && customResponse.data) {
          // Custom playbook
          const pb = customResponse.data
          setYamlContent(pb.yaml_content)
          setName(pb.name)
          setDescription(pb.description || '')
          setCustomPlaybookId(pb.playbook_id)
          setIsReadOnly(false)
        } else {
          // Built-in playbook - allow editing to create custom copy
          const response = await apiClient.getPlaybookYaml(playbookId)
          if (response.error) {
            setError(response.error)
          } else {
            setYamlContent(response.data.yaml || '')
            setName(`Custom ${playbookId}`)
            setCustomPlaybookId(`CUSTOM_${playbookId}`)
            setIsReadOnly(false) // Allow editing - user can customize name/ID before saving
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load playbook')
      } finally {
        setLoading(false)
      }
    }
  }

  const handleSave = async () => {
    if (!yamlContent.trim()) {
      setError('YAML content cannot be empty')
      return
    }

    if (!customPlaybookId.trim()) {
      setError('Playbook ID is required')
      return
    }

    setSaving(true)
    setError(null)

    try {
      if (playbookId && !isReadOnly) {
        // Update existing custom playbook
        const response = await apiClient.updateCustomPlaybook(playbookId, workspaceId, {
          name,
          description: description || undefined,
          yaml_content: yamlContent
        })

        if (response.error) {
          setError(response.error)
          // Show error in toast for instant feedback
          addToast({
            type: 'error',
            message: `Failed to update playbook: ${response.error}`
          })
        } else {
          // Show instant toast notification
          addToast({
            type: 'success',
            message: `Custom playbook "${name}" has been updated successfully!`
          })
          onSave?.(customPlaybookId)
          // Close editor modal immediately after successful save
          onClose()
        }
      } else {
        // Create new custom playbook
        const response = await apiClient.createCustomPlaybook(workspaceId, {
          name,
          playbook_id: customPlaybookId.toUpperCase(),
          description: description || undefined,
          yaml_content: yamlContent,
          base_playbook_id: basePlaybookId || undefined
        })

        if (response.error) {
          setError(response.error)
          // Show error in toast for instant feedback
          addToast({
            type: 'error',
            message: `Failed to create playbook: ${response.error}`
          })
        } else {
          // Show instant toast notification
          addToast({
            type: 'success',
            message: `Custom playbook "${name}" has been created successfully!`
          })
          onSave?.(customPlaybookId.toUpperCase())
          // Close editor modal immediately after successful save
          onClose()
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to save playbook'
      setError(errorMessage)
      // Show error in toast for instant feedback
      addToast({
        type: 'error',
        message: errorMessage
      })
    } finally {
      setSaving(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(yamlContent)
    addToast({
      type: 'success',
      message: 'YAML content copied to clipboard'
    })
  }

  if (!isOpen) return null

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div>
              <h2 className="text-2xl font-semibold text-gray-900">
                {playbookId && !basePlaybookId ? 'Edit Custom Playbook' : 'Create Custom Playbook'}
              </h2>
              {basePlaybookId && (
                <p className="text-sm text-gray-500 mt-1">
                  Based on: <strong>{basePlaybookId}</strong>
                </p>
              )}
            </div>
            <Button
              variant="outline"
              onClick={onClose}
              disabled={saving}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
              </div>
            ) : error ? (
              <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg">
                <AlertCircle className="h-5 w-5 text-red-500" />
                <p className="text-sm text-red-700">{error}</p>
              </div>
            ) : (
              <>
                {/* Playbook Metadata */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="playbook-name">Playbook Name</Label>
                    <input
                      id="playbook-name"
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      disabled={isReadOnly || saving}
                      className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md"
                      placeholder="My Custom Playbook"
                    />
                  </div>
                  <div>
                    <Label htmlFor="playbook-id">Playbook ID</Label>
                    <input
                      id="playbook-id"
                      type="text"
                      value={customPlaybookId}
                      onChange={(e) => setCustomPlaybookId(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_'))}
                      disabled={!!playbookId || saving}  // Allow editing ID when creating from built-in
                      className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md font-mono text-sm"
                      placeholder="CUSTOM_PLAYBOOK"
                    />
                    <p className="text-xs text-gray-500 mt-1">Must be unique (uppercase letters, numbers, underscores only)</p>
                  </div>
                </div>

                <div>
                  <Label htmlFor="playbook-description">Description (Optional)</Label>
                  <input
                    id="playbook-description"
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    disabled={isReadOnly || saving}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md"
                    placeholder="Brief description of what this playbook is for"
                  />
                </div>

                {/* YAML Editor */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label htmlFor="yaml-content">Playbook YAML Configuration</Label>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCopy}
                        disabled={saving}
                      >
                        <Copy className="h-4 w-4 mr-1" />
                        Copy
                      </Button>
                      {isReadOnly && (
                        <span className="text-xs text-gray-500 bg-yellow-50 px-2 py-1 rounded">
                          Read-only (built-in playbook). Save as custom to edit.
                        </span>
                      )}
                    </div>
                  </div>
                  <textarea
                    id="yaml-content"
                    value={yamlContent}
                    onChange={(e) => setYamlContent(e.target.value)}
                    disabled={isReadOnly || saving}
                    className="w-full h-96 font-mono text-sm border border-gray-300 rounded-md p-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Enter playbook YAML content..."
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Edit the YAML configuration above. The playbook will be validated when you save.
                  </p>
                </div>

                {basePlaybookId && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <p className="text-sm text-blue-800">
                      <strong>Note:</strong> This playbook is based on <strong>{basePlaybookId}</strong>. 
                      You can customize the name, ID, and YAML configuration before saving as your own custom playbook.
                    </p>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || loading}
            >
              {saving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  {playbookId && !basePlaybookId ? 'Update Custom Playbook' : 'Save as Custom Playbook'}
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

    </>
  )
}

