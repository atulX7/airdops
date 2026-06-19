'use client'

import { useState } from 'react'
import { AlertTriangle, X, ChevronDown, ChevronUp } from 'lucide-react'
import { Button } from './ui/button'

interface DataQualityViolation {
  id: string
  rule_name: string
  rule_type: string
  severity: 'error' | 'warning' | 'info'
  message: string
  details: Record<string, any>
  affected_count: number
  total_count: number
  violation_rate: number
  created_at: string
}

interface DataQualityBannerProps {
  violations: DataQualityViolation[]
  onViewDetails: () => void
  className?: string
}

export function DataQualityBanner({ violations, onViewDetails, className = '' }: DataQualityBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  
  if (!violations || violations.length === 0) {
    return null
  }
  
  const errorCount = violations.filter(v => v.severity === 'error').length
  const warningCount = violations.filter(v => v.severity === 'warning').length
  const infoCount = violations.filter(v => v.severity === 'info').length
  
  const hasErrors = errorCount > 0
  const hasWarnings = warningCount > 0
  
  // Determine banner color and icon based on severity
  const bannerColor = hasErrors 
    ? 'bg-red-50 border-red-200 text-red-800' 
    : hasWarnings 
    ? 'bg-orange-50 border-orange-200 text-orange-800'
    : 'bg-blue-50 border-blue-200 text-blue-800'
  
  const iconColor = hasErrors ? 'text-red-600' : hasWarnings ? 'text-orange-600' : 'text-blue-600'
  
  const getSeverityText = () => {
    if (hasErrors) return 'Quality checks failed'
    if (hasWarnings) return 'Quality warnings detected'
    return 'Quality info available'
  }
  
  const getSeverityDescription = () => {
    if (hasErrors) return `${errorCount} error${errorCount > 1 ? 's' : ''} found`
    if (hasWarnings) return `${warningCount} warning${warningCount > 1 ? 's' : ''} found`
    return `${infoCount} info message${infoCount > 1 ? 's' : ''}`
  }
  
  return (
    <div className={`border rounded-lg p-4 ${bannerColor} ${className}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <AlertTriangle className={`h-5 w-5 ${iconColor}`} />
          <div>
            <h3 className="font-medium">{getSeverityText()}</h3>
            <p className="text-sm opacity-90">{getSeverityDescription()}</p>
          </div>
        </div>
        
        <div className="flex items-center space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs"
          >
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            {isExpanded ? 'Hide' : 'Show'} Details
          </Button>
          
          <Button
            variant="outline"
            size="sm"
            onClick={onViewDetails}
            className="text-xs"
          >
            View All
          </Button>
        </div>
      </div>
      
      {isExpanded && (
        <div className="mt-4 space-y-2">
          {violations.slice(0, 3).map((violation) => (
            <div key={violation.id} className="bg-white bg-opacity-50 rounded p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-sm">{violation.rule_name}</span>
                <span className={`text-xs px-2 py-1 rounded ${
                  violation.severity === 'error' 
                    ? 'bg-red-100 text-red-800' 
                    : violation.severity === 'warning'
                    ? 'bg-orange-100 text-orange-800'
                    : 'bg-blue-100 text-blue-800'
                }`}>
                  {violation.severity}
                </span>
              </div>
              <p className="text-sm opacity-90">{violation.message}</p>
              {violation.affected_count > 0 && (
                <p className="text-xs opacity-75 mt-1">
                  Affects {violation.affected_count} of {violation.total_count} items 
                  ({(violation.violation_rate * 100).toFixed(1)}%)
                </p>
              )}
            </div>
          ))}
          
          {violations.length > 3 && (
            <div className="text-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={onViewDetails}
                className="text-xs"
              >
                View {violations.length - 3} more violations
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

