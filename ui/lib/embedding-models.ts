/**
 * Embedding model configuration for frontend.
 *
 * Models are fetched from the backend API - backend is the single source of truth.
 * When workspace_id is provided, paid models include `enabled` and `disabled_reason`.
 */

import { apiClient } from './api-client'

export interface EmbeddingModelOption {
  value: string
  label: string
  disabled?: boolean
  disabledReason?: string
}

export interface EmbeddingModel {
  id: string
  name: string
  description: string
  dimension: number
  requires_api_key: boolean
  cost_per_token?: number
  metadata?: Record<string, any>
  /** Present when listing with workspace_id: false if provider key missing */
  enabled?: boolean
  disabled_reason?: string | null
}

// Cache per workspace (or global when workspace id empty)
let embeddingModelsCache: EmbeddingModel[] | null = null
let embeddingModelsCacheTime: number = 0
let embeddingModelsCacheWorkspaceKey: string = ''
const CACHE_DURATION = 5 * 60 * 1000 // 5 minutes

/**
 * Fetch embedding models from the API.
 *
 * @param useCache - Whether to use cached models if available
 * @param workspaceId - Optional workspace scope for provider key checks
 */
async function fetchEmbeddingModels(useCache: boolean = true, workspaceId?: string): Promise<EmbeddingModel[]> {
  const wsKey = workspaceId || ''
  if (
    useCache &&
    embeddingModelsCache &&
    Date.now() - embeddingModelsCacheTime < CACHE_DURATION &&
    embeddingModelsCacheWorkspaceKey === wsKey
  ) {
    return embeddingModelsCache
  }

  try {
    const response = await apiClient.getEmbeddingModels({
      free_only: false,
      workspace_id: workspaceId,
    })

    if (response.error || !response.data) {
      const errorMessage = response.error || 'Failed to fetch embedding models from API'
      console.error('Failed to fetch embedding models from API:', errorMessage)
      embeddingModelsCache = null
      throw new Error(errorMessage)
    }

    embeddingModelsCache = response.data.models || []
    embeddingModelsCacheTime = Date.now()
    embeddingModelsCacheWorkspaceKey = wsKey

    return embeddingModelsCache || []
  } catch (error) {
    console.error('Error fetching embedding models:', error)
    embeddingModelsCache = null
    throw error
  }
}

/**
 * Get list of embedding model options for select dropdowns.
 *
 * @param useCache - Whether to use cached models if available
 * @param workspaceId - Optional workspace scope for paid model enablement
 */
export async function getEmbeddingModelOptions(
  useCache: boolean = true,
  workspaceId?: string
): Promise<EmbeddingModelOption[]> {
  try {
    const models = await fetchEmbeddingModels(useCache, workspaceId)
    return models.map((model) => {
      const enabled = model.enabled !== false
      const disabledReason = model.disabled_reason || undefined
      return {
        value: model.id,
        label: model.name,
        disabled: !enabled,
        disabledReason,
      }
    })
  } catch (error) {
    console.error('Failed to get embedding model options:', error)
    return []
  }
}

/**
 * Synchronous version that uses cache only.
 */
export function getEmbeddingModelOptionsSync(): EmbeddingModelOption[] {
  if (embeddingModelsCache) {
    return embeddingModelsCache.map((model) => ({
      value: model.id,
      label: model.name,
      disabled: model.enabled === false,
      disabledReason: model.disabled_reason || undefined,
    }))
  }

  return []
}

/**
 * Get the embedding dimension for a given model name.
 */
export async function getEmbeddingDimension(modelName: string): Promise<number | undefined> {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find((m) => m.id === modelName)
    if (model) return model.dimension
  }

  try {
    const models = await fetchEmbeddingModels(false)
    const model = models.find((m) => m.id === modelName)
    if (model) return model.dimension
  } catch (error) {
    console.error('Error fetching embedding dimension:', error)
  }

  return undefined
}

/**
 * Synchronous version that uses cache only.
 */
export function getEmbeddingDimensionSync(modelName: string): number | undefined {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find((m) => m.id === modelName)
    if (model) return model.dimension
  }

  return undefined
}

/**
 * Check if an embedding model requires an API key.
 */
export async function requiresApiKey(modelName: string): Promise<boolean> {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find((m) => m.id === modelName)
    if (model) return model.requires_api_key
  }

  try {
    const models = await fetchEmbeddingModels(false)
    const model = models.find((m) => m.id === modelName)
    if (model) return model.requires_api_key || false
  } catch (error) {
    console.error('Error checking API key requirement:', error)
  }

  return false
}

/**
 * Synchronous version that uses cache only.
 */
export function requiresApiKeySync(modelName: string): boolean {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find((m) => m.id === modelName)
    if (model) return model.requires_api_key
  }

  return false
}

/**
 * Format embedding model name for display.
 */
export function formatEmbeddingModelName(modelName: string): string {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find((m) => m.id === modelName)
    if (model) return model.name
  }

  return modelName
}

/**
 * Preload embedding models from API (call this after workspace is known).
 */
export async function preloadEmbeddingModels(workspaceId?: string): Promise<void> {
  try {
    await fetchEmbeddingModels(false, workspaceId)
  } catch (error) {
    console.error('Failed to preload embedding models:', error)
  }
}

/** Call after workspace API key changes so product edit refetches model availability. */
export function invalidateEmbeddingModelsCache(): void {
  embeddingModelsCache = null
  embeddingModelsCacheTime = 0
  embeddingModelsCacheWorkspaceKey = ''
}
