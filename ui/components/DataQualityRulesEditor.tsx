'use client'

import { useState, useEffect } from 'react'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Textarea } from './ui/textarea'
import { Modal } from './ui/modal'
import { Save, X, Plus, Trash2, AlertCircle } from 'lucide-react'

interface DataQualityRule {
  name: string
  description: string
  severity: 'error' | 'warning' | 'info'
  enabled: boolean
  rule_type: string
  [key: string]: any
}

interface DataQualityRulesEditorProps {
  isOpen: boolean
  onClose: () => void
  onSave: (rules: any) => void
  initialRules?: any
  productId: string
}

export function DataQualityRulesEditor({ 
  isOpen, 
  onClose, 
  onSave, 
  initialRules, 
  productId 
}: DataQualityRulesEditorProps) {
  const [rules, setRules] = useState<any>(() => {
    if (initialRules) {
      return initialRules
    }
    return {
      product_id: productId,
      version: 1,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      required_fields_rules: [],
      max_duplicate_rate_rules: [],
      min_chunk_coverage_rules: [],
      bad_extensions_rules: [],
      min_freshness_rules: [],
      file_size_rules: [],
      content_length_rules: []
    }
  })
  
  const [activeTab, setActiveTab] = useState('required_fields')
  const [errors, setErrors] = useState<Record<string, string>>({})
  
  useEffect(() => {
    if (initialRules) {
      setRules(initialRules)
    }
  }, [initialRules])
  
  const addRule = (ruleType: string) => {
    const newRule: DataQualityRule = {
      name: '',
      description: '',
      severity: 'error',
      enabled: true,
      rule_type: ruleType
    }
    
    // Add type-specific fields
    switch (ruleType) {
      case 'required_fields':
        newRule.required_fields = []
        break
      case 'max_duplicate_rate':
        newRule.max_duplicate_rate = 0.1
        break
      case 'min_chunk_coverage':
        newRule.min_chunk_coverage = 0.8
        break
      case 'bad_extensions':
        newRule.bad_extensions = []
        break
      case 'min_freshness':
        newRule.min_freshness_days = 30
        break
      case 'file_size':
        newRule.max_file_size_mb = 10
        newRule.min_file_size_kb = 1
        break
      case 'content_length':
        newRule.min_content_length = 100
        newRule.max_content_length = 10000
        break
    }
    
    setRules((prev: any) => {
      const rulesData = prev.rules || prev
      return {
        ...prev,
        rules: {
          ...rulesData,
          [`${ruleType}_rules`]: [...(rulesData[`${ruleType}_rules`] || []), newRule]
        }
      }
    })
  }
  
  const updateRule = (ruleType: string, index: number, field: string, value: any) => {
    setRules((prev: any) => {
      const rulesData = prev.rules || prev
      return {
        ...prev,
        rules: {
          ...rulesData,
          [`${ruleType}_rules`]: rulesData[`${ruleType}_rules`].map((rule: any, i: number) => 
            i === index ? { ...rule, [field]: value } : rule
          )
        }
      }
    })
  }
  
  const removeRule = (ruleType: string, index: number) => {
    setRules((prev: any) => {
      const rulesData = prev.rules || prev
      return {
        ...prev,
        rules: {
          ...rulesData,
          [`${ruleType}_rules`]: rulesData[`${ruleType}_rules`].filter((_: any, i: number) => i !== index)
        }
      }
    })
  }
  
  const validateRules = () => {
    const newErrors: Record<string, string> = {}
    const rulesData = rules.rules || rules
    
    // Validate each rule type
    Object.keys(rulesData).forEach(key => {
      if (key.endsWith('_rules')) {
        const ruleList = rulesData[key]
        if (Array.isArray(ruleList)) {
          ruleList.forEach((rule: any, index: number) => {
          if (!rule.name?.trim()) {
            newErrors[`${key}_${index}_name`] = 'Rule name is required'
          }
          if (!rule.description?.trim()) {
            newErrors[`${key}_${index}_description`] = 'Rule description is required'
          }
          
          // Type-specific validation
          if (rule.rule_type === 'required_fields' && (!rule.required_fields || rule.required_fields.length === 0)) {
            newErrors[`${key}_${index}_required_fields`] = 'At least one required field must be specified'
          }
          if (rule.rule_type === 'max_duplicate_rate' && (rule.max_duplicate_rate < 0 || rule.max_duplicate_rate > 1)) {
            newErrors[`${key}_${index}_max_duplicate_rate`] = 'Duplicate rate must be between 0 and 1'
          }
          if (rule.rule_type === 'min_chunk_coverage' && (rule.min_chunk_coverage < 0 || rule.min_chunk_coverage > 1)) {
            newErrors[`${key}_${index}_min_chunk_coverage`] = 'Chunk coverage must be between 0 and 1'
          }
          if (rule.rule_type === 'bad_extensions' && (!rule.bad_extensions || rule.bad_extensions.length === 0)) {
            newErrors[`${key}_${index}_bad_extensions`] = 'At least one bad extension must be specified'
          }
          if (rule.rule_type === 'min_freshness' && rule.min_freshness_days < 1) {
            newErrors[`${key}_${index}_min_freshness_days`] = 'Minimum freshness must be at least 1 day'
          }
          if (rule.rule_type === 'file_size' && rule.max_file_size_mb <= 0) {
            newErrors[`${key}_${index}_max_file_size_mb`] = 'Maximum file size must be greater than 0'
          }
          })
        }
      }
    })
    
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }
  
  const handleSave = () => {
    if (validateRules()) {
      const rulesData = rules.rules || rules
      
      // Helper function to transform rule severity
      const transformRule = (rule: any) => ({
        ...rule,
        severity: rule.severity?.replace('RuleSeverity.', '').toLowerCase() || 'error'
      })
      
      // Transform rules to match backend schema
      const transformedRules = {
        product_id: productId,
        version: rules.version || 1,
        created_at: rules.created_at || new Date().toISOString(),
        updated_at: new Date().toISOString(),
        required_fields_rules: (rulesData.required_fields_rules || []).map(transformRule),
        max_duplicate_rate_rules: (rulesData.max_duplicate_rate_rules || []).map(transformRule),
        min_chunk_coverage_rules: (rulesData.min_chunk_coverage_rules || []).map(transformRule),
        bad_extensions_rules: (rulesData.bad_extensions_rules || []).map(transformRule),
        min_freshness_rules: (rulesData.min_freshness_rules || []).map(transformRule),
        file_size_rules: (rulesData.file_size_rules || []).map(transformRule),
        content_length_rules: (rulesData.content_length_rules || []).map(transformRule)
      }
      
      onSave(transformedRules)
      onClose()
    }
  }
  
  const renderRuleEditor = (ruleType: string, rule: any, index: number) => {
    const baseKey = `${ruleType}_rules_${index}`
    
    return (
      <div key={index} className="border rounded-lg p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="font-medium">Rule {index + 1}</h4>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => removeRule(ruleType, index)}
            className="text-red-600 hover:text-red-700"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor={`${baseKey}_name`}>Rule Name</Label>
            <Input
              id={`${baseKey}_name`}
              value={rule.name}
              onChange={(e) => updateRule(ruleType, index, 'name', e.target.value)}
              className={errors[`${baseKey}_name`] ? 'border-red-500' : ''}
            />
            {errors[`${baseKey}_name`] && (
              <p className="text-red-500 text-sm mt-1">{errors[`${baseKey}_name`]}</p>
            )}
          </div>
          
          <div>
            <Label htmlFor={`${baseKey}_severity`}>Severity</Label>
            <select
              id={`${baseKey}_severity`}
              value={rule.severity}
              onChange={(e) => updateRule(ruleType, index, 'severity', e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
            >
              <option value="error">Error</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
          </div>
        </div>
        
        <div>
          <Label htmlFor={`${baseKey}_description`}>Description</Label>
          <Textarea
            id={`${baseKey}_description`}
            value={rule.description}
            onChange={(e) => updateRule(ruleType, index, 'description', e.target.value)}
            className={errors[`${baseKey}_description`] ? 'border-red-500' : ''}
            rows={2}
          />
          {errors[`${baseKey}_description`] && (
            <p className="text-red-500 text-sm mt-1">{errors[`${baseKey}_description`]}</p>
          )}
        </div>
        
        <div className="flex items-center">
          <input
            type="checkbox"
            id={`${baseKey}_enabled`}
            checked={rule.enabled}
            onChange={(e) => updateRule(ruleType, index, 'enabled', e.target.checked)}
            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
          />
          <Label htmlFor={`${baseKey}_enabled`} className="ml-2">Enabled</Label>
        </div>
        
        {/* Type-specific fields */}
        {ruleType === 'required_fields' && (
          <div>
            <Label>Required Fields</Label>
            <div className="space-y-2">
              {rule.required_fields?.map((field: string, fieldIndex: number) => (
                <div key={fieldIndex} className="flex items-center space-x-2">
                  <Input
                    value={field}
                    onChange={(e) => {
                      const newFields = [...rule.required_fields]
                      newFields[fieldIndex] = e.target.value
                      updateRule(ruleType, index, 'required_fields', newFields)
                    }}
                    placeholder="Field name"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const newFields = rule.required_fields.filter((_: any, i: number) => i !== fieldIndex)
                      updateRule(ruleType, index, 'required_fields', newFields)
                    }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const newFields = [...(rule.required_fields || []), '']
                  updateRule(ruleType, index, 'required_fields', newFields)
                }}
              >
                <Plus className="h-4 w-4 mr-1" />
                Add Field
              </Button>
            </div>
          </div>
        )}
        
        {ruleType === 'max_duplicate_rate' && (
          <div>
            <Label htmlFor={`${baseKey}_max_duplicate_rate`}>Maximum Duplicate Rate (0-1)</Label>
            <Input
              id={`${baseKey}_max_duplicate_rate`}
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={rule.max_duplicate_rate}
              onChange={(e) => updateRule(ruleType, index, 'max_duplicate_rate', parseFloat(e.target.value))}
              className={errors[`${baseKey}_max_duplicate_rate`] ? 'border-red-500' : ''}
            />
            {errors[`${baseKey}_max_duplicate_rate`] && (
              <p className="text-red-500 text-sm mt-1">{errors[`${baseKey}_max_duplicate_rate`]}</p>
            )}
          </div>
        )}
        
        {ruleType === 'bad_extensions' && (
          <div>
            <Label>Bad Extensions</Label>
            <div className="space-y-2">
              {rule.bad_extensions?.map((ext: string, extIndex: number) => (
                <div key={extIndex} className="flex items-center space-x-2">
                  <Input
                    value={ext}
                    onChange={(e) => {
                      const newExts = [...rule.bad_extensions]
                      newExts[extIndex] = e.target.value
                      updateRule(ruleType, index, 'bad_extensions', newExts)
                    }}
                    placeholder=".tmp"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const newExts = rule.bad_extensions.filter((_: any, i: number) => i !== extIndex)
                      updateRule(ruleType, index, 'bad_extensions', newExts)
                    }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const newExts = [...(rule.bad_extensions || []), '']
                  updateRule(ruleType, index, 'bad_extensions', newExts)
                }}
              >
                <Plus className="h-4 w-4 mr-1" />
                Add Extension
              </Button>
            </div>
          </div>
        )}
        
        {ruleType === 'min_freshness' && (
          <div>
            <Label htmlFor={`${baseKey}_min_freshness_days`}>Minimum Freshness (days)</Label>
            <Input
              id={`${baseKey}_min_freshness_days`}
              type="number"
              min="1"
              value={rule.min_freshness_days}
              onChange={(e) => updateRule(ruleType, index, 'min_freshness_days', parseInt(e.target.value))}
              className={errors[`${baseKey}_min_freshness_days`] ? 'border-red-500' : ''}
            />
            {errors[`${baseKey}_min_freshness_days`] && (
              <p className="text-red-500 text-sm mt-1">{errors[`${baseKey}_min_freshness_days`]}</p>
            )}
          </div>
        )}
      </div>
    )
  }
  
  const tabs = [
    { id: 'required_fields', label: 'Required Fields', description: 'Check for required fields in documents' },
    { id: 'max_duplicate_rate', label: 'Duplicate Rate', description: 'Limit maximum duplicate content' },
    { id: 'min_chunk_coverage', label: 'Chunk Coverage', description: 'Ensure minimum chunk coverage' },
    { id: 'bad_extensions', label: 'Bad Extensions', description: 'Reject files with bad extensions' },
    { id: 'min_freshness', label: 'Freshness', description: 'Ensure data is not too old' },
    { id: 'file_size', label: 'File Size', description: 'Check file size limits' },
    { id: 'content_length', label: 'Content Length', description: 'Check content length limits' }
  ]
  
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Data Quality Rules Editor" size="xl">
      <div className="flex flex-col h-[600px]">
        {/* Tabs */}
        <div className="border-b border-gray-200 flex-shrink-0">
          <nav className="-mb-px flex space-x-8">
            {tabs.map((tab) => {
              const ruleKey = `${tab.id}_rules`
              const rulesData = rules.rules || rules
              const hasRules = rulesData[ruleKey] && rulesData[ruleKey].length > 0
              const ruleCount = hasRules ? rulesData[ruleKey].length : 0
              
              
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`py-2 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  {tab.label}
                  {hasRules && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {ruleCount}
                    </span>
                  )}
                </button>
              )
            })}
          </nav>
        </div>
        
        {/* Tab Content - Scrollable */}
        <div className="flex-1 overflow-y-auto">
          {/* Rules Summary */}
          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <h4 className="text-sm font-medium text-gray-900 mb-2">Existing Rules Summary</h4>
            <div className="flex flex-wrap gap-2">
              {tabs.map((tab) => {
                const ruleKey = `${tab.id}_rules`
                const rulesData = rules.rules || rules
                const ruleCount = rulesData[ruleKey] ? rulesData[ruleKey].length : 0
                
                
                if (ruleCount === 0) return null
                
                return (
                  <span
                    key={tab.id}
                    className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-blue-100 text-blue-800 cursor-pointer hover:bg-blue-200"
                    onClick={() => setActiveTab(tab.id)}
                  >
                    {tab.label}: {ruleCount} rule{ruleCount !== 1 ? 's' : ''}
                  </span>
                )
              })}
              {tabs.every(tab => !rules[`${tab.id}_rules`] || rules[`${tab.id}_rules`].length === 0) && (
                <span className="text-sm text-gray-500">No existing rules</span>
              )}
            </div>
          </div>
          
          <div className="mb-4">
            <h3 className="text-lg font-medium text-gray-900">{tabs.find(t => t.id === activeTab)?.label}</h3>
            <p className="text-sm text-gray-600">{tabs.find(t => t.id === activeTab)?.description}</p>
          </div>
          
          <div className="space-y-4">
            {(rules.rules || rules)[`${activeTab}_rules`]?.map((rule: any, index: number) => 
              renderRuleEditor(activeTab, rule, index)
            )}
            
            <Button
              variant="outline"
              onClick={() => addRule(activeTab)}
              className="w-full"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add {tabs.find(t => t.id === activeTab)?.label} Rule
            </Button>
          </div>
        </div>
        
        {/* Actions - Fixed at bottom */}
        <div className="flex justify-end space-x-3 pt-4 border-t flex-shrink-0">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} className="flex items-center">
            <Save className="h-4 w-4 mr-2" />
            Save Rules
          </Button>
        </div>
      </div>
    </Modal>
  )
}

