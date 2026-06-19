'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { Footer } from '@/components/Footer'
import { 
  Sparkles, 
  CheckCircle2,
  Zap,
  Shield,
  Rocket,
  Building,
  ArrowLeft,
  type LucideIcon
} from 'lucide-react'

// Type definitions
interface PricingPlan {
  readonly name: string
  readonly price: string
  readonly period: string
  readonly description: string
  readonly icon: LucideIcon
  readonly gradient: string
  readonly features: readonly string[]
  readonly cta: string
  readonly ctaHref: string
  readonly popular: boolean
}

interface FAQItem {
  readonly question: string
  readonly answer: string
}

// Constants
const PLANS: readonly PricingPlan[] = [
  {
    name: "Starter",
    price: "$99",
    period: "/month",
    description: "Perfect for small teams getting started with AI data",
    icon: Zap,
    gradient: "from-blue-500 to-indigo-600",
    features: [
      "Up to 10,000 documents/month",
      "5 data sources",
      "Basic AI trust scoring",
      "Standard embedding models",
      "Email support",
      "Community access"
    ] as const,
    cta: "Start Free Trial",
    ctaHref: "/signin",
    popular: false
  },
  {
    name: "Professional",
    price: "$499",
    period: "/month",
    description: "For growing teams with advanced needs",
    icon: Rocket,
    gradient: "from-purple-500 to-pink-600",
    features: [
      "Up to 100,000 documents/month",
      "Unlimited data sources",
      "Advanced AI trust scoring",
      "Custom embedding models",
      "Priority support",
      "Advanced analytics",
      "RAG testing suite",
      "API access"
    ] as const,
    cta: "Start Free Trial",
    ctaHref: "/signin",
    popular: true
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For large organizations with custom requirements",
    icon: Building,
    gradient: "from-gray-700 to-gray-900",
    features: [
      "Unlimited documents",
      "Unlimited data sources",
      "Full AI trust scoring suite",
      "Custom embedding models",
      "Dedicated support",
      "Custom integrations",
      "SLA guarantees",
      "On-premise deployment",
      "Custom training & onboarding",
      "Account manager"
    ] as const,
    cta: "Contact Sales",
    ctaHref: "/contact",
    popular: false
  }
] as const

const FAQ: readonly FAQItem[] = [
  {
    question: "Can I change plans later?",
    answer: "Yes, you can upgrade or downgrade your plan at any time. Changes take effect immediately."
  },
  {
    question: "What happens after my free trial?",
    answer: "After your 14-day free trial, you'll be automatically enrolled in the plan you selected. You can cancel anytime."
  },
  {
    question: "Do you offer discounts for annual plans?",
    answer: "Yes! Annual plans receive a 20% discount. Contact sales for more information."
  },
  {
    question: "What payment methods do you accept?",
    answer: "We accept all major credit cards, ACH transfers, and can arrange invoicing for Enterprise customers."
  }
] as const

const BETA_BANNER_TEXT = "AIRDOps Beta Release - We're actively improving based on your feedback"

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

// Component: Pricing Card
function PricingCard({ plan, index }: { plan: PricingPlan; index: number }) {
  const Icon = plan.icon
  
  return (
    <article
      className={`bg-white rounded-2xl p-8 shadow-lg border-2 transition-all hover:shadow-2xl hover:-translate-y-1 ${
        plan.popular
          ? 'border-blue-500 scale-105 relative'
          : 'border-gray-100'
      }`}
      aria-labelledby={`plan-${index}-title`}
    >
      {plan.popular && (
        <div 
          className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4 py-1 rounded-full text-sm font-semibold"
          aria-label="Most popular plan"
        >
          Most Popular
        </div>
      )}
      <div className={`w-16 h-16 bg-gradient-to-br ${plan.gradient} rounded-2xl flex items-center justify-center mb-6`}>
        <Icon className="h-8 w-8 text-white" aria-hidden="true" />
      </div>
      <h3 id={`plan-${index}-title`} className="text-2xl font-bold text-gray-900 mb-2">
        {plan.name}
      </h3>
      <p className="text-gray-600 mb-6">{plan.description}</p>
      <div className="mb-6">
        <span className="text-4xl font-bold text-gray-900">{plan.price}</span>
        {plan.period && <span className="text-gray-600">{plan.period}</span>}
      </div>
      <Link
        href={plan.ctaHref}
        className={`w-full block text-center py-3 px-6 rounded-xl font-semibold transition-all duration-200 mb-6 focus:outline-none focus:ring-2 focus:ring-offset-2 ${
          plan.popular
            ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:from-blue-700 hover:to-indigo-700 shadow-lg hover:shadow-xl focus:ring-blue-500'
            : 'bg-gray-100 text-gray-900 hover:bg-gray-200 focus:ring-gray-500'
        }`}
        aria-label={`${plan.cta} for ${plan.name} plan`}
      >
        {plan.cta}
      </Link>
      <ul className="space-y-3" role="list">
        {plan.features.map((feature, idx) => (
          <li key={idx} className="flex items-start text-gray-700">
            <CheckCircle2 
              className="h-5 w-5 text-blue-600 mr-2 flex-shrink-0 mt-0.5" 
              aria-hidden="true"
            />
            <span className="text-sm">{feature}</span>
          </li>
        ))}
      </ul>
    </article>
  )
}

// Component: FAQ Section
function FAQSection() {
  return (
    <section className="max-w-4xl mx-auto mb-16" aria-labelledby="faq-heading">
      <h2 id="faq-heading" className="text-3xl font-bold text-gray-900 text-center mb-8">
        Frequently Asked Questions
      </h2>
      <div className="bg-white rounded-2xl p-8 shadow-lg border-2 border-gray-100 space-y-6">
        {FAQ.map((item, index) => (
          <div key={index}>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              {item.question}
            </h3>
            <p className="text-gray-600">{item.answer}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/**
 * Pricing Page Component
 * 
 * Displays pricing plans and FAQ for AIRDOps platform.
 * Follows enterprise best practices with proper TypeScript types,
 * accessibility, and performance optimizations.
 */
export default function PricingPage() {
  const plans = useMemo(() => PLANS, [])

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

      {/* Hero Section */}
      <header className="container mx-auto px-4 py-16">
        <div className="text-center max-w-4xl mx-auto mb-16">
          <div className="inline-flex items-center space-x-2 bg-blue-100 text-blue-700 px-4 py-2 rounded-full text-sm font-semibold mb-6">
            <Shield className="h-4 w-4" aria-hidden="true" />
            <span>Simple, Transparent Pricing</span>
          </div>
          
          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 mb-6 leading-tight">
            Choose Your Plan
          </h1>
          
          <p className="text-xl text-gray-600 mb-8 leading-relaxed">
            Start free, scale as you grow. All plans include a 14-day free trial.
          </p>
        </div>
      </header>

      {/* Pricing Cards */}
      <main className="container mx-auto px-4 mb-16">
        <div 
          className="grid md:grid-cols-3 gap-8 max-w-7xl mx-auto mb-16"
          role="list"
          aria-label="Pricing plans"
        >
          {plans.map((plan, index) => (
            <PricingCard key={plan.name} plan={plan} index={index} />
          ))}
        </div>

        <FAQSection />
      </main>

      <Footer />
    </div>
  )
}

