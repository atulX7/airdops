'use client'

import { ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from './button'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

export function Modal({ isOpen, onClose, title, children, size = 'md' }: ModalProps) {
  if (!isOpen) return null

  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl'
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        {/* Enhanced Backdrop with animation */}
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 transition-opacity duration-300"
          onClick={onClose}
        />
        
        {/* Enhanced Modal with animation */}
        <div className={`relative w-full ${sizeClasses[size]} bg-white rounded-xl shadow-2xl transform transition-all duration-300 scale-100`}>
          {/* Enhanced Header */}
          <div className="flex items-center justify-between p-6 border-b-2 border-gray-100 bg-gradient-to-r from-gray-50 to-blue-50/30">
            <h3 className="text-xl font-semibold text-gray-900">{title}</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg p-1.5 transition-all"
              aria-label="Close modal"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          
          {/* Enhanced Content */}
          <div className="p-6">
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}

interface ConfirmModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'warning' | 'info'
}

export function ConfirmModal({ 
  isOpen, 
  onClose, 
  onConfirm, 
  title, 
  message, 
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'info'
}: ConfirmModalProps) {
  const variantClasses = {
    danger: 'bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-700 hover:to-rose-700 shadow-md hover:shadow-lg',
    warning: 'bg-gradient-to-r from-yellow-600 to-amber-600 hover:from-yellow-700 hover:to-amber-700 shadow-md hover:shadow-lg',
    info: 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg'
  }

  const iconConfig = {
    danger: '⚠️',
    warning: '⚠️',
    info: 'ℹ️'
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <div className="space-y-6">
        <div className="flex items-start space-x-4">
          <div className="flex-shrink-0 text-3xl">{iconConfig[variant]}</div>
          <div className="text-gray-700 leading-relaxed whitespace-pre-line">{message}</div>
        </div>
        <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200">
          <Button 
            variant="outline" 
            onClick={onClose}
            className="border-2 hover:border-gray-300 hover:bg-gray-50"
          >
            {cancelText}
          </Button>
          <Button 
            onClick={onConfirm}
            className={variantClasses[variant]}
          >
            {confirmText}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

interface ResultModalProps {
  isOpen: boolean
  onClose: () => void
  title: string
  message: string
  type: 'success' | 'error' | 'warning' | 'info'
  actionButton?: {
    label: string
    onClick: () => void
    variant?: 'primary' | 'secondary'
  }
}

export function ResultModal({ isOpen, onClose, title, message, type, actionButton }: ResultModalProps) {
  const typeConfig = {
    success: {
      icon: (
        <div className="flex-shrink-0 h-8 w-8 text-green-400">
          <svg fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        </div>
      ),
      bgColor: 'bg-green-50',
      borderColor: 'border-green-200',
      textColor: 'text-green-800'
    },
    error: {
      icon: (
        <div className="flex-shrink-0 h-8 w-8 text-red-400">
          <svg fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
        </div>
      ),
      bgColor: 'bg-red-50',
      borderColor: 'border-red-200',
      textColor: 'text-red-800'
    },
    warning: {
      icon: (
        <div className="flex-shrink-0 h-8 w-8 text-yellow-400">
          <svg fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        </div>
      ),
      bgColor: 'bg-yellow-50',
      borderColor: 'border-yellow-200',
      textColor: 'text-yellow-800'
    },
    info: {
      icon: (
        <div className="flex-shrink-0 h-8 w-8 text-blue-400">
          <svg fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
        </div>
      ),
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-200',
      textColor: 'text-blue-800'
    }
  }

  const config = typeConfig[type]

  const iconConfig = {
    success: { icon: '✅', bg: 'bg-green-100' },
    error: { icon: '❌', bg: 'bg-red-100' },
    warning: { icon: '⚠️', bg: 'bg-yellow-100' },
    info: { icon: 'ℹ️', bg: 'bg-blue-100' }
  }

  const icon = iconConfig[type]

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <div className="space-y-6">
        <div className={`border-2 rounded-xl p-6 ${config.bgColor} ${config.borderColor}`}>
          <div className="flex items-start space-x-4">
            <div className={`${icon.bg} rounded-full p-3 flex-shrink-0`}>
              <span className="text-2xl">{icon.icon}</span>
            </div>
            <div className="flex-1">
              <p className={`text-lg font-semibold ${config.textColor} mb-2`}>
                {title}
              </p>
              <p className={`text-sm ${config.textColor.replace('800', '700')} leading-relaxed`}>
                {message}
              </p>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-3">
          {actionButton && (
            <Button 
              onClick={actionButton.onClick}
              className={
                actionButton.variant === 'secondary'
                  ? "bg-gray-600 hover:bg-gray-700 text-white shadow-md hover:shadow-lg"
                  : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"
              }
            >
              {actionButton.label}
            </Button>
          )}
          <Button 
            onClick={onClose}
            className={actionButton ? "border-2 border-gray-300 hover:border-gray-400 hover:bg-gray-50" : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"}
          >
            {actionButton ? 'Cancel' : 'OK'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
