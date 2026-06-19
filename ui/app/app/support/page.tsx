'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function SupportPage() {
  const router = useRouter()
  
  useEffect(() => {
    // Redirect to unified help page with support tab
    router.replace('/app/help#contact')
  }, [router])
  
  // Show loading state during redirect
  return null
}
