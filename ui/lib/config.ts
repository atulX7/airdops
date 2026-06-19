/**
 * Centralized configuration for API URLs
 */

// Use HTTPS for production, HTTP only for local development
const DEFAULT_API_URL = "http://127.0.0.1:8000"

/**
 * Get the API base URL from environment variables or return the default
 * Uses 127.0.0.1 instead of localhost for better server-side compatibility
 * 
 * In production (browser), if the page is loaded over HTTPS, use HTTPS for API calls
 * to avoid Mixed Content errors.
 * 
 * @returns The API base URL
 */
export function getApiUrl(): string {
  // First check environment variables (set at build time)
  const envUrl = process.env.NEXT_PUBLIC_API_URL || 
                 process.env.NEXT_PUBLIC_API_BASE || 
                 process.env.API_URL
  
  if (envUrl) {
    return envUrl
  }
  
  // In browser, use the current origin if on HTTPS (prevents Mixed Content errors)
  if (typeof window !== 'undefined') {
    if (window.location.protocol === 'https:') {
      return window.location.origin
    }
  }
  
  // Fallback to default (HTTP for local development)
  return DEFAULT_API_URL
}

/**
 * Default API URL constant (for cases where you need the default value directly)
 */
export const DEFAULT_API_BASE_URL = DEFAULT_API_URL

