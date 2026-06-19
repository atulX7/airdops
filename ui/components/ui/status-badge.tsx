import * as React from "react"
import { cn } from "@/lib/utils"
import { CheckCircle2, Clock, Activity, AlertCircle, AlertTriangle } from "lucide-react"

export type StatusType = 'draft' | 'running' | 'ready' | 'failed' | 'failed_policy' | 'ready_with_warnings' | 'queued' | 'succeeded'

interface StatusBadgeProps {
  status: StatusType
  className?: string
  showIcon?: boolean
  size?: 'sm' | 'md' | 'lg'
}

const statusConfig: Record<StatusType, {
  label: string
  icon: React.ComponentType<{ className?: string }>
  gradient: string
  textColor: string
  bgColor: string
  borderColor: string
  pulse?: boolean
}> = {
  draft: {
    label: 'Draft',
    icon: Clock,
    gradient: 'from-gray-500 to-gray-600',
    textColor: 'text-gray-700',
    bgColor: 'bg-gray-100',
    borderColor: 'border-gray-300',
  },
  running: {
    label: 'Running',
    icon: Activity,
    gradient: 'from-blue-500 to-indigo-600',
    textColor: 'text-blue-700',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-300',
    pulse: true,
  },
  ready: {
    label: 'Ready',
    icon: CheckCircle2,
    gradient: 'from-green-500 to-emerald-600',
    textColor: 'text-green-700',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-300',
  },
  failed: {
    label: 'Failed',
    icon: AlertCircle,
    gradient: 'from-red-500 to-rose-600',
    textColor: 'text-red-700',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-300',
  },
  failed_policy: {
    label: 'Policy Failed',
    icon: AlertTriangle,
    gradient: 'from-red-500 to-rose-600',
    textColor: 'text-red-700',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-300',
  },
  ready_with_warnings: {
    label: 'Ready (Warnings)',
    icon: AlertTriangle,
    gradient: 'from-yellow-500 to-amber-600',
    textColor: 'text-yellow-700',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-300',
  },
  queued: {
    label: 'Queued',
    icon: Clock,
    gradient: 'from-gray-500 to-slate-600',
    textColor: 'text-gray-700',
    bgColor: 'bg-gray-100',
    borderColor: 'border-gray-300',
  },
  succeeded: {
    label: 'Succeeded',
    icon: CheckCircle2,
    gradient: 'from-green-500 to-emerald-600',
    textColor: 'text-green-700',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-300',
  },
}

const sizeClasses = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-xs',
  lg: 'px-4 py-1.5 text-sm',
}

export function StatusBadge({ status, className, showIcon = true, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status]
  if (!config) {
    // Fallback for unknown status
    return (
      <span className={cn(
        'inline-flex items-center rounded-full font-medium',
        'bg-gray-100 text-gray-800 border border-gray-300',
        sizeClasses[size],
        className
      )}>
        {status}
      </span>
    )
  }

  const Icon = config.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-semibold',
        'border shadow-sm transition-all',
        config.bgColor,
        config.textColor,
        config.borderColor,
        sizeClasses[size],
        config.pulse && 'animate-pulse',
        className
      )}
      title={config.label}
    >
      {showIcon && <Icon className="h-3.5 w-3.5" />}
      <span>{config.label}</span>
    </span>
  )
}

// Enhanced gradient badge variant for special use cases
export function StatusBadgeGradient({ status, className, showIcon = true, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status]
  if (!config) {
    return <StatusBadge status={status} className={className} showIcon={showIcon} size={size} />
  }

  const Icon = config.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-semibold',
        'bg-gradient-to-r text-white shadow-md',
        `bg-gradient-to-r ${config.gradient}`,
        sizeClasses[size],
        config.pulse && 'animate-pulse',
        className
      )}
      title={config.label}
    >
      {showIcon && <Icon className="h-3.5 w-3.5" />}
      <span>{config.label}</span>
    </span>
  )
}

