'use client'

import { useState, FormEvent } from 'react'
import Link from 'next/link'
import { Footer } from '@/components/Footer'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { apiClient } from '@/lib/api-client'
import { Mail, Send, CheckCircle2, AlertCircle, ArrowLeft } from 'lucide-react'

export default function ContactPage() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    feedback: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitStatus, setSubmitStatus] = useState<{
    type: 'success' | 'error' | null
    message: string
  }>({ type: null, message: '' })

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {}

    if (!formData.name.trim()) {
      newErrors.name = 'Name is required'
    }

    if (!formData.email.trim()) {
      newErrors.email = 'Email is required'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address'
    }

    if (!formData.feedback.trim()) {
      newErrors.feedback = 'Feedback or query is required'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!validateForm()) {
      return
    }

    setSubmitting(true)
    setSubmitStatus({ type: null, message: '' })

    try {
      const response = await apiClient.submitContactForm({
        name: formData.name.trim(),
        email: formData.email.trim(),
        feedback: formData.feedback.trim(),
      })

      if (response.error) {
        setSubmitStatus({
          type: 'error',
          message: response.error || 'Failed to submit your message. Please try again later.',
        })
      } else if (response.data) {
        setSubmitStatus({
          type: 'success',
          message: response.data.message || 'Thank you for contacting us! We\'ll get back to you soon.',
        })
        // Clear form on success
        setFormData({ name: '', email: '', feedback: '' })
      } else {
        setSubmitStatus({
          type: 'error',
          message: 'An unexpected error occurred. Please try again later.',
        })
      }
    } catch (error) {
      console.error('Contact form submission error:', error)
      setSubmitStatus({
        type: 'error',
        message: 'An error occurred while submitting your message. Please try again later.',
      })
    } finally {
      setSubmitting(false)
    }
  }

  const handleChange = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
    // Clear error for this field when user starts typing
    if (errors[field]) {
      setErrors((prev) => {
        const newErrors = { ...prev }
        delete newErrors[field]
        return newErrors
      })
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link href="/" className="flex items-center space-x-2">
              <ArrowLeft className="h-5 w-5 text-gray-600 hover:text-gray-900 transition-colors" />
              <span className="text-sm text-gray-600 hover:text-gray-900 transition-colors">Back to Home</span>
            </Link>
            <Link href="/" className="text-2xl font-bold bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
              AIRDOps
            </Link>
            <div className="w-24"></div> {/* Spacer for centering */}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 container mx-auto px-4 py-12 max-w-2xl">
        <div className="bg-white rounded-2xl shadow-xl border border-gray-200 p-8 md:p-12">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full mb-4">
              <Mail className="h-8 w-8 text-white" />
            </div>
            <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-3">
              Support
            </h1>
            <p className="text-gray-600 text-lg">
              Have a question or feedback? We'd love to hear from you!
            </p>
          </div>

          {/* Status Message */}
          {submitStatus.type && (
            <div
              className={`mb-6 p-4 rounded-lg flex items-start space-x-3 ${
                submitStatus.type === 'success'
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-red-50 border border-red-200'
              }`}
            >
              {submitStatus.type === 'success' ? (
                <CheckCircle2 className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
              )}
              <p
                className={`text-sm font-medium ${
                  submitStatus.type === 'success' ? 'text-green-800' : 'text-red-800'
                }`}
              >
                {submitStatus.message}
              </p>
            </div>
          )}

          {/* Contact Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Name Field */}
            <div>
              <Label htmlFor="name" className="text-gray-700 font-medium">
                Name <span className="text-red-500">*</span>
              </Label>
              <Input
                id="name"
                type="text"
                value={formData.name}
                onChange={(e) => handleChange('name', e.target.value)}
                className={`mt-1 ${errors.name ? 'border-red-500 focus:ring-red-500' : ''}`}
                placeholder="Your full name"
                disabled={submitting}
                required
              />
              {errors.name && (
                <p className="mt-1 text-sm text-red-600">{errors.name}</p>
              )}
            </div>

            {/* Email Field */}
            <div>
              <Label htmlFor="email" className="text-gray-700 font-medium">
                Email <span className="text-red-500">*</span>
              </Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => handleChange('email', e.target.value)}
                className={`mt-1 ${errors.email ? 'border-red-500 focus:ring-red-500' : ''}`}
                placeholder="your.email@example.com"
                disabled={submitting}
                required
              />
              {errors.email && (
                <p className="mt-1 text-sm text-red-600">{errors.email}</p>
              )}
            </div>

            {/* Feedback Field */}
            <div>
              <Label htmlFor="feedback" className="text-gray-700 font-medium">
                Message <span className="text-red-500">*</span>
              </Label>
              <Textarea
                id="feedback"
                value={formData.feedback}
                onChange={(e) => handleChange('feedback', e.target.value)}
                className={`mt-1 min-h-[150px] ${errors.feedback ? 'border-red-500 focus:ring-red-500' : ''}`}
                placeholder="Tell us your question, feedback, or any query you have..."
                disabled={submitting}
                required
              />
              {errors.feedback && (
                <p className="mt-1 text-sm text-red-600">{errors.feedback}</p>
              )}
            </div>

            {/* Submit Button */}
            <div className="pt-4">
              <Button
                type="submit"
                disabled={submitting}
                className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold py-3 px-6 rounded-lg transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? (
                  <>
                    <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2 inline-block"></span>
                    Sending...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4 mr-2 inline-block" />
                    Send Message
                  </>
                )}
              </Button>
            </div>
          </form>

          {/* Additional Info */}
          <div className="mt-8 pt-8 border-t border-gray-200">
            <p className="text-sm text-gray-500 text-center">
              We typically respond within 24-48 hours. For urgent matters, please mention it in your message.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  )
}

