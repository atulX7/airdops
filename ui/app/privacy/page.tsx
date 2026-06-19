'use client'

import Link from 'next/link'
import { Footer } from '@/components/Footer'
import { 
  Sparkles, 
  Shield,
  ArrowLeft
} from 'lucide-react'

// Constants
const BETA_BANNER_TEXT = "AIRDOps Beta Release - We're actively improving based on your feedback"
const LAST_UPDATED = new Date().toLocaleDateString('en-US', { 
  year: 'numeric', 
  month: 'long', 
  day: 'numeric' 
})

// Component: Beta Banner
function BetaBanner() {
  return (
    <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white py-2" role="banner">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-center space-x-2" aria-live="polite">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          <span className="text-sm font-medium">{BETA_BANNER_TEXT}</span>
        </div>
      </div>
    </div>
  )
}

// Component: Privacy Section
interface PrivacySectionProps {
  readonly id: string
  readonly title: string
  readonly children: React.ReactNode
  readonly subtitle?: string
}

function PrivacySection({ id, title, subtitle, children }: PrivacySectionProps) {
  return (
    <section id={id} className="mt-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">{title}</h2>
      {subtitle && (
        <h3 className="text-xl font-semibold text-gray-900 mt-6 mb-3">{subtitle}</h3>
      )}
      {children}
    </section>
  )
}

/**
 * Privacy Policy Page Component
 * 
 * Displays privacy policy for AIRDOps platform.
 * Follows enterprise best practices with proper accessibility,
 * semantic HTML, and GDPR compliance considerations.
 */
export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 flex flex-col">
      <BetaBanner />

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

      {/* Content */}
      <main className="container mx-auto px-4 py-16 max-w-4xl">
        <article className="bg-white rounded-2xl shadow-lg border-2 border-gray-100 p-8 md:p-12">
          {/* Header */}
          <header className="flex items-center mb-8">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center mr-4">
              <Shield className="h-6 w-6 text-white" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-gray-900">Privacy Policy</h1>
              <p className="text-gray-600 mt-2">
                Last updated: <time dateTime={LAST_UPDATED}>{LAST_UPDATED}</time>
              </p>
            </div>
          </header>

          {/* Content */}
          <div className="prose prose-lg max-w-none space-y-8 text-gray-700">
            <section>
              <p className="text-lg">
                At AIRDOps, we take your privacy seriously. This Privacy Policy explains how we collect, use, disclose, 
                and safeguard your information when you use our Service.
              </p>
            </section>

            <PrivacySection id="information-collection" title="1. Information We Collect">
              <div className="mt-6">
                <h3 className="text-xl font-semibold text-gray-900 mb-3">1.1 Personal Information</h3>
                <p>
                  We collect information that you provide directly to us, including:
                </p>
                <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                  <li>Name and email address when you create an account</li>
                  <li>Payment information (processed securely through third-party payment processors)</li>
                  <li>Profile information and preferences</li>
                  <li>Communications with our support team</li>
                </ul>
              </div>

              <div className="mt-6">
                <h3 className="text-xl font-semibold text-gray-900 mb-3">1.2 Usage Information</h3>
                <p>
                  We automatically collect certain information about your use of the Service, including:
                </p>
                <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                  <li>Log data (IP address, browser type, pages visited)</li>
                  <li>Device information (device type, operating system)</li>
                  <li>Usage patterns and feature interactions</li>
                  <li>Performance and error data</li>
                </ul>
              </div>

              <div className="mt-6">
                <h3 className="text-xl font-semibold text-gray-900 mb-3">1.3 Data You Process</h3>
                <p>
                  We process data that you upload to AIRDOps for the purpose of providing our services. You retain all ownership 
                  and rights to your data. We do not use your processed data for any purpose other than providing the Service.
                </p>
              </div>
            </PrivacySection>

            <PrivacySection id="information-use" title="2. How We Use Your Information">
              <p>We use the information we collect to:</p>
              <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                <li>Provide, maintain, and improve our Service</li>
                <li>Process transactions and send related information</li>
                <li>Send technical notices, updates, and support messages</li>
                <li>Respond to your comments, questions, and requests</li>
                <li>Monitor and analyze trends, usage, and activities</li>
                <li>Detect, prevent, and address technical issues and security threats</li>
                <li>Personalize and improve your experience</li>
              </ul>
            </PrivacySection>

            <PrivacySection id="information-sharing" title="3. Information Sharing and Disclosure">
              <p>We do not sell your personal information. We may share your information only in the following circumstances:</p>
              <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                <li><strong>Service Providers:</strong> With third-party vendors who perform services on our behalf</li>
                <li><strong>Legal Requirements:</strong> When required by law or to protect our rights</li>
                <li><strong>Business Transfers:</strong> In connection with a merger, acquisition, or sale of assets</li>
                <li><strong>With Your Consent:</strong> When you have given us explicit permission to share</li>
              </ul>
            </PrivacySection>

            <PrivacySection id="data-security" title="4. Data Security">
              <p>
                We implement appropriate technical and organizational security measures to protect your information against 
                unauthorized access, alteration, disclosure, or destruction. These measures include:
              </p>
              <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                <li>Encryption of data in transit and at rest</li>
                <li>Regular security assessments and audits</li>
                <li>Access controls and authentication</li>
                <li>Secure data centers and infrastructure</li>
                <li>Employee training on data protection</li>
              </ul>
            </PrivacySection>

            <PrivacySection id="user-rights" title="5. Your Rights and Choices">
              <p>You have the following rights regarding your personal information:</p>
              <ul className="list-disc pl-6 space-y-2 mt-4" role="list">
                <li><strong>Access:</strong> Request access to your personal information</li>
                <li><strong>Correction:</strong> Request correction of inaccurate information</li>
                <li><strong>Deletion:</strong> Request deletion of your personal information</li>
                <li><strong>Portability:</strong> Request transfer of your data</li>
                <li><strong>Opt-out:</strong> Unsubscribe from marketing communications</li>
                <li><strong>Account Deletion:</strong> Delete your account and associated data</li>
              </ul>
              <p className="mt-4">
                To exercise these rights, please contact us at{' '}
                <Link href="/contact" className="text-blue-600 hover:text-blue-700 underline">
                  our contact page
                </Link>.
              </p>
            </PrivacySection>

            <PrivacySection id="data-retention" title="6. Data Retention">
              <p>
                We retain your personal information for as long as necessary to provide the Service and fulfill the purposes 
                outlined in this Privacy Policy, unless a longer retention period is required or permitted by law. When you 
                delete your account, we will delete or anonymize your personal information, except where we are required to 
                retain it for legal or legitimate business purposes.
              </p>
            </PrivacySection>

            <PrivacySection id="international-transfers" title="7. International Data Transfers">
              <p>
                Your information may be transferred to and processed in countries other than your country of residence. 
                These countries may have data protection laws that differ from those in your country. We ensure appropriate 
                safeguards are in place to protect your information in accordance with this Privacy Policy.
              </p>
            </PrivacySection>

            <PrivacySection id="children-privacy" title="8. Children's Privacy">
              <p>
                Our Service is not intended for individuals under the age of 18. We do not knowingly collect personal 
                information from children. If you become aware that a child has provided us with personal information, 
                please contact us immediately.
              </p>
            </PrivacySection>

            <PrivacySection id="cookies" title="9. Cookies and Tracking Technologies">
              <p>
                We use cookies and similar tracking technologies to track activity on our Service and hold certain information. 
                You can instruct your browser to refuse all cookies or to indicate when a cookie is being sent. However, 
                if you do not accept cookies, you may not be able to use some portions of our Service.
              </p>
            </PrivacySection>

            <PrivacySection id="changes" title="10. Changes to This Privacy Policy">
              <p>
                We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new 
                Privacy Policy on this page and updating the "Last updated" date. You are advised to review this Privacy 
                Policy periodically for any changes.
              </p>
            </PrivacySection>

            <PrivacySection id="contact" title="11. Contact Us">
              <p>
                If you have any questions about this Privacy Policy, please contact us at{' '}
                <Link href="/contact" className="text-blue-600 hover:text-blue-700 underline">
                  our contact page
                </Link>.
              </p>
            </PrivacySection>
          </div>
        </article>
      </main>

      <Footer />
    </div>
  )
}

