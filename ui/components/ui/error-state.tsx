import * as React from "react"
import { AlertCircle, RefreshCw, Home, ArrowLeft, AlertTriangle, XCircle } from "lucide-react"
import { Button } from "./button"
import { cn } from "@/lib/utils"

interface ErrorStateProps {
  title?: string
  message?: string
  error?: string | Error | null
  onRetry?: () => void
  onGoHome?: () => void
  onGoBack?: () => void
  variant?: 'error' | 'warning' | 'info' | 'empty'
  className?: string
}

const variantConfig = {
  error: {
    icon: XCircle,
    iconColor: 'text-red-500',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
    titleColor: 'text-red-900',
    messageColor: 'text-red-700',
    defaultTitle: 'Something went wrong',
    defaultMessage: 'An error occurred while processing your request. Please try again.',
  },
  warning: {
    icon: AlertTriangle,
    iconColor: 'text-yellow-500',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-200',
    titleColor: 'text-yellow-900',
    messageColor: 'text-yellow-700',
    defaultTitle: 'Warning',
    defaultMessage: 'Please review the information and try again.',
  },
  info: {
    icon: AlertCircle,
    iconColor: 'text-blue-500',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
    titleColor: 'text-blue-900',
    messageColor: 'text-blue-700',
    defaultTitle: 'Information',
    defaultMessage: 'No information available at this time.',
  },
  empty: {
    icon: AlertCircle,
    iconColor: 'text-gray-400',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
    titleColor: 'text-gray-900',
    messageColor: 'text-gray-600',
    defaultTitle: 'No data available',
    defaultMessage: 'There is no data to display at this time.',
  },
}

export function ErrorState({
  title,
  message,
  error,
  onRetry,
  onGoHome,
  onGoBack,
  variant = 'error',
  className,
}: ErrorStateProps) {
  const config = variantConfig[variant]
  const Icon = config.icon

  const displayTitle = title || config.defaultTitle
  const displayMessage = message || 
    (error instanceof Error ? error.message : typeof error === 'string' ? error : null) || 
    config.defaultMessage

  return (
    <div className={cn(
      "flex flex-col items-center justify-center py-12 px-4",
      className
    )}>
      <div className={cn(
        "rounded-2xl border-2 p-8 max-w-md w-full text-center",
        config.bgColor,
        config.borderColor
      )}>
        <div className="flex justify-center mb-4">
          <div className={cn(
            "rounded-full p-4",
            config.bgColor
          )}>
            <Icon className={cn("h-12 w-12", config.iconColor)} />
          </div>
        </div>
        
        <h3 className={cn(
          "text-xl font-semibold mb-2",
          config.titleColor
        )}>
          {displayTitle}
        </h3>
        
        <p className={cn(
          "text-sm mb-6",
          config.messageColor
        )}>
          {displayMessage}
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          {onRetry && (
            <Button
              onClick={onRetry}
              className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md hover:shadow-lg"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Try Again
            </Button>
          )}
          {onGoBack && (
            <Button
              variant="outline"
              onClick={onGoBack}
              className="border-2 hover:border-gray-300 hover:bg-gray-50"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Go Back
            </Button>
          )}
          {onGoHome && (
            <Button
              variant="outline"
              onClick={onGoHome}
              className="border-2 hover:border-gray-300 hover:bg-gray-50"
            >
              <Home className="h-4 w-4 mr-2" />
              Go Home
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

