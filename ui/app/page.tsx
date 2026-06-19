'use client'

import { useState, useEffect } from 'react'
import { Footer } from '@/components/Footer'
import Link from 'next/link'
import { 
  Sparkles, 
  Shield, 
  BarChart3, 
  TestTube, 
  Link2, 
  Workflow, 
  Download,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  TrendingUp,
  Zap
} from 'lucide-react'

export default function HomePage() {
  const [currentSlide, setCurrentSlide] = useState(0)

  // Auto-rotate carousel
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % 3)
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const getStartedHref = "/dashboard"

  const carouselSlides = [
    {
      title: "AI Trust Score",
      description: "Comprehensive quality metrics for your AI-ready data",
      features: [
        "Real-time trust scoring across 15+ dimensions",
        "Completeness, accuracy, and security validation",
        "Context quality and metadata presence analysis",
        "Knowledge base readiness assessment"
      ],
      icon: Shield,
      color: "blue",
      gradient: "from-blue-500 to-indigo-600"
    },
    {
      title: "Readiness Fingerprint",
      description: "Deep insights into your data's AI readiness profile",
      features: [
        "Multi-dimensional fingerprint analysis",
        "Policy compliance evaluation",
        "Automated threshold validation",
        "Actionable improvement recommendations"
      ],
      icon: BarChart3,
      color: "green",
      gradient: "from-green-500 to-emerald-600"
    },
    {
      title: "RAG Testing & Validation",
      description: "Test your AI-ready data with real-world RAG scenarios",
      features: [
        "End-to-end RAG pipeline testing",
        "Retrieval accuracy validation",
        "Response quality assessment",
        "Export-ready vector embeddings"
      ],
      icon: TestTube,
      color: "purple",
      gradient: "from-purple-500 to-pink-600"
    }
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 flex flex-col">
      {/* Beta Badge - Top Banner */}
      <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white py-2">
        <div className="container mx-auto px-4">
          <div className="flex items-center justify-center space-x-2">
            <Sparkles className="h-4 w-4" />
            <span className="text-sm font-medium">
              AIRDOps Beta Release - We're actively improving based on your feedback
            </span>
          </div>
        </div>
      </div>

      {/* Hero Section */}
      <div className="container mx-auto px-4 py-20">
        <div className="text-center max-w-5xl mx-auto">
          <div className="inline-flex items-center space-x-2 bg-blue-100 text-blue-700 px-4 py-2 rounded-full text-sm font-semibold mb-6">
            <Zap className="h-4 w-4" />
            <span>Enterprise AI Data Platform</span>
          </div>
          
          <h1 className="text-6xl md:text-7xl font-bold mb-4 leading-tight">
            <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
              AIRDOps
            </span>
            <span className="block text-xl md:text-2xl text-gray-500 font-normal mt-5 tracking-normal">
              Making Data AI-Ready
            </span>
          </h1>
          
          <p className="text-base md:text-lg text-gray-600 mb-4 leading-relaxed max-w-3xl mx-auto">
            Transform your data into{' '}
            <span className="font-semibold text-gray-800">production-ready AI assets</span>
            {' '}with enterprise-grade{' '}
            <span className="font-semibold text-gray-800">ingestion, processing, validation, and vectorization</span>.
          </p>
          
          <div className="flex flex-wrap items-center justify-center gap-2 mb-12">
            {[
              { text: 'Ingest', gradient: 'from-blue-500 to-blue-600' },
              { text: 'Clean', gradient: 'from-green-500 to-green-600' },
              { text: 'Chunk', gradient: 'from-purple-500 to-purple-600' },
              { text: 'Embed', gradient: 'from-pink-500 to-pink-600' },
              { text: 'Index', gradient: 'from-indigo-500 to-indigo-600' },
              { text: 'Test', gradient: 'from-cyan-500 to-cyan-600' },
              { text: 'Export', gradient: 'from-orange-500 to-orange-600' }
            ].map((item, index, array) => (
              <span key={item.text} className="flex items-center">
                <span className={`px-4 py-1.5 rounded-full text-sm font-semibold bg-gradient-to-r ${item.gradient} text-white shadow-sm hover:shadow-md transition-all duration-200 hover:scale-105`}>
                  {item.text}
                </span>
                {index < array.length - 1 && (
                  <span className="mx-2 text-gray-300 font-light text-lg">|</span>
                )}
              </span>
            ))}
          </div>
          
          {/* CTA Button */}
          <div className="flex justify-center items-center mb-20">
            <Link
              data-testid="cta-get-started"
              href={getStartedHref}
              className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold py-4 px-12 rounded-xl shadow-lg transition-all duration-200 hover:shadow-xl hover:scale-105 text-lg"
            >
              Get Started
            </Link>
          </div>
        </div>

        {/* Feature Carousel */}
        <div className="max-w-6xl mx-auto mb-20">
          <div className="relative bg-white rounded-2xl shadow-2xl overflow-hidden">
            {/* Carousel Navigation */}
            <div className="absolute top-4 right-4 z-10 flex space-x-2">
              {carouselSlides.map((_, index) => (
                <button
                  key={index}
                  onClick={() => setCurrentSlide(index)}
                  className={`w-2 h-2 rounded-full transition-all ${
                    currentSlide === index ? 'bg-blue-600 w-8' : 'bg-gray-300'
                  }`}
                  aria-label={`Go to slide ${index + 1}`}
                />
              ))}
            </div>

            {/* Carousel Content */}
            <div className="relative h-96 md:h-[500px]">
              {carouselSlides.map((slide, index) => {
                const Icon = slide.icon
                return (
                  <div
                    key={index}
                    className={`absolute inset-0 transition-opacity duration-500 ${
                      currentSlide === index ? 'opacity-100' : 'opacity-0'
                    }`}
                  >
                    <div className={`h-full bg-gradient-to-br ${slide.gradient} p-12 md:p-16`}>
                      <div className="max-w-4xl mx-auto h-full flex flex-col justify-center text-white">
                        <div className="mb-8">
                          <div className="inline-flex items-center justify-center w-16 h-16 bg-white/20 backdrop-blur-sm rounded-2xl mb-6">
                            <Icon className="h-8 w-8 text-white" />
                          </div>
                          <h2 className="text-4xl md:text-5xl font-bold mb-4">{slide.title}</h2>
                          <p className="text-xl md:text-2xl text-white/90 mb-8">{slide.description}</p>
                        </div>
                        <div className="grid md:grid-cols-2 gap-4">
                          {slide.features.map((feature, idx) => (
                            <div key={idx} className="flex items-start space-x-3">
                              <CheckCircle2 className="h-6 w-6 text-white/90 flex-shrink-0 mt-0.5" />
                              <span className="text-lg text-white/90">{feature}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Carousel Controls */}
            <button
              onClick={() => setCurrentSlide((prev) => (prev - 1 + 3) % 3)}
              className="absolute left-4 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white text-gray-800 p-3 rounded-full shadow-lg transition-all hover:scale-110 z-10"
              aria-label="Previous slide"
            >
              <ChevronLeft className="h-6 w-6" />
            </button>
            <button
              onClick={() => setCurrentSlide((prev) => (prev + 1) % 3)}
              className="absolute right-4 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white text-gray-800 p-3 rounded-full shadow-lg transition-all hover:scale-110 z-10"
              aria-label="Next slide"
            >
              <ChevronRight className="h-6 w-6" />
            </button>
          </div>
        </div>

        {/* Core Features Grid */}
        <div className="max-w-7xl mx-auto mb-20">
          <div className="text-center mb-12">
            <h2 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">
              Enterprise-Grade Features
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              Everything you need to prepare, validate, and deploy AI-ready data at scale
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {/* AI Trust Score */}
            <div className="bg-white rounded-2xl p-8 shadow-lg border-2 border-blue-100 hover:border-blue-300 transition-all hover:shadow-2xl hover:-translate-y-1">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl flex items-center justify-center mb-6">
                <Shield className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-4">AI Trust Score</h3>
              <p className="text-gray-600 mb-6 leading-relaxed">
                Comprehensive quality assessment across 15+ dimensions including completeness, 
                accuracy, security, and context quality. Get real-time trust scores for every data product.
              </p>
              <ul className="space-y-2">
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-blue-600 mr-2 flex-shrink-0" />
                  <span>Multi-dimensional scoring</span>
                </li>
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-blue-600 mr-2 flex-shrink-0" />
                  <span>Policy compliance validation</span>
                </li>
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-blue-600 mr-2 flex-shrink-0" />
                  <span>Automated threshold checks</span>
                </li>
              </ul>
            </div>

            {/* Readiness Fingerprint */}
            <div className="bg-white rounded-2xl p-8 shadow-lg border-2 border-green-100 hover:border-green-300 transition-all hover:shadow-2xl hover:-translate-y-1">
              <div className="w-16 h-16 bg-gradient-to-br from-green-500 to-emerald-600 rounded-2xl flex items-center justify-center mb-6">
                <TrendingUp className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-4">Readiness Fingerprint</h3>
              <p className="text-gray-600 mb-6 leading-relaxed">
                Deep insights into your data's AI readiness profile. Understand completeness, 
                metadata presence, knowledge base readiness, and more with detailed fingerprint analysis.
              </p>
              <ul className="space-y-2">
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-green-600 mr-2 flex-shrink-0" />
                  <span>Comprehensive fingerprint metrics</span>
                </li>
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-green-600 mr-2 flex-shrink-0" />
                  <span>Visual analytics dashboard</span>
                </li>
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-green-600 mr-2 flex-shrink-0" />
                  <span>Historical trend tracking</span>
                </li>
              </ul>
            </div>

            {/* RAG Testing */}
            <div className="bg-white rounded-2xl p-8 shadow-lg border-2 border-purple-100 hover:border-purple-300 transition-all hover:shadow-2xl hover:-translate-y-1">
              <div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-pink-600 rounded-2xl flex items-center justify-center mb-6">
                <TestTube className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-4">RAG Testing & Validation</h3>
              <p className="text-gray-600 mb-6 leading-relaxed">
                Test your AI-ready data with real-world RAG scenarios. Validate retrieval accuracy, 
                response quality, and export production-ready vector embeddings for your AI applications.
              </p>
              <ul className="space-y-2">
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-purple-600 mr-2 flex-shrink-0" />
                  <span>End-to-end RAG pipeline testing</span>
                </li>
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-purple-600 mr-2 flex-shrink-0" />
                  <span>Retrieval accuracy metrics</span>
                </li>
                <li className="flex items-center text-gray-700">
                  <CheckCircle2 className="h-5 w-5 text-purple-600 mr-2 flex-shrink-0" />
                  <span>Vector embedding export</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Additional Features */}
        <div className="max-w-7xl mx-auto mb-20">
          <div className="grid md:grid-cols-3 gap-8">
            {/* Connectors */}
            <div className="bg-white rounded-xl p-8 shadow-md border border-gray-100 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-6">
                <Link2 className="w-6 h-6 text-blue-600" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-4">Universal Connectors</h3>
              <p className="text-gray-600 leading-relaxed">
                Seamlessly ingest data from files, APIs, databases, AWS S3, Azure Blob, Google Drive, 
                and cloud storage. Built-in connectors with real-time sync capabilities.
              </p>
            </div>

            {/* Orchestration */}
            <div className="bg-white rounded-xl p-8 shadow-md border border-gray-100 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mb-6">
                <Workflow className="w-6 h-6 text-green-600" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-4">Pipeline Orchestration</h3>
              <p className="text-gray-600 leading-relaxed">
                Powerful data pipeline orchestration with Apache Airflow. Schedule, monitor, and manage 
                complex data workflows with visual DAGs and enterprise-grade reliability.
              </p>
            </div>

            {/* Export */}
            <div className="bg-white rounded-xl p-8 shadow-md border border-gray-100 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-6">
                <Download className="w-6 h-6 text-purple-600" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-4">Export & Integration</h3>
              <p className="text-gray-600 leading-relaxed">
                Export processed data in multiple formats. Integrate with vector databases, 
                AI platforms, and downstream applications with confidence.
              </p>
            </div>
          </div>
        </div>

        {/* Trust Indicators */}
        <div className="max-w-4xl mx-auto text-center mb-20">
          <div className="bg-white rounded-2xl p-12 shadow-lg border-2 border-gray-100">
            <h3 className="text-3xl font-bold text-gray-900 mb-6">
              Enterprise-Ready AI Data Platform
            </h3>
            <div className="grid md:grid-cols-3 gap-8 mt-8">
              <div>
                <div className="text-4xl font-bold text-blue-600 mb-2">15+</div>
                <div className="text-gray-600">Quality Dimensions</div>
              </div>
              <div>
                <div className="text-4xl font-bold text-green-600 mb-2">100%</div>
                <div className="text-gray-600">Policy Compliance</div>
              </div>
              <div>
                <div className="text-4xl font-bold text-purple-600 mb-2">∞</div>
                <div className="text-gray-600">Data Sources</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      {/* Footer */}
      <Footer />
    </div>
  )
}
