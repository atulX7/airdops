'use client'

import { useState, useEffect } from 'react'
import { X, AlertTriangle, AlertCircle, Info, Filter, Download } from 'lucide-react'
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

interface DataQualityViolationsDrawerProps {
  isOpen: boolean
  onClose: () => void
  violations: DataQualityViolation[]
  productId: string
  version?: number
}

export function DataQualityViolationsDrawer({ 
  isOpen, 
  onClose, 
  violations, 
  productId, 
  version 
}: DataQualityViolationsDrawerProps) {
  const [filteredViolations, setFilteredViolations] = useState<DataQualityViolation[]>(violations)
  const [severityFilter, setSeverityFilter] = useState<'all' | 'error' | 'warning' | 'info'>('all')
  const [searchTerm, setSearchTerm] = useState('')
  
  useEffect(() => {
    let filtered = violations
    
    // Filter by severity
    if (severityFilter !== 'all') {
      filtered = filtered.filter(v => v.severity === severityFilter)
    }
    
    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(v => 
        v.rule_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        v.message.toLowerCase().includes(searchTerm.toLowerCase())
      )
    }
    
    setFilteredViolations(filtered)
  }, [violations, severityFilter, searchTerm])
  
  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'error':
        return <AlertTriangle className="h-5 w-5 text-red-600" />
      case 'warning':
        return <AlertCircle className="h-5 w-5 text-orange-600" />
      case 'info':
        return <Info className="h-5 w-5 text-blue-600" />
      default:
        return <AlertTriangle className="h-5 w-5 text-gray-600" />
    }
  }
  
  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'error':
        return 'border-red-200 bg-red-50'
      case 'warning':
        return 'border-orange-200 bg-orange-50'
      case 'info':
        return 'border-blue-200 bg-blue-50'
      default:
        return 'border-gray-200 bg-gray-50'
    }
  }
  
  const getSeverityBadgeColor = (severity: string) => {
    switch (severity) {
      case 'error':
        return 'bg-red-100 text-red-800'
      case 'warning':
        return 'bg-orange-100 text-orange-800'
      case 'info':
        return 'bg-blue-100 text-blue-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }
  
  const exportViolations = () => {
    const csvContent = [
      ['Rule Name', 'Type', 'Severity', 'Message', 'Affected Count', 'Total Count', 'Violation Rate', 'Created At'],
      ...filteredViolations.map(v => [
        v.rule_name,
        v.rule_type,
        v.severity,
        v.message,
        v.affected_count,
        v.total_count,
        (v.violation_rate * 100).toFixed(2) + '%',
        new Date(v.created_at).toLocaleString()
      ])
    ].map(row => row.map(cell => `"${cell}"`).join(',')).join('\n')
    
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `data-quality-violations-${productId}-v${version || 'latest'}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  }
  
  if (!isOpen) return null
  
  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      <div className="absolute inset-0 bg-black bg-opacity-50" onClick={onClose} />
      
      <div className="absolute right-0 top-0 h-full w-full max-w-2xl bg-white shadow-xl">
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Data Quality Violations</h2>
              <p className="text-sm text-gray-600">
                {violations.length} violation{violations.length !== 1 ? 's' : ''} found
                {version && ` for version ${version}`}
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-5 w-5" />
            </Button>
          </div>
          
          {/* Filters */}
          <div className="border-b border-gray-200 px-6 py-4">
            <div className="flex items-center space-x-4">
              <div className="flex-1">
                <input
                  type="text"
                  placeholder="Search violations..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                />
              </div>
              
              <div className="flex items-center space-x-2">
                <Filter className="h-4 w-4 text-gray-500" />
                <select
                  value={severityFilter}
                  onChange={(e) => setSeverityFilter(e.target.value as any)}
                  className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                >
                  <option value="all">All Severities</option>
                  <option value="error">Errors</option>
                  <option value="warning">Warnings</option>
                  <option value="info">Info</option>
                </select>
              </div>
              
              <Button variant="outline" size="sm" onClick={exportViolations}>
                <Download className="h-4 w-4 mr-2" />
                Export
              </Button>
            </div>
          </div>
          
          {/* Violations List */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {filteredViolations.length === 0 ? (
              <div className="text-center py-12">
                <AlertTriangle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No violations found</h3>
                <p className="text-gray-600">
                  {searchTerm || severityFilter !== 'all' 
                    ? 'Try adjusting your filters to see more violations.'
                    : 'Great! No data quality violations were detected.'
                  }
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {filteredViolations.map((violation) => (
                  <div
                    key={violation.id}
                    className={`border rounded-lg p-4 ${getSeverityColor(violation.severity)}`}
                  >
                    <div className="flex items-start space-x-3">
                      {getSeverityIcon(violation.severity)}
                      
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-2">
                          <h3 className="text-sm font-medium text-gray-900 truncate">
                            {violation.rule_name}
                          </h3>
                          <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getSeverityBadgeColor(violation.severity)}`}>
                            {violation.severity}
                          </span>
                        </div>
                        
                        <p className="text-sm text-gray-700 mb-3">{violation.message}</p>
                        
                        <div className="grid grid-cols-2 gap-4 text-xs text-gray-600">
                          <div>
                            <span className="font-medium">Affected:</span> {violation.affected_count} of {violation.total_count}
                          </div>
                          <div>
                            <span className="font-medium">Rate:</span> {(violation.violation_rate * 100).toFixed(1)}%
                          </div>
                          <div>
                            <span className="font-medium">Type:</span> {violation.rule_type}
                          </div>
                          <div>
                            <span className="font-medium">Created:</span> {new Date(violation.created_at).toLocaleString()}
                          </div>
                        </div>
                        
                        {Object.keys(violation.details).length > 0 && (
                          <details className="mt-3">
                            <summary className="text-xs font-medium text-gray-600 cursor-pointer hover:text-gray-800">
                              View Details
                            </summary>
                            <div className="mt-2 p-3 bg-white bg-opacity-50 rounded border">
                              <pre className="text-xs text-gray-700 whitespace-pre-wrap">
                                {JSON.stringify(violation.details, null, 2)}
                              </pre>
                            </div>
                          </details>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          
          {/* Footer */}
          <div className="border-t border-gray-200 px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-600">
                Showing {filteredViolations.length} of {violations.length} violations
              </div>
              <Button variant="outline" onClick={onClose}>
                Close
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

