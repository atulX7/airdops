'use client'

import { useState, useEffect, FormEvent, useRef } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter, usePathname } from 'next/navigation'
import AppLayout from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { apiClient } from '@/lib/api-client'
import { 
  ChevronDown, 
  ChevronUp, 
  BookOpen, 
  Play, 
  Package, 
  Database, 
  BarChart3,
  Shield,
  FileText,
  Layers,
  Search,
  HelpCircle,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Info,
  Send,
  MessageSquare,
  type LucideIcon
} from 'lucide-react'

interface FAQItem {
  question: string
  answer: React.ReactNode
  category: 'getting-started' | 'features' | 'metrics' | 'troubleshooting'
}

interface MetricCategoryConfig {
  name: string
  icon: LucideIcon
  metrics: {
    key: string
    name: string
    description: string
  }[]
  note?: string
}

const METRIC_CATEGORIES: Record<string, MetricCategoryConfig> = {
  governance: {
    name: 'Governance & Compliance',
    icon: Shield,
    metrics: [
      { 
        key: 'Secure', 
        name: 'Security', 
        description: 'Measures how well your data protects sensitive information. This metric detects Personally Identifiable Information (PII) like email addresses, phone numbers, social security numbers, and other private data. Higher scores (80%+) mean your data is safe for AI use without privacy concerns. Lower scores indicate you should remove or anonymize sensitive information before processing. This is critical for compliance with regulations like GDPR and HIPAA.' 
      },
      { 
        key: 'Completeness', 
        name: 'Completeness', 
        description: 'Evaluates whether your content has enough information to be useful for AI. Think of it like checking if a book has all its chapters - incomplete content leads to poor AI responses. This metric checks token count (words/characters) and ensures content isn\'t empty or truncated. Scores above 70% mean your data has sufficient detail. For vector search, incomplete chunks return irrelevant results because they lack context. Higher completeness = better AI understanding and more accurate answers.' 
      },
      { 
        key: 'Accuracy', 
        name: 'Accuracy', 
        description: 'Measures how clean and error-free your text is. This metric checks for spelling mistakes, encoding issues (like garbled characters), and text quality. Think of it as proofreading your data. Higher scores (75%+) mean your content is clean and reliable. Low accuracy scores indicate typos, encoding problems, or corrupted text that confuse AI models. For vectors, inaccurate text creates poor embeddings because the AI model struggles to understand garbled or misspelled words, leading to incorrect search results.' 
      },
      { 
        key: 'Metadata_Presence', 
        name: 'Metadata Presence', 
        description: 'Checks if your data includes helpful labels and organization information. Metadata is like tags on a library book - it tells you which section it belongs to, what it\'s about, and its ID. This metric looks for fields like section, field_name, and document_id. Higher scores (80%+) mean your data is well-organized. For vector search, metadata helps filter results (e.g., "only search in the API documentation section"). Without metadata, you can\'t organize or filter your search results effectively. This is especially important for large knowledge bases with multiple topics.' 
      },
    ],
  },
  content: {
    name: 'Content Quality',
    icon: FileText,
    metrics: [
      { 
        key: 'Quality', 
        name: 'Quality', 
        description: 'Overall readability and structure of your content. This metric uses the Flesch Reading Ease test (like a readability score) and analyzes sentence length. Higher scores (70%+) mean your content is well-written, clear, and easy to understand. For AI and vectors, high-quality text creates better embeddings because the AI model can more easily understand well-structured sentences. Poor quality (run-on sentences, unclear writing) leads to confusing embeddings and inaccurate search results.' 
      },
      { 
        key: 'Context_Quality', 
        name: 'Context Quality', 
        description: 'Measures how rich and informative your content is. This metric looks for structured elements (paragraphs, bullet points, numbered lists), factual information (numbers, dates, statistics), and references to other content. Think of it as checking if your content has "meat" - real information, not just fluff. Higher scores (75%+) mean your content is information-dense and useful. For vectors, context-rich content creates embeddings that capture meaning better, leading to more relevant search results. Low context quality means your AI might return generic or unhelpful answers.' 
      },
      { 
        key: 'Audience_Intentionality', 
        name: 'Audience Intentionality', 
        description: 'Checks if your content is written for a specific audience. This metric looks for audience labels or indicators that show who the content is meant for (e.g., "developers", "end users", "administrators"). Higher scores mean your content is targeted and relevant. For vector search, this helps ensure users get answers appropriate to their role. Without audience targeting, a developer might get end-user documentation, or vice versa, leading to confusion.' 
      },
      { 
        key: 'Audience_Accessibility', 
        name: 'Audience Accessibility', 
        description: 'Measures how easy your content is to read based on sentence length. The ideal range is 10-25 words per sentence. Shorter sentences are clearer; very long sentences are hard to follow. This metric helps ensure your content is digestible. For AI, accessible content is easier to process and understand. Extremely long sentences can confuse both humans and AI models, leading to poor comprehension and inaccurate embeddings.' 
      },
      { 
        key: 'Diversity', 
        name: 'Diversity', 
        description: 'Measures vocabulary variety in your content. This uses the type-token ratio - the number of unique words divided by total words. Higher scores (60%+) mean your content uses varied language instead of repeating the same words. Think of it as checking if you\'re using synonyms and different ways to express ideas. For vectors, diverse vocabulary creates richer embeddings that capture more nuanced meanings. Repetitive content (low diversity) creates similar embeddings for different concepts, making it harder to distinguish between topics in search results.' 
      },
      { 
        key: 'Timeliness', 
        name: 'Timeliness', 
        description: 'Checks how recent your content is. This metric compares content timestamps to a reference date. Newer content gets higher scores. For AI applications, outdated information leads to incorrect answers. For example, if your documentation says "use API v1" but v2 is current, users get wrong information. Higher timeliness scores (80%+) mean your knowledge base is up-to-date. This is especially important for technical documentation, policies, and procedures that change frequently.' 
      },
      { 
        key: 'KnowledgeBase_Ready', 
        name: 'Knowledge Base Ready', 
        description: 'A composite score (40% metadata + 40% quality + 20% context) that predicts how well your data will work in RAG (Retrieval-Augmented Generation) applications. This is like an overall "readiness grade" for AI use. Scores above 80% mean your data is excellent for chatbots and knowledge bases. Scores 60-80% are good but could be improved. Below 60% means you should address quality issues before deploying. This metric combines the most important factors for successful AI applications.' 
      },
      { 
        key: 'Token_Count', 
        name: 'Token Count', 
        description: 'Measures if your content chunks are the right size (around 900 tokens, roughly 600-700 words). Tokens are how AI models count text - one token is about 4 characters. Chunks that are too small lack context; chunks that are too large are hard to process and retrieve. This metric normalizes around the optimal size. For vectors, properly sized chunks create embeddings that are detailed enough to be useful but focused enough to be accurate. Wrong-sized chunks lead to poor search results - too small = missing context, too large = irrelevant information mixed in.' 
      },
    ],
  },
  chunking: {
    name: 'Chunking & Structure',
    icon: Layers,
    metrics: [
      { 
        key: 'Chunk_Coherence', 
        name: 'Chunk Coherence', 
        description: 'Measures how well each chunk stays on a single topic. Think of it like checking if a paragraph is about one thing or jumps between topics. This metric uses AI embeddings to compare sentences within a chunk - if they\'re similar, the chunk is coherent. Higher scores (75%+) mean your chunks are focused and clear. For vectors, coherent chunks create better embeddings because all the information in a chunk relates to the same topic. Low coherence means a chunk might mix topics (e.g., talking about both "authentication" and "billing" in one chunk), leading to confusing search results where users get mixed information.' 
      },
      { 
        key: 'Noise_Free_Score', 
        name: 'Noise-Free Score', 
        description: 'Measures how much of your content is actual useful information versus "noise" like navigation menus, legal footers, cookie notices, headers, and boilerplate text. Think of it as checking if your content is clean or cluttered with website elements. Higher scores (80%+) mean your content is clean and useful. For vectors, noise-free content creates better embeddings because the AI focuses on actual information, not navigation elements. Low scores mean your search results might include irrelevant footer text or navigation menus instead of useful content.' 
      },
      { 
        key: 'Chunk_Boundary_Quality', 
        name: 'Chunk Boundary Quality', 
        description: 'Checks if your content is split at good breaking points (like the end of a sentence or paragraph) versus in the middle of sentences. This metric measures how often chunks break mid-sentence. Lower mid-sentence breaks = better chunking. Higher scores (80%+) mean chunks break at natural points. For vectors, good boundaries ensure each chunk is a complete thought, making embeddings more meaningful. Poor boundaries (breaking mid-sentence) create confusing chunks that start or end with incomplete thoughts, leading to poor search results and AI responses that don\'t make sense.' 
      },
    ],
  },
  vector: {
    name: 'Vector Metrics',
    icon: Database,
    metrics: [
      { 
        key: 'Embedding_Dimension_Consistency', 
        name: 'Embedding Dimension Consistency', 
        description: 'Checks if all your vector embeddings have the correct size (dimension). Think of dimensions like the size of a box - all boxes should be the same size to stack properly. Each embedding model has a specific dimension (e.g., 384, 768, or 1536 numbers). This metric ensures 100% of your vectors match the expected size. For vector search, inconsistent dimensions break the search system - you can\'t compare vectors of different sizes. Scores below 100% indicate errors in embedding generation that need to be fixed. This is critical for search accuracy.' 
      },
      { 
        key: 'Embedding_Success_Rate', 
        name: 'Embedding Success Rate', 
        description: 'Measures what percentage of your content chunks were successfully converted into vector embeddings and stored in the database. Higher rates (95%+) mean almost all your content is searchable. Lower rates mean some content failed to embed (due to errors, API issues, or invalid text). For vector search, low success rates mean parts of your knowledge base aren\'t searchable - users won\'t find those chunks even if they\'re relevant. This directly impacts search coverage and user experience.' 
      },
      { 
        key: 'Vector_Quality_Score', 
        name: 'Vector Quality Score', 
        description: 'A comprehensive check of your vector embeddings to ensure they\'re valid and useful. This metric checks three things: 1) No invalid numbers (NaN/Inf) that break calculations, 2) Vectors aren\'t all zeros (which would be meaningless), and 3) Vector magnitudes (norms) are in a healthy range. Think of it as quality control for your embeddings. Higher scores (80%+) mean your vectors are mathematically sound. For search, low-quality vectors return incorrect results because the math behind similarity calculations breaks down. This is essential for reliable semantic search.' 
      },
      { 
        key: 'Embedding_Model_Health', 
        name: 'Embedding Model Health', 
        description: 'Monitors the health and reliability of the AI model used to create your embeddings. This checks API error rates, whether fallback models were needed, dimension consistency, and response quality. Higher scores (85%+) mean your embedding model is working reliably. Low scores indicate API issues, model failures, or inconsistent behavior. For vector search, an unhealthy model creates poor embeddings, leading to inaccurate search results. This metric helps you identify when to switch models or fix API configuration issues.' 
      },
      { 
        key: 'Semantic_Search_Readiness', 
        name: 'Semantic Search Readiness', 
        description: 'An overall score (25% dimension + 35% quality + 25% health + 15% success rate) that predicts how well your vector database will perform in semantic search. This is like a "health check" for your entire vector search system. Scores above 85% mean your vectors are excellent for search. Scores 70-85% are good but could be improved. Below 70% means you should fix vector issues before deploying search. This metric combines all vector quality factors to give you confidence that your search will work well. Higher readiness = more accurate, relevant search results for users.' 
      },
    ],
    note: 'These metrics are only available when vector creation is enabled for your product. They are critical for ensuring your semantic search works accurately.',
  },
  rag: {
    name: 'RAG Performance',
    icon: Search,
    metrics: [
      { 
        key: 'Retrieval_Recall_At_K', 
        name: 'Retrieval Recall@K', 
        description: 'Measures how often your search system finds the right content. This metric tests if chunks can retrieve themselves - for each chunk, it uses the first sentence as a search query and checks if the original chunk appears in the top K results. Higher scores (75%+) mean your search is finding relevant content most of the time. Lower scores mean users often won\'t find what they\'re looking for, even if it exists in your knowledge base. This is critical for RAG applications - if recall is low, your AI chatbot will give wrong answers because it can\'t find the right information. Think of it as "coverage" - what percentage of your content is actually findable through search.' 
      },
      { 
        key: 'Average_Precision_At_K', 
        name: 'Average Precision@K', 
        description: 'Measures how well your search ranks results - are the most relevant results at the top of the list? This metric checks where the correct chunk appears in search results. If it\'s at position 1, that\'s perfect. If it\'s at position 10, that\'s poor. Higher scores (80%+) mean relevant results appear near the top. Lower scores mean users have to scroll through irrelevant results to find what they need. For RAG applications, high precision means your AI gets the best information first, leading to more accurate answers. Low precision means your AI might use less relevant information, giving suboptimal responses. This directly impacts answer quality.' 
      },
    ],
    note: 'These metrics are only available when vector creation is enabled. They use self-retrieval evaluation (testing if chunks can find themselves) to predict how well your RAG system will perform in production. Higher scores = better AI responses.',
  },
}

export default function HelpPage() {
  const { data: session } = useSession()
  const router = useRouter()
  const pathname = usePathname()
  const [activeTab, setActiveTab] = useState<'faq' | 'support'>('faq')
  const hashCheckIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set())
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
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

  // Check for hash in URL to switch to support tab
  useEffect(() => {
    const checkHash = () => {
      if (typeof window !== 'undefined') {
        const hash = window.location.hash
        if (hash === '#contact' || hash === '#support') {
          setActiveTab('support')
          // Browser will automatically scroll to #contact-support element
        } else if (!hash || hash === '') {
          setActiveTab('faq')
        }
      }
    }

    // Check hash on mount and when pathname changes
    checkHash()

    // Listen for hash changes
    window.addEventListener('hashchange', checkHash)

    // Also poll for hash changes (fallback for Next.js Link navigation)
    // This handles cases where hashchange event doesn't fire
    hashCheckIntervalRef.current = setInterval(() => {
      checkHash()
    }, 100) // Check every 100ms

    // Cleanup
    return () => {
      window.removeEventListener('hashchange', checkHash)
      if (hashCheckIntervalRef.current) {
        clearInterval(hashCheckIntervalRef.current)
      }
    }
  }, [pathname]) // Re-run when pathname changes

  // Pre-populate name and email from session
  useEffect(() => {
    if (session?.user) {
      setFormData((prev) => ({
        ...prev,
        name: session.user?.name || '',
        email: session.user?.email || '',
      }))
    }
  }, [session])

  const toggleItem = (id: string) => {
    setExpandedItems(prev => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }

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
        // Clear only feedback field on success, keep name and email
        setFormData((prev) => ({ ...prev, feedback: '' }))
      } else {
        setSubmitStatus({
          type: 'error',
          message: 'An unexpected error occurred. Please try again later.',
        })
      }
    } catch (error) {
      console.error('Support form submission error:', error)
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

  const faqItems: FAQItem[] = [
    // Getting Started
    {
      category: 'getting-started',
      question: 'How do I get started with AIRDOps?',
      answer: (
        <div className="space-y-4">
          <p className="text-gray-700">Follow these steps to get started:</p>
          <ol className="list-decimal list-inside space-y-2 text-gray-700 ml-4">
            <li><strong>Create a Product:</strong> Go to Products → New Product. Give it a name and optionally select a playbook.</li>
            <li><strong>Add Data Sources:</strong> Navigate to your product → Data Sources tab → Add Data Source. Connect your data (web, database, Confluence, SharePoint, or folder).</li>
            <li><strong>Run the Pipeline:</strong> Go to your product → Overview tab → Click "Run Pipeline" to process your data.</li>
            <li><strong>Review Metrics:</strong> After the pipeline completes, check the AI Trust Score tab to see quality metrics and recommendations.</li>
            <li><strong>Enable Vector Creation (Optional):</strong> If you need semantic search, enable vector creation in product settings to generate embeddings and RAG metrics.</li>
          </ol>
        </div>
      ),
    },
    {
      category: 'getting-started',
      question: 'What is a Product in AIRDOps?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            A <strong>Product</strong> is a container for your data that goes through the complete AI readiness pipeline. 
            Each product represents a distinct dataset or knowledge base that you want to make AI-ready.
          </p>
          <p className="text-gray-700">
            Products have versions, allowing you to track changes over time. You can have multiple products 
            for different use cases (e.g., "Product Documentation", "Customer Support KB", "Internal Wiki").
          </p>
        </div>
      ),
    },
    {
      category: 'getting-started',
      question: 'What is a Playbook and do I need one?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            A <strong>Playbook</strong> defines preprocessing strategies, chunking rules, and quality controls 
            tailored to specific content types (e.g., TECH, REGULATORY, FINANCE).
          </p>
          <p className="text-gray-700">
            <strong>You can:</strong>
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li>Let AIRDOps auto-detect the best playbook based on your content</li>
            <li>Manually select a playbook during product creation</li>
            <li>Use the default playbook if none is specified</li>
          </ul>
          <p className="text-gray-700">
            Playbooks enable AI-Ready metrics (Chunk Coherence, Noise-Free Score) which provide deeper insights 
            into your data quality.
          </p>
        </div>
      ),
    },
    {
      category: 'getting-started',
      question: 'How long does the pipeline take to run?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            Pipeline duration depends on several factors:
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>Data volume:</strong> Number of files and total content size</li>
            <li><strong>Embedding model:</strong> Large models (1024+ dimensions) take longer than smaller ones</li>
            <li><strong>Vector creation:</strong> If enabled, embedding generation is the longest step</li>
          </ul>
          <p className="text-gray-700">
            <strong>Typical times:</strong>
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li>Small datasets (&lt;100 files): 5-15 minutes</li>
            <li>Medium datasets (100-1000 files): 15-60 minutes</li>
            <li>Large datasets (1000+ files): 1-4 hours (with vector creation)</li>
          </ul>
          <p className="text-gray-700 text-sm bg-blue-50 p-3 rounded-lg border border-blue-200">
            <strong>💡 Tip:</strong> For faster processing, use smaller embedding models (e.g., minilm) or disable 
            vector creation if you only need quality metrics.
          </p>
        </div>
      ),
    },
    // Features
    {
      category: 'features',
      question: 'What data sources can I connect?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">AIRDOps supports multiple data source types:</p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>Web:</strong> Websites, documentation sites, blogs</li>
            <li><strong>Database:</strong> SQL databases (PostgreSQL, MySQL, etc.)</li>
            <li><strong>Confluence:</strong> Atlassian Confluence spaces and pages</li>
            <li><strong>SharePoint:</strong> Microsoft SharePoint sites and document libraries</li>
            <li><strong>Folder:</strong> Local or network file system folders</li>
          </ul>
          <p className="text-gray-700">
            Each data source type has specific configuration options. Navigate to your product → 
            Data Sources tab → Add Data Source to see available options.
          </p>
        </div>
      ),
    },
    {
      category: 'features',
      question: 'What is the difference between vector-enabled and non-vector-enabled products?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            <strong>Vector-Enabled Products:</strong>
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li>Generate embeddings for semantic search</li>
            <li>Store vectors in the vector database for retrieval</li>
            <li>Calculate Vector Metrics (5 metrics) and RAG Performance Metrics (3 metrics)</li>
            <li>Enable semantic search in the Playground</li>
            <li>Require more processing time and storage</li>
          </ul>
          <p className="text-gray-700 mt-3">
            <strong>Non-Vector-Enabled Products:</strong>
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li>Calculate Base Trust Metrics (14 metrics) and AI-Ready Metrics (5 metrics)</li>
            <li>Faster processing (no embedding generation)</li>
            <li>Lower storage requirements</li>
            <li>Ideal for quality assessment without semantic search needs</li>
          </ul>
          <p className="text-gray-700 text-sm bg-yellow-50 p-3 rounded-lg border border-yellow-200 mt-3">
            <strong>Note:</strong> You can enable/disable vector creation in product settings. 
            Vector metrics will show "Not Evaluated" when disabled.
          </p>
        </div>
      ),
    },
    {
      category: 'features',
      question: 'How do I improve my AI Trust Score?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            The AI Trust Score is a weighted composite of all quality metrics. To improve it:
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>Review Optimization Suggestions:</strong> Check the AI Trust Score tab for actionable recommendations</li>
            <li><strong>Apply Recommendations:</strong> Click "Apply" on suggestions like "Increase Overlap" or "Extract Metadata"</li>
            <li><strong>Improve Data Quality:</strong> Ensure your source data is clean, well-structured, and complete</li>
            <li><strong>Add Metadata:</strong> Include section, field_name, and document_id in your data</li>
            <li><strong>Remove PII:</strong> Clean sensitive information before ingestion</li>
            <li><strong>Optimize Chunking:</strong> Adjust chunk size and overlap based on recommendations</li>
            <li><strong>Re-run Pipeline:</strong> After making changes, run the pipeline again to see updated scores</li>
          </ul>
        </div>
      ),
    },
    {
      category: 'features',
      question: 'What is the Playground feature?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            The <strong>Playground</strong> allows you to test semantic search on your indexed data. 
            It's available for products with vector creation enabled.
          </p>
          <p className="text-gray-700">
            <strong>Features:</strong>
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li>Test queries against your indexed data</li>
            <li>See retrieval results with relevance scores</li>
            <li>Compare different embedding models</li>
            <li>Validate RAG performance before production use</li>
          </ul>
          <p className="text-gray-700">
            Access it from: Product → Playground tab (only visible for vector-enabled products).
          </p>
        </div>
      ),
    },
    // Metrics
    {
      category: 'metrics',
      question: 'What metrics are available and what do they mean?',
      answer: (
        <div className="space-y-4">
          <p className="text-gray-700">
            AIRDOps provides <strong>26 comprehensive metrics</strong> organized into 5 categories. 
            All metrics are scored on a 0-100 scale, where higher scores indicate better quality.
          </p>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
            <p className="text-sm text-blue-800">
              <strong>💡 Beginner Tip:</strong> These metrics work together like a quality checklist. 
              Each metric checks a different aspect of your data. Higher scores across all metrics = better AI performance. 
              Focus on metrics below 70% first, as they have the biggest impact on quality.
            </p>
          </div>
          <div className="space-y-6">
            {Object.entries(METRIC_CATEGORIES).map(([catKey, catConfig]) => {
              const Icon = catConfig.icon
              return (
                <div key={catKey} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Icon className="h-5 w-5 text-blue-600" />
                    <h4 className="font-semibold text-gray-900">{catConfig.name}</h4>
                  </div>
                  {catConfig.note && (
                    <p className="text-sm text-amber-600 bg-amber-50 p-2 rounded mb-3 border border-amber-200">
                      <Info className="h-4 w-4 inline mr-1" />
                      {catConfig.note}
                    </p>
                  )}
                  <div className="space-y-3">
                    {catConfig.metrics.map((metric) => (
                      <div key={metric.key} className="border-l-2 border-gray-200 pl-3">
                        <h5 className="font-medium text-gray-900">{metric.name}</h5>
                        <p className="text-sm text-gray-600 mt-1">{metric.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ),
    },
    {
      category: 'metrics',
      question: 'How do these metrics help determine vector quality and search accuracy?',
      answer: (
        <div className="space-y-4">
          <p className="text-gray-700">
            All 26 metrics work together to ensure your data creates high-quality vectors that produce accurate search results. 
            Here's how they connect:
          </p>
          
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg p-4">
            <h4 className="font-semibold text-gray-900 mb-3">The Vector Quality Chain</h4>
            <ol className="list-decimal list-inside space-y-2 text-gray-700">
              <li><strong>Base Quality (Governance & Content Metrics):</strong> Clean, accurate, complete content creates better embeddings. If your text has errors, missing information, or poor structure, the AI model creates poor embeddings.</li>
              <li><strong>Chunking Quality:</strong> Well-structured chunks (coherent, noise-free, good boundaries) ensure each embedding represents a complete, focused topic. Poor chunking creates confusing embeddings.</li>
              <li><strong>Vector Quality:</strong> Valid, consistent embeddings with proper dimensions ensure the math behind similarity search works correctly. Broken vectors = broken search.</li>
              <li><strong>RAG Performance:</strong> High recall and precision mean your search actually finds and ranks relevant content correctly, leading to accurate AI responses.</li>
            </ol>
          </div>

          <div className="space-y-3">
            <div className="border-l-4 border-green-500 pl-4">
              <h5 className="font-semibold text-gray-900 mb-2">Example: Why Low Accuracy Breaks Vector Search</h5>
              <p className="text-gray-700 text-sm">
                If your <strong>Accuracy</strong> metric is 40% (lots of typos), the embedding model sees "authenitcation" instead of "authentication". 
                When a user searches for "authentication", the system won't find chunks with typos because the embeddings are different. 
                This directly impacts <strong>Retrieval Recall</strong> - users won't find relevant content.
              </p>
            </div>

            <div className="border-l-4 border-blue-500 pl-4">
              <h5 className="font-semibold text-gray-900 mb-2">Example: How Chunk Coherence Affects Search</h5>
              <p className="text-gray-700 text-sm">
                If <strong>Chunk Coherence</strong> is 50% (chunks mix topics), a chunk might contain both "API authentication" and "billing information". 
                When a user searches for "authentication", they might get results that also include billing info, leading to confusing answers. 
                This hurts <strong>Average Precision</strong> because results aren't focused.
              </p>
            </div>

            <div className="border-l-4 border-purple-500 pl-4">
              <h5 className="font-semibold text-gray-900 mb-2">Example: Vector Dimension Consistency is Critical</h5>
              <p className="text-gray-700 text-sm">
                If <strong>Embedding Dimension Consistency</strong> is 95% (some vectors are wrong size), the vector database can't compare vectors properly. 
                The search system breaks because you can't calculate similarity between vectors of different sizes. 
                This makes <strong>Semantic Search Readiness</strong> drop, and search becomes unreliable.
              </p>
            </div>
          </div>

          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-sm text-yellow-800">
              <strong>🎯 Key Takeaway:</strong> Every metric impacts vector quality. Low scores in any category can break your search. 
              Aim for 70%+ across all metrics for reliable AI applications. The <strong>Semantic Search Readiness</strong> and 
              <strong> Knowledge Base Ready</strong> composite scores give you an overall health check.
            </p>
          </div>
        </div>
      ),
    },
    {
      category: 'metrics',
      question: 'Why do some metrics show "Not Evaluated"?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            Some metrics require specific configurations to be calculated:
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>Vector Metrics (5) & RAG Metrics (3):</strong> Only available when <code className="bg-gray-100 px-1 rounded">vector_creation_enabled = true</code>. Enable vector creation in product settings to see these metrics.</li>
            <li><strong>AI-Ready Metrics (Chunk Coherence, Noise-Free Score):</strong> Require a playbook with <code className="bg-gray-100 px-1 rounded">coherence</code> and <code className="bg-gray-100 px-1 rounded">noise_patterns</code> sections. Most playbooks include these by default.</li>
            <li><strong>Chunk Boundary Quality:</strong> Requires preprocessing statistics. This is automatically calculated during the preprocessing stage.</li>
          </ul>
          <p className="text-gray-700 text-sm bg-blue-50 p-3 rounded-lg border border-blue-200 mt-3">
            <strong>💡 Tip:</strong> To see all 26 metrics, ensure vector creation is enabled and a playbook is selected for your product.
          </p>
        </div>
      ),
    },
    {
      category: 'metrics',
      question: 'What is a good AI Trust Score?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            AI Trust Score interpretation:
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>80-100% (Excellent):</strong> Ready for AI use. Your data is high-quality and well-structured.</li>
            <li><strong>60-79% (Good):</strong> Minor improvements recommended. Review optimization suggestions for quick wins.</li>
            <li><strong>40-59% (Needs Improvement):</strong> Significant enhancements required. Focus on data quality and structure.</li>
            <li><strong>0-39% (Poor):</strong> Major issues detected. Review violations and apply recommended fixes.</li>
          </ul>
          <p className="text-gray-700 text-sm bg-green-50 p-3 rounded-lg border border-green-200 mt-3">
            <strong>📊 Industry Standard:</strong> Organizations achieving &gt;85% quality scores see <strong>4x efficiency gains</strong> 
            in AI applications compared to 70-85% quality data.
          </p>
        </div>
      ),
    },
    {
      category: 'metrics',
      question: 'How are metrics calculated?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            Metrics are calculated during the pipeline execution:
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>Base Trust Metrics:</strong> Calculated in the Scoring stage using heuristics and optional advanced libraries (textstat, spellchecker)</li>
            <li><strong>AI-Ready Metrics:</strong> Calculated in the Scoring stage using playbook configurations (coherence analysis, noise detection)</li>
            <li><strong>Vector Metrics:</strong> Calculated in the Indexing stage by analyzing embedding quality, dimension consistency, and model health</li>
            <li><strong>RAG Metrics:</strong> Calculated in the Indexing stage using self-retrieval evaluation (testing if chunks can retrieve themselves)</li>
          </ul>
          <p className="text-gray-700">
            All metrics are aggregated from chunk-level to product-level in the Fingerprint stage, 
            creating your readiness fingerprint.
          </p>
        </div>
      ),
    },
    {
      category: 'metrics',
      question: 'How are RAG Performance metrics calculated?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            RAG Performance metrics are calculated during the Indexing stage using <strong>self-retrieval evaluation</strong>:
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>Retrieval Recall@K:</strong> For each chunk, the first sentence is embedded and used as a query. The system searches for the top K results and checks if the original chunk appears in those results. Recall@K = (number of chunks that successfully retrieved themselves) / (total chunks evaluated) × 100%</li>
            <li><strong>Average Precision@K:</strong> For each successful retrieval, precision is calculated based on the position of the correct chunk in the results. Higher positions (rank 1, 2, 3) contribute more to precision. The average across all queries gives the final score.</li>
          </ul>
          <p className="text-gray-700 text-sm bg-blue-50 p-3 rounded-lg border border-blue-200 mt-3">
            <strong>💡 Note:</strong> These metrics evaluate how well your indexed data can retrieve itself, which is a proxy for how well it will perform in real RAG applications. Higher scores indicate better retrieval accuracy and ranking quality.
          </p>
        </div>
      ),
    },
    {
      category: 'metrics',
      question: "What's the difference between RAG Performance metrics and similarity scores?",
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            These are two different types of measurements:
          </p>
          <div className="space-y-3">
            <div>
              <p className="text-gray-700 font-semibold mb-1">RAG Performance Metrics (Retrieval Recall@K, Average Precision@K):</p>
              <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
                <li><strong>Purpose:</strong> Evaluate overall system performance and data quality</li>
                <li><strong>When calculated:</strong> During the Indexing stage, using self-retrieval evaluation</li>
                <li><strong>What they measure:</strong> How often chunks can retrieve themselves and how well they rank</li>
                <li><strong>Scope:</strong> Product-level metrics that assess your entire dataset</li>
                <li><strong>Display:</strong> Shown in the AI Trust Score tab under "RAG Performance"</li>
              </ul>
            </div>
            <div>
              <p className="text-gray-700 font-semibold mb-1">Similarity Scores (e.g., 49.8%, 72.3%):</p>
              <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
                <li><strong>Purpose:</strong> Show relevance of individual search results to a specific query</li>
                <li><strong>When calculated:</strong> In real-time when you search in the RAG Playground</li>
                <li><strong>What they measure:</strong> Cosine similarity between the query embedding and each result's embedding (0-100% scale)</li>
                <li><strong>Scope:</strong> Per-query, per-result scores for individual searches</li>
                <li><strong>Display:</strong> Shown next to each result in the Playground search results</li>
              </ul>
            </div>
          </div>
          <p className="text-gray-700 text-sm bg-green-50 p-3 rounded-lg border border-green-200 mt-3">
            <strong>📊 In Summary:</strong> RAG Performance metrics tell you "Is my data good for RAG?" while similarity scores tell you "How relevant is this specific result to my query?"
          </p>
        </div>
      ),
    },
    {
      category: 'metrics',
      question: "What does 'AI-ready' mean and how does AIRDOps make my data AI-ready?",
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            <strong>"AI-ready"</strong> means your data is prepared, optimized, and validated for use in AI applications like RAG (Retrieval-Augmented Generation), chatbots, and knowledge bases.
          </p>
          <p className="text-gray-700">
            AIRDOps makes your data AI-ready through a comprehensive pipeline:
          </p>
          <ol className="list-decimal list-inside space-y-2 text-gray-700 ml-4">
            <li><strong>Data Ingestion & Preprocessing:</strong> Extracts content from various sources, normalizes text, removes noise, and structures data for processing</li>
            <li><strong>Intelligent Chunking:</strong> Splits content into optimal-sized chunks (around 900 tokens) with proper boundaries, maintaining semantic coherence within each chunk</li>
            <li><strong>Quality Scoring:</strong> Calculates 19 quality metrics covering governance, content quality, and chunking structure to identify issues and areas for improvement</li>
            <li><strong>Vector Embedding (if enabled):</strong> Converts text chunks into high-dimensional vectors using embedding models, enabling semantic search</li>
            <li><strong>Vector Database Storage:</strong> Stores embeddings in Qdrant with metadata for fast, accurate retrieval</li>
            <li><strong>RAG Evaluation:</strong> Tests retrieval performance using self-retrieval to ensure your data will work well in production RAG systems</li>
            <li><strong>Optimization Recommendations:</strong> Provides actionable suggestions to improve chunk size, overlap, metadata extraction, and other parameters</li>
          </ol>
          <p className="text-gray-700 text-sm bg-purple-50 p-3 rounded-lg border border-purple-200 mt-3">
            <strong>🎯 Result:</strong> Your data is cleaned, chunked, embedded, indexed, and validated - ready to power AI applications with high-quality, relevant search results and accurate responses.
          </p>
        </div>
      ),
    },
    // Troubleshooting
    {
      category: 'troubleshooting',
      question: 'My pipeline failed. What should I do?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            If your pipeline fails, follow these steps:
          </p>
          <ol className="list-decimal list-inside space-y-2 text-gray-700 ml-4">
            <li><strong>Check Pipeline Runs:</strong> Go to your product → Overview tab → View recent pipeline runs to see error messages</li>
            <li><strong>Review Error Details:</strong> Click on the failed run to see detailed error information</li>
            <li><strong>Common Issues:</strong>
              <ul className="list-disc list-inside ml-6 mt-1 space-y-1">
                <li>Data source connection issues (check credentials and permissions)</li>
                <li>Vector database connection problems (ensure the vector database service is running)</li>
                <li>Embedding model errors (check API keys for OpenAI models)</li>
                <li>Storage issues (check S3/MinIO configuration)</li>
              </ul>
            </li>
            <li><strong>Contact Support:</strong> If the issue persists, use the Support tab below to report the problem with error details</li>
          </ol>
        </div>
      ),
    },
    {
      category: 'troubleshooting',
      question: 'Why are my vector metrics showing 0% or "Not Evaluated"?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            Vector metrics show "Not Evaluated" when:
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-700 ml-4">
            <li><strong>Vector creation is disabled:</strong> Check product settings → ensure <code className="bg-gray-100 px-1 rounded">vector_creation_enabled</code> is set to <code className="bg-gray-100 px-1 rounded">true</code></li>
            <li><strong>Indexing stage was skipped:</strong> The DAG automatically skips indexing when vector creation is disabled</li>
            <li><strong>Indexing failed:</strong> Check pipeline runs for indexing stage errors</li>
            <li><strong>No vectors were created:</strong> All embedding attempts may have failed (check logs)</li>
          </ul>
          <p className="text-gray-700 text-sm bg-blue-50 p-3 rounded-lg border border-blue-200 mt-3">
            <strong>Solution:</strong> Enable vector creation in product settings and re-run the pipeline. 
            Vector metrics will be calculated during the indexing stage.
          </p>
        </div>
      ),
    },
    {
      category: 'troubleshooting',
      question: 'How do I change my embedding model?',
      answer: (
        <div className="space-y-2">
          <p className="text-gray-700">
            To change your embedding model:
          </p>
          <ol className="list-decimal list-inside space-y-2 text-gray-700 ml-4">
            <li>Go to your product → Settings tab (or Edit Product)</li>
            <li>Update the <code className="bg-gray-100 px-1 rounded">embedding_config</code>:
              <ul className="list-disc list-inside ml-6 mt-1 space-y-1">
                <li><code className="bg-gray-100 px-1 rounded">embedder_name</code>: Model name (e.g., "minilm", "text-embedding-3-small")</li>
                <li><code className="bg-gray-100 px-1 rounded">embedding_dimension</code>: Model dimension (e.g., 384, 768, 1536)</li>
              </ul>
            </li>
            <li>Save the changes</li>
            <li>Re-run the pipeline to generate new embeddings with the updated model</li>
          </ol>
          <p className="text-gray-700 text-sm bg-yellow-50 p-3 rounded-lg border border-yellow-200 mt-3">
            <strong>⚠️ Important:</strong> Changing the embedding model will require re-indexing all data. 
            This may take significant time for large datasets.
          </p>
        </div>
      ),
    },
  ]

  const categories = [
    { id: 'getting-started', name: 'Getting Started', icon: Play },
    { id: 'features', name: 'Features & Usage', icon: Sparkles },
    { id: 'metrics', name: 'Metrics Explained', icon: BarChart3 },
    { id: 'troubleshooting', name: 'Troubleshooting', icon: HelpCircle },
  ]

  const filteredItems = activeCategory 
    ? faqItems.filter(item => item.category === activeCategory)
    : faqItems

  return (
    <AppLayout>
      <div className="p-6 bg-gradient-to-br from-gray-50 via-blue-50/30 to-indigo-50/30 min-h-screen">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg">
                <HelpCircle className="h-8 w-8 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900">Help & Support</h1>
                <p className="text-gray-600 mt-1">Find answers to common questions or contact our support team</p>
              </div>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="mb-8">
            <div className="flex gap-2 border-b border-gray-200">
              <button
                onClick={() => setActiveTab('faq')}
                className={`px-6 py-3 font-medium transition-colors border-b-2 ${
                  activeTab === 'faq'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <div className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4" />
                  FAQ
                </div>
              </button>
              <button
                onClick={() => {
                  setActiveTab('support')
                  setTimeout(() => {
                    const element = document.getElementById('contact-support')
                    if (element) {
                      element.scrollIntoView({ behavior: 'smooth' })
                    }
                  }, 100)
                }}
                className={`px-6 py-3 font-medium transition-colors border-b-2 ${
                  activeTab === 'support'
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4" />
                  Contact Support
                </div>
              </button>
            </div>
          </div>

          {/* FAQ Tab Content */}
          {activeTab === 'faq' && (
            <div>
              {/* Category Filter */}
              <div className="mb-8">
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => setActiveCategory(null)}
                    className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                      activeCategory === null
                        ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white'
                        : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
                    }`}
                  >
                    All Questions
                  </button>
                  {categories.map((cat) => {
                    const Icon = cat.icon
                    return (
                      <button
                        key={cat.id}
                        onClick={() => setActiveCategory(cat.id)}
                        className={`px-4 py-2 rounded-lg font-medium transition-colors flex items-center gap-2 ${
                          activeCategory === cat.id
                            ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white'
                            : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {cat.name}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Quick Start Guide */}
              {activeCategory === null || activeCategory === 'getting-started' ? (
                <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-8">
                  <h2 className="text-xl font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <Play className="h-5 w-5 text-blue-600" />
                    Quick Start Guide
                  </h2>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                          <span className="text-blue-600 font-bold">1</span>
                        </div>
                        <h3 className="font-semibold text-gray-900">Create Product</h3>
                      </div>
                      <p className="text-sm text-gray-600">Go to Products → New Product. Name it and optionally select a playbook.</p>
                    </div>
                    <div className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                          <span className="text-blue-600 font-bold">2</span>
                        </div>
                        <h3 className="font-semibold text-gray-900">Add Data Sources</h3>
                      </div>
                      <p className="text-sm text-gray-600">Connect your data (web, database, Confluence, SharePoint, or folder).</p>
                    </div>
                    <div className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                          <span className="text-blue-600 font-bold">3</span>
                        </div>
                        <h3 className="font-semibold text-gray-900">Run Pipeline</h3>
                      </div>
                      <p className="text-sm text-gray-600">Click "Run Pipeline" to process your data and generate metrics.</p>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* FAQ Items */}
              <div className="space-y-4">
                {filteredItems.map((item, index) => {
                  const itemId = `${item.category}-${index}`
                  const isExpanded = expandedItems.has(itemId)
                  return (
                    <div
                      key={itemId}
                      className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden"
                    >
                      <button
                        onClick={() => toggleItem(itemId)}
                        className="w-full px-6 py-4 flex items-center justify-between text-left hover:bg-gray-50 transition-colors"
                      >
                        <span className="font-semibold text-gray-900 pr-4">{item.question}</span>
                        {isExpanded ? (
                          <ChevronUp className="h-5 w-5 text-gray-400 flex-shrink-0" />
                        ) : (
                          <ChevronDown className="h-5 w-5 text-gray-400 flex-shrink-0" />
                        )}
                      </button>
                      {isExpanded && (
                        <div className="px-6 pb-4 pt-0 border-t border-gray-100">
                          <div className="pt-4 text-gray-700">{item.answer}</div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* Metrics Reference Section */}
              {activeCategory === null || activeCategory === 'metrics' ? (
                <div className="mt-12 bg-white rounded-xl shadow-sm border border-gray-200 p-8">
                  <h2 className="text-2xl font-semibold text-gray-900 mb-6 flex items-center gap-2">
                    <BarChart3 className="h-6 w-6 text-blue-600" />
                    Complete Metrics Reference
                  </h2>
                  <p className="text-gray-600 mb-6">
                    AIRDOps provides 26 comprehensive metrics organized into 5 categories. 
                    All metrics are scored on a 0-100 scale, where higher scores indicate better quality.
                  </p>
                  
                  <div className="space-y-6">
                    {Object.entries(METRIC_CATEGORIES).map(([catKey, catConfig]) => {
                      const Icon = catConfig.icon
                      const isExpanded = expandedItems.has(`metric-category-${catKey}`)
                      return (
                        <div key={catKey} className="border-2 border-gray-200 rounded-xl overflow-hidden">
                          <button
                            onClick={() => toggleItem(`metric-category-${catKey}`)}
                            className="w-full px-6 py-4 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                          >
                            <div className="flex items-center gap-3">
                              <Icon className="h-5 w-5 text-blue-600" />
                              <h3 className="text-lg font-semibold text-gray-900">{catConfig.name}</h3>
                              <span className="text-sm text-gray-500">({catConfig.metrics.length} metrics)</span>
                            </div>
                            {isExpanded ? (
                              <ChevronUp className="h-5 w-5 text-gray-400" />
                            ) : (
                              <ChevronDown className="h-5 w-5 text-gray-400" />
                            )}
                          </button>
                          {isExpanded && (
                            <div className="p-6 bg-white">
                              {catConfig.note && (
                                <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                                  <p className="text-sm text-amber-800 flex items-start gap-2">
                                    <Info className="h-4 w-4 mt-0.5 flex-shrink-0" />
                                    <span>{catConfig.note}</span>
                                  </p>
                                </div>
                              )}
                              <div className="grid md:grid-cols-2 gap-4">
                                {catConfig.metrics.map((metric) => (
                                  <div key={metric.key} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                                    <h4 className="font-semibold text-gray-900 mb-2">{metric.name}</h4>
                                    <p className="text-sm text-gray-600">{metric.description}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ) : null}

              {/* Still Need Help */}
              <div className="mt-12 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl border border-blue-200 p-6">
                <div className="flex items-start gap-4">
                  <HelpCircle className="h-6 w-6 text-blue-600 flex-shrink-0 mt-1" />
                  <div>
                    <h3 className="font-semibold text-gray-900 mb-2">Still Need Help?</h3>
                    <p className="text-gray-700 mb-3">
                      Can't find the answer you're looking for? Our support team is here to help.
                    </p>
                    <button
                      onClick={() => {
                        setActiveTab('support')
                        setTimeout(() => {
                          const element = document.getElementById('contact-support')
                          if (element) {
                            element.scrollIntoView({ behavior: 'smooth' })
                          }
                        }, 100)
                      }}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
                    >
                      Contact Support
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Support Tab Content */}
          {activeTab === 'support' && (
            <div id="contact-support">
              <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8 md:p-12">
                {/* Header */}
                <div className="text-center mb-8">
                  <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-full mb-4">
                    <MessageSquare className="h-8 w-8 text-white" />
                  </div>
                  <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-3">
                    Contact Support
                  </h2>
                  <p className="text-gray-600 text-lg">
                    Need help? Have a question or feedback? We're here to assist you!
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

                {/* Support Form */}
                <form onSubmit={handleSubmit} className="space-y-6">
                  {/* Name Field - Pre-populated, readonly */}
                  <div>
                    <Label htmlFor="name" className="text-gray-700 font-medium">
                      Name <span className="text-red-500">*</span>
                    </Label>
                    <Input
                      id="name"
                      type="text"
                      value={formData.name}
                      readOnly
                      className={`mt-1 bg-gray-50 cursor-not-allowed ${errors.name ? 'border-red-500' : ''}`}
                      placeholder="Your full name"
                      disabled={submitting}
                      required
                    />
                    {errors.name && (
                      <p className="mt-1 text-sm text-red-600">{errors.name}</p>
                    )}
                  </div>

                  {/* Email Field - Pre-populated, readonly */}
                  <div>
                    <Label htmlFor="email" className="text-gray-700 font-medium">
                      Email <span className="text-red-500">*</span>
                    </Label>
                    <Input
                      id="email"
                      type="email"
                      value={formData.email}
                      readOnly
                      className={`mt-1 bg-gray-50 cursor-not-allowed ${errors.email ? 'border-red-500' : ''}`}
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
                      className={`mt-1 min-h-[200px] ${errors.feedback ? 'border-red-500 focus:ring-red-500' : ''}`}
                      placeholder="Tell us about your question, issue, feedback, or any problem you're experiencing..."
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
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  )
}

