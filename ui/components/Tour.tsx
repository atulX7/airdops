'use client'

import { useState, useEffect } from 'react'
import Joyride, { CallBackProps, STATUS, Step, Styles } from 'react-joyride'

interface TourProps {
  steps: Step[]
  run?: boolean
  onComplete?: () => void
}

const TOUR_STORAGE_KEY = 'primedata_tour_completed'

// Custom styles to match AIRDOps design
const joyrideStyles: Partial<Styles> = {
  options: {
    primaryColor: '#4f46e5', // indigo-600
    zIndex: 10000,
  },
  tooltip: {
    borderRadius: '12px',
    padding: '20px',
    fontSize: '14px',
  },
  tooltipContainer: {
    textAlign: 'left',
  },
  tooltipTitle: {
    fontSize: '18px',
    fontWeight: '600',
    marginBottom: '8px',
    color: '#111827',
  },
  tooltipContent: {
    padding: '8px 0',
    fontSize: '14px',
    lineHeight: '1.5',
    color: '#4b5563',
  },
  buttonNext: {
    backgroundColor: '#4f46e5',
    borderRadius: '8px',
    padding: '10px 20px',
    fontSize: '14px',
    fontWeight: '600',
    outline: 'none',
  },
  buttonBack: {
    color: '#6b7280',
    marginRight: '10px',
    fontSize: '14px',
    fontWeight: '500',
  },
  buttonSkip: {
    color: '#6b7280',
    fontSize: '14px',
    fontWeight: '500',
  },
  spotlight: {
    borderRadius: '12px',
  },
  overlay: {
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
}

export function Tour({ steps, run = false, onComplete }: TourProps) {
  const [isRunning, setIsRunning] = useState(run)

  useEffect(() => {
    setIsRunning(run)
  }, [run])

  const handleJoyrideCallback = (data: CallBackProps) => {
    const { status } = data

    if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
      setIsRunning(false)
      // Mark tour as completed
      if (typeof window !== 'undefined') {
        localStorage.setItem(TOUR_STORAGE_KEY, 'true')
      }
      onComplete?.()
    }
  }

  return (
    <Joyride
      steps={steps}
      run={isRunning}
      continuous
      showProgress
      showSkipButton
      callback={handleJoyrideCallback}
      styles={joyrideStyles}
      locale={{
        back: 'Back',
        close: 'Close',
        last: 'Finish',
        next: 'Next',
        skip: 'Skip Tour',
      }}
    />
  )
}

export function hasCompletedTour(): boolean {
  if (typeof window === 'undefined') return false
  return localStorage.getItem(TOUR_STORAGE_KEY) === 'true'
}

export function resetTour() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(TOUR_STORAGE_KEY)
  }
}

