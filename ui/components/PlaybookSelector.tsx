'use client'

import { useState, useEffect } from 'react'
import { Loader2, BookOpen, AlertCircle, Edit2 } from 'lucide-react'
import { Label } from './ui/label'
import { Button } from './ui/button'
import { apiClient, PlaybookInfo } from '@/lib/api-client'
import { useToast } from './ui/toast'
import { PlaybookEditor } from './PlaybookEditor'

interface PlaybookSelectorProps {
  value?: string
  onChange: (playbookId: string | undefined) => void
  disabled?: boolean
  showDescription?: boolean
  workspaceId?: string
  showCustomizeButton?: boolean
}

export function PlaybookSelector({
  value,
  onChange,
  disabled = false,
  showDescription = true,
  workspaceId,
  showCustomizeButton = true,
}: PlaybookSelectorProps) {
  const [playbooks, setPlaybooks] = useState<PlaybookInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const { addToast } = useToast()

  useEffect(() => {
    loadPlaybooks()
  }, [workspaceId])

  const loadPlaybooks = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.listPlaybooks(workspaceId)
      if (response.error) {
        setError(response.error)
        addToast({
          type: 'error',
          message: `Failed to load playbooks: ${response.error}`,
        })
      } else if (response.data) {
        setPlaybooks(response.data)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load playbooks'
      setError(errorMessage)
      addToast({
        type: 'error',
        message: errorMessage,
      })
    } finally {
      setLoading(false)
    }
  }

  const handlePlaybookSaved = (newPlaybookId: string) => {
    // Reload playbooks to include the new custom playbook
    loadPlaybooks()
    // Optionally select the newly created playbook
    onChange(newPlaybookId)
  }

  const selectedPlaybook = playbooks.find((pb) => pb.id === value)

  if (loading) {
    return (
      <div className="space-y-2">
        <Label>Preprocessing Playbook (Optional)</Label>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading playbooks...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-2">
        <Label>Preprocessing Playbook (Optional)</Label>
        <div className="flex items-center gap-2 text-sm text-red-600">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="playbook-select">
            Preprocessing Playbook <span className="text-gray-500 font-normal">(Optional)</span>
          </Label>
          {showCustomizeButton && workspaceId && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowEditor(true)}
              disabled={disabled}
              className="flex items-center gap-1"
            >
              <Edit2 className="h-3 w-3" />
              Customize
            </Button>
          )}
        </div>
        <select
          id="playbook-select"
          value={value || ''}
          onChange={(e) => onChange(e.target.value || undefined)}
          disabled={disabled}
          className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
        >
          <option value="">Auto-Detect</option>
          <optgroup label="Built-in Playbooks">
            {playbooks.filter((pb: any) => !pb.path?.startsWith('custom:')).map((playbook) => (
              <option key={playbook.id} value={playbook.id}>
                {playbook.id}
              </option>
            ))}
          </optgroup>
          {playbooks.filter((pb: any) => pb.path?.startsWith('custom:')).length > 0 && (
            <optgroup label="Custom Playbooks">
              {playbooks.filter((pb: any) => pb.path?.startsWith('custom:')).map((playbook) => (
                <option key={playbook.id} value={playbook.id}>
                  {playbook.id} (Custom)
                </option>
              ))}
            </optgroup>
          )}
        </select>
        {showDescription && selectedPlaybook && (
          <p className="text-sm text-gray-600 mt-1 flex items-start gap-2">
            <BookOpen className="h-4 w-4 mt-0.5 flex-shrink-0" />
            <span>{selectedPlaybook.description}</span>
          </p>
        )}
        {showDescription && !value && (
          <p className="text-sm text-gray-500 mt-1">
            If no playbook is selected, the system will automatically detect the best playbook based on your content.
            Click "Customize" to create or edit a custom playbook.
          </p>
        )}
      </div>

      {/* Playbook Editor Modal */}
      {showEditor && workspaceId && (
        <PlaybookEditor
          playbookId={value && value.startsWith('CUSTOM_') ? value : undefined}
          workspaceId={workspaceId}
          basePlaybookId={value && !value.startsWith('CUSTOM_') ? value : undefined}
          isOpen={showEditor}
          onClose={() => setShowEditor(false)}
          onSave={handlePlaybookSaved}
        />
      )}
    </>
  )
}



