'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import { Footer } from '@/components/Footer'
import { 
  Sparkles, 
  Shield, 
  BarChart3, 
  TestTube, 
  Link2, 
  Workflow, 
  Download,
  CheckCircle2,
  TrendingUp,
  Zap,
  Database,
  FileText,
  Cloud,
  Lock,
  Gauge,
  Layers,
  Search,
  Code,
  Settings,
  ArrowLeft,
  type LucideIcon
} from 'lucide-react'

// Type definitions
interface Feature {
  category: string
  icon: LucideIcon
  gradient: string
  items: readonly string[]
}

interface FeatureSectionProps {
  features: readonly Feature[]
}

// Constants - extracted outside component for better performance
const FEATURES: readonly Feature[] = [
  {
    category: "AI Trust & Quality",
    icon: Shield,
    gradient: "from-blue-500 to-indigo-600",
    items: [
      "Real-time trust scoring across 15+ dimensions",
      "Completeness, accuracy, and security validation",
      "Context quality and metadata presence analysis",
      "Knowledge base readiness assessment",
      "Policy compliance evaluation",
      "Automated threshold validation"
    ] as const
  },
  {
    category: "Data Processing",
    icon: Workflow,
    gradient: "from-green-500 to-emerald-600",
    items: [
      "Multi-format data ingestion",
      "Intelligent chunking strategies",
      "Advanced text preprocessing",
      "Metadata extraction and enrichment",
      "Data cleaning and normalization",
      "Duplicate detection and removal"
    ] as const
  },
  {
    category: "Vectorization & Embeddings",
    icon: Layers,
    gradient: "from-purple-500 to-pink-600",
    items: [
      "Multiple embedding model support",
      "Custom embedding dimensions",
      "Batch processing optimization",
      "Vector similarity search",
      "Embedding quality validation",
      "Export-ready vector formats"
    ] as const
  },
  {
    category: "Data Sources & Connectors",
    icon: Link2,
    gradient: "from-orange-500 to-red-600",
    items: [
      "File uploads (PDF, TXT, DOCX)",
      "AWS S3 integration",
      "Azure Blob Storage",
      "Google Drive connector",
      "Web scraping and crawling",
      "Database connectors (coming soon)"
    ] as const
  },
  {
    category: "RAG Testing & Validation",
    icon: TestTube,
    gradient: "from-cyan-500 to-blue-600",
    items: [
      "End-to-end RAG pipeline testing",
      "Retrieval accuracy validation",
      "Response quality assessment",
      "Query performance metrics",
      "Context relevance scoring",
      "Export test results"
    ] as const
  },
  {
    category: "Analytics & Insights",
    icon: BarChart3,
    gradient: "from-indigo-500 to-purple-600",
    items: [
      "Readiness fingerprint analysis",
      "Historical trend tracking",
      "Quality metrics dashboard",
      "Performance benchmarking",
      "Custom report generation",
      "Data export and sharing"
    ] as const
  },
  {
    category: "Pipeline Orchestration",
    icon: Settings,
    gradient: "from-teal-500 to-green-600",
    items: [
      "Apache Airflow integration",
      "Visual DAG workflows",
      "Scheduled data processing",
      "Pipeline monitoring and alerts",
      "Error handling and retries",
      "Version control for pipelines"
    ] as const
  },
  {
    category: "Security & Compliance",
    icon: Lock,
    gradient: "from-gray-700 to-gray-900",
    items: [
      "Enterprise-grade security",
      "Data encryption at rest and in transit",
      "Access control and permissions",
      "Audit logging",
      "GDPR compliance",
      "SOC 2 ready"
    ] as const
  }
] as const

const BETA_BANNER_TEXT = "AIRDOps Beta Release - We're actively improving based on your feedback"

// Component: Beta Banner (reusable)
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

// Component: Feature Card (extracted for reusability)
function FeatureCard({ feature, index }: { feature: Feature; index: number }) {
  const Icon = feature.icon
  
  return (
    <article
      className="bg-white rounded-2xl p-8 shadow-lg border-2 border-gray-100 hover:border-blue-300 transition-all hover:shadow-2xl hover:-translate-y-1"
      aria-labelledby={`feature-${index}-title`}
    >
      <div className={`w-16 h-16 bg-gradient-to-br ${feature.gradient} rounded-2xl flex items-center justify-center mb-6`}>
        <Icon className="h-8 w-8 text-white" aria-hidden="true" />
      </div>
      <h3 id={`feature-${index}-title`} className="text-2xl font-bold text-gray-900 mb-4">
        {feature.category}
      </h3>
      <ul className="space-y-3" role="list">
        {feature.items.map((item, idx) => (
          <li key={idx} className="flex items-start text-gray-700">
            <CheckCircle2 
              className="h-5 w-5 text-blue-600 mr-2 flex-shrink-0 mt-0.5" 
              aria-hidden="true"
            />
            <span className="text-sm leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
    </article>
  )
}

// Component: CTA Section (extracted for reusability)
function CTASection() {
  return (
    <section 
      className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-12 text-center text-white mb-16"
      aria-labelledby="cta-heading"
    >
      <h2 id="cta-heading" className="text-3xl font-bold mb-4">
        Ready to Get Started?
      </h2>
      <p className="text-xl text-blue-100 mb-8">
        Transform your data into AI-ready assets today
      </p>
      <div className="flex flex-col sm:flex-row gap-4 justify-center">
        <Link
          href="/signin"
          className="bg-white hover:bg-gray-50 text-blue-600 font-semibold py-3 px-8 rounded-xl shadow-lg transition-all duration-200 hover:shadow-xl hover:scale-105 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-600"
          aria-label="Sign up for a free account"
        >
          Sign Up Free
        </Link>
        <Link
          href="/contact"
          className="bg-blue-700 hover:bg-blue-800 text-white font-semibold py-3 px-8 rounded-xl shadow-lg transition-all duration-200 hover:shadow-xl hover:scale-105 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:ring-offset-2 focus:ring-offset-blue-600"
          aria-label="Contact our sales team"
        >
          Contact Sales
        </Link>
      </div>
    </section>
  )
}

/**
 * Features Page Component
 * 
 * Displays comprehensive feature list for AIRDOps platform.
 * Follows enterprise best practices with proper TypeScript types,
 * accessibility, and performance optimizations.
 */
export default function FeaturesPage() {
  // Memoize features to prevent unnecessary re-renders
  const features = useMemo(() => FEATURES, [])

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
            <Zap className="h-4 w-4" aria-hidden="true" />
            <span>Comprehensive Feature Set</span>
          </div>
          
          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 mb-6 leading-tight">
            Enterprise Features
          </h1>
          
          <p className="text-xl text-gray-600 mb-8 leading-relaxed">
            Everything you need to transform your data into production-ready AI assets
          </p>
        </div>
      </header>

      {/* Features Grid */}
      <main className="container mx-auto px-4 mb-16">
        <div 
          className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 mb-16"
          role="list"
          aria-label="Product features"
        >
          {features.map((feature, index) => (
            <FeatureCard key={feature.category} feature={feature} index={index} />
          ))}
        </div>

        <CTASection />
      </main>

      <Footer />
    </div>
  )
}

