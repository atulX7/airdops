'use client'

import { ReactNode } from 'react'
import { LucideIcon } from 'lucide-react'

interface ComingSoonBadgeProps {
  /**
   * Title of the feature/section
   */
  title: string
  /**
   * Description of what the feature will provide
   */
  description: string
  /**
   * Icon to display (from lucide-react)
   */
  icon: LucideIcon
  /**
   * Optional custom message (defaults to "Available in Next Release")
   */
  message?: string
  /**
   * Optional additional content to display
   */
  children?: ReactNode
  /**
   * Optional custom className for the container
   */
  className?: string
  /**
   * Display variant: 'full' for full section, 'compact' for card grid
   */
  variant?: 'full' | 'compact'
}

/**
 * Enterprise-grade "Coming Soon" badge component
 * 
 * Displays a professional, non-clickable placeholder for features
 * that are planned for future releases. Includes animated badge,
 * gradient backgrounds, and clear messaging.
 * 
 * @example
 * ```tsx
 * <ComingSoonBadge
 *   title="Pipeline Artifacts"
 *   description="View and manage all artifacts generated during pipeline execution"
 *   icon={Package}
 * />
 * ```
 */
export function ComingSoonBadge({
  title,
  description,
  icon: Icon,
  message = "Available in Next Release",
  children,
  className = "",
  variant = 'full',
}: ComingSoonBadgeProps) {
  // Compact variant for card grid layout
  if (variant === 'compact') {
    return (
      <div className={`border border-gray-200 rounded-lg p-4 relative overflow-hidden cursor-default flex flex-col ${className}`}>
        {/* Decorative gradient background */}
        <div className="absolute inset-0 bg-gradient-to-br from-blue-50/30 via-indigo-50/20 to-purple-50/30 opacity-50"></div>
        
        <div className="relative">
          {/* Icon with badge */}
          <div className="relative mb-3">
            <div className="bg-gradient-to-br from-blue-100 to-indigo-100 rounded-lg p-2.5 w-fit">
              <Icon className="h-8 w-8 text-blue-600" />
            </div>
            <span className="absolute -top-1 -right-1 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 text-white shadow-sm animate-pulse">
              <span className="relative flex h-1.5 w-1.5 mr-1">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-white"></span>
              </span>
              Coming Soon
            </span>
          </div>
          
          {/* Title */}
          <h3 className="font-medium text-gray-900 mb-1">{title}</h3>
          
          {/* Description */}
          <p className="text-sm text-gray-600 mb-3">{description}</p>
          
          {/* Compact message badge - only show if message is provided */}
          {message && (
            <div className="inline-flex items-center px-2.5 py-1 rounded-md bg-gradient-to-r from-blue-500 to-indigo-600 text-white text-xs font-medium shadow-sm">
              <span className="mr-1.5 text-[10px]">🚀</span>
              {message}
            </div>
          )}
        </div>
      </div>
    )
  }

  // Full variant for section layout
  return (
    <div className={`bg-white rounded-lg shadow-sm border border-gray-200 p-6 relative overflow-hidden ${className}`}>
      {/* Decorative gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 via-indigo-50/30 to-purple-50/50 opacity-50"></div>
      
      <div className="relative">
        {/* Header with title and badge */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
              <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 text-white shadow-md animate-pulse">
                <span className="relative flex h-2 w-2 mr-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
                </span>
                Coming Soon
              </span>
            </div>
            <p className="text-sm text-gray-600 mt-1">{description}</p>
          </div>
        </div>
        
        {/* Coming Soon Content */}
        <div className="text-center py-12 bg-gradient-to-br from-gray-50 to-blue-50 rounded-lg border-2 border-dashed border-gray-300 relative">
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-full h-full bg-gradient-to-br from-blue-100/20 to-indigo-100/20"></div>
          </div>
          
          <div className="relative z-10">
            {/* Icon */}
            <div className="bg-white rounded-full w-20 h-20 flex items-center justify-center mx-auto mb-6 shadow-lg border-4 border-blue-100">
              <Icon className="h-10 w-10 text-blue-500" />
            </div>
            
            {/* Title */}
            <h3 className="text-xl font-semibold text-gray-900 mb-3">
              {title}
            </h3>
            
            {/* Description */}
            <p className="text-gray-600 max-w-md mx-auto mb-6">
              {description}
            </p>
            
            {/* Message Badge */}
            <div className="inline-flex items-center px-4 py-2 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-600 text-white text-sm font-medium shadow-md">
              <span className="mr-2">🚀</span>
              {message}
            </div>
            
            {/* Optional additional content */}
            {children && (
              <div className="mt-6">
                {children}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}


