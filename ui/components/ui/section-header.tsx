'use client'

import { ReactNode } from 'react'
import { Info, LucideIcon } from 'lucide-react'

interface SectionHeaderProps {
  /** Main heading text */
  title: string
  /** Icon to display before the title */
  icon?: LucideIcon
  /** Icon color class (default: text-blue-600) */
  iconColor?: string
  /** Subtitle text or metadata to display below the title */
  subtitle?: string | ReactNode
  /** Tooltip content (shows info icon if provided) */
  tooltip?: string | ReactNode
  /** Additional actions/buttons to show on the right */
  actions?: ReactNode
  /** Custom className for the container */
  className?: string
  /** Status indicator (e.g., "Current Production", "Active") */
  status?: {
    label: string
    color?: 'green' | 'yellow' | 'red' | 'blue' | 'gray'
    dot?: boolean
  }
}

const statusColors = {
  green: 'bg-green-500',
  yellow: 'bg-yellow-500',
  red: 'bg-red-500',
  blue: 'bg-blue-500',
  gray: 'bg-gray-500',
}

export function SectionHeader({
  title,
  icon: Icon,
  iconColor = 'text-blue-600',
  subtitle,
  tooltip,
  actions,
  className = '',
  status,
}: SectionHeaderProps) {
  return (
    <div className={`flex items-center justify-between mb-3 ${className}`}>
      <div className="flex-1 min-w-0">
        {/* Main heading with icon */}
        <div className="flex items-center gap-2 mb-1">
          <h3 className="text-md font-medium text-gray-900 flex items-center gap-2">
            {Icon && <Icon className={`h-4 w-4 ${iconColor}`} />}
            <span>{title}</span>
          </h3>
          {/* Tooltip icon */}
          {tooltip && (
            <div className="relative group">
              <Info className="h-3.5 w-3.5 text-gray-400 hover:text-gray-600 cursor-help transition-colors" />
              <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block z-10 w-72 p-3 text-xs text-gray-700 bg-white border border-gray-200 rounded-lg shadow-lg pointer-events-none">
                {typeof tooltip === 'string' ? (
                  <p>{tooltip}</p>
                ) : (
                  tooltip
                )}
                {/* Arrow pointing down */}
                <div className="absolute top-full left-4 -mt-1">
                  <div className="w-2 h-2 bg-white border-r border-b border-gray-200 transform rotate-45"></div>
                </div>
              </div>
            </div>
          )}
        </div>
        {/* Subtitle with optional status */}
        {(subtitle || status) && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            {subtitle && (
              <>
                {typeof subtitle === 'string' ? (
                  <span className="font-medium text-gray-700">{subtitle}</span>
                ) : (
                  subtitle
                )}
              </>
            )}
            {status && (
              <span className="inline-flex items-center gap-1">
                {status.dot !== false && (
                  <span className={`h-1.5 w-1.5 rounded-full ${statusColors[status.color || 'green']}`}></span>
                )}
                {status.label}
              </span>
            )}
          </div>
        )}
      </div>
      {/* Actions on the right */}
      {actions && (
        <div className="flex items-center gap-2 ml-4">
          {actions}
        </div>
      )}
    </div>
  )
}

