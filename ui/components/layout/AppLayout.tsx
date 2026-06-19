'use client'

import { usePathname } from 'next/navigation'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { 
  Package, 
  Database, 
  BarChart3, 
  Settings, 
  Users, 
  Home,
  Menu,
  X,
  ChevronDown,
  CreditCard,
  Sparkles,
  ChevronLeft,
  Bell,
  Search,
  HelpCircle,
  Play,
  BookOpen
} from 'lucide-react'
import { ComingSoonBadgeInline } from '@/components/ui/coming-soon-badge-inline'
import { resetTour } from '@/components/Tour'

interface AppLayoutProps {
  children: React.ReactNode
}

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: Home },
  { name: 'Products', href: '/app/products', icon: Package },
  { name: 'Data Sources', href: '/app/datasources', icon: Database },
  { name: 'Analytics', href: '/app/analytics', icon: BarChart3 },
  { name: 'Billing', href: '/app/billing', icon: CreditCard },
  { name: 'Team', href: '/app/team', icon: Users, comingSoon: true },
  { name: 'Settings', href: '/app/settings', icon: Settings },
]

export default function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname()
  const visibleNavigation = navigation.filter((item) => item.name !== 'Billing' && item.name !== 'Team')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [helpMenuOpen, setHelpMenuOpen] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [betaBannerDismissed, setBetaBannerDismissed] = useState(() => {
    // Check localStorage to persist dismissal
    if (typeof window !== 'undefined') {
      return localStorage.getItem('betaBannerDismissed') === 'true'
    }
    return false
  })

  // Close user menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userMenuOpen) {
        const target = event.target as Element
        if (!target.closest('.user-menu')) {
          setUserMenuOpen(false)
        }
      }
      if (helpMenuOpen) {
        const target = event.target as Element
        if (!target.closest('.help-menu')) {
          setHelpMenuOpen(false)
        }
      }
    }

    if (userMenuOpen || helpMenuOpen) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [userMenuOpen, helpMenuOpen])

  const handleDismissBanner = () => {
    setBetaBannerDismissed(true)
    if (typeof window !== 'undefined') {
      localStorage.setItem('betaBannerDismissed', 'true')
    }
  }

  const localUser = {
    name: "Local User",
    email: "local@airdops.local",
  }

  // Get user initial from email (fallback to name if not available)
  const getUserInitial = () => {
    const email = localUser.email
    const name = localUser.name
    if (email) {
      return email.charAt(0).toUpperCase()
    }
    if (name) {
      return name.charAt(0).toUpperCase()
    }
    return 'U'
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-gray-50">
      {/* Professional Beta Release Banner */}
      {!betaBannerDismissed && (
        <div className="relative bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white shadow-lg">
          <div className="absolute inset-0 bg-black opacity-5"></div>
          <div className="relative flex items-center justify-center px-4 py-2.5">
            <div className="flex items-center space-x-3 max-w-7xl w-full">
              <div className="flex items-center space-x-2 flex-shrink-0">
                <div className="bg-white/20 backdrop-blur-sm rounded-full p-1.5">
                  <Sparkles className="h-4 w-4 text-white" />
                </div>
                <span className="text-xs font-bold tracking-wider uppercase bg-white/20 px-2 py-0.5 rounded">
                  Beta
                </span>
              </div>
              <p className="text-sm font-medium flex-1 text-center">
                You're using AIRDOps Beta. We're actively improving features and performance. 
                <span className="hidden sm:inline"> Your feedback helps us build better.</span>
              </p>
              <button
                onClick={handleDismissBanner}
                className="flex-shrink-0 p-1 rounded-md hover:bg-white/20 transition-colors focus:outline-none focus:ring-2 focus:ring-white/50"
                aria-label="Dismiss beta banner"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div 
            className="fixed inset-0 bg-gray-600 bg-opacity-75" 
            onClick={() => setSidebarOpen(false)} 
          />
        </div>
      )}

      {/* Enhanced Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 bg-white shadow-xl transform transition-all duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0 ${
        sidebarOpen ? 'translate-x-0' : '-translate-x-full'
      } ${sidebarCollapsed ? 'w-20 lg:w-20' : 'w-64'}`}>
        {/* Enhanced Sidebar header */}
        <div className="flex items-center justify-between h-16 px-4 border-b-2 border-gray-100 bg-gradient-to-r from-blue-50/50 to-indigo-50/50">
          {!sidebarCollapsed && (
            <div>
              <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                AIRDOps
              </h1>
              <p className="text-xs text-gray-500 mt-0.5">Making Data AI-Ready</p>
            </div>
          )}
          {sidebarCollapsed && (
            <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg flex items-center justify-center mx-auto">
              <span className="text-white font-bold text-sm">A</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="hidden lg:flex p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <ChevronLeft className={`h-4 w-4 transition-transform ${sidebarCollapsed ? 'rotate-180' : ''}`} />
            </button>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-2 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
              <X className="h-5 w-5" />
          </button>
          </div>
        </div>
        
        {/* Enhanced Navigation */}
        <nav data-tour="navigation-sidebar" className="mt-6 px-3">
          <div className="space-y-1">
            {visibleNavigation.map((item) => {
              const isActive = pathname.startsWith(item.href)
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`group flex items-center px-3 py-3 text-sm font-medium rounded-lg transition-all duration-200 ${
                    isActive
                      ? 'bg-gradient-to-r from-blue-50 to-indigo-50 text-blue-700 border-l-4 border-blue-600 shadow-sm'
                      : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                  onClick={() => setSidebarOpen(false)}
                  title={sidebarCollapsed ? item.name : undefined}
                >
                  <item.icon className={`h-5 w-5 flex-shrink-0 ${
                    isActive ? 'text-blue-600' : 'text-gray-400 group-hover:text-gray-600'
                  } ${sidebarCollapsed ? 'mx-auto' : 'mr-3'}`} />
                  {!sidebarCollapsed && (
                    <div className="flex items-center flex-1 min-w-0">
                      <span className="truncate">{item.name}</span>
                      {item.comingSoon && <ComingSoonBadgeInline />}
                    </div>
                  )}
                </Link>
              )
            })}
          </div>
        </nav>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Enhanced Top header */}
        <header className="bg-white shadow-md border-b-2 border-gray-100">
          <div className="flex items-center justify-between h-16 px-4 sm:px-6 lg:px-8">
            <div className="flex items-center flex-1">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              >
                <Menu className="h-6 w-6" />
              </button>
              <h2 className="ml-2 text-xl font-semibold text-gray-900">
                {visibleNavigation.find(item => item.href === pathname)?.name || 'AIRDOps'}
              </h2>
            </div>
            
            <div className="flex items-center space-x-3">
              {/* Take Tour Button */}
              {pathname === '/dashboard' && (
                <button
                  onClick={() => {
                    resetTour()
                    // Trigger tour by reloading or using a state management approach
                    if (typeof window !== 'undefined') {
                      window.dispatchEvent(new CustomEvent('startTour'))
                    }
                  }}
                  className="hidden md:flex items-center gap-2 px-3 py-2 text-sm font-medium text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 rounded-lg transition-colors border border-indigo-200 hover:border-indigo-300"
                  title="Take Product Tour"
                >
                  <Play className="h-4 w-4" />
                  <span>Take Tour</span>
                </button>
              )}
              
              {/* Search button (placeholder for future) */}
              <button
                className="hidden md:flex p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                aria-label="Search"
              >
                <Search className="h-5 w-5" />
              </button>
              
              {/* Notifications (placeholder) */}
              <button
                className="hidden md:flex relative p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                aria-label="Notifications"
              >
                <Bell className="h-5 w-5" />
                <span className="absolute top-1 right-1 h-2 w-2 bg-red-500 rounded-full"></span>
              </button>
              
              {/* Help menu */}
              <div className="relative help-menu">
                <button
                  onClick={() => setHelpMenuOpen(!helpMenuOpen)}
                  className="hidden md:flex p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                  aria-label="Help & Support"
                  title="Help & Support"
                >
                  <HelpCircle className="h-5 w-5" />
                </button>
                
                {helpMenuOpen && (
                  <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-xl border-2 border-gray-100 z-50 overflow-hidden">
                    <div className="py-2">
                      <Link
                        href="/app/help"
                        onClick={() => {
                          setHelpMenuOpen(false)
                          // Force hash update if already on help page
                          if (pathname === '/app/help' && typeof window !== 'undefined') {
                            window.location.hash = ''
                            window.dispatchEvent(new HashChangeEvent('hashchange'))
                          }
                        }}
                        className="flex items-center px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                      >
                        <BookOpen className="h-4 w-4 mr-3 text-gray-400" />
                        FAQ & Support
                      </Link>
                      <Link
                        href="/app/help#contact"
                        onClick={(e) => {
                          setHelpMenuOpen(false)
                          // If already on help page, manually update hash and trigger change
                          if (pathname === '/app/help' && typeof window !== 'undefined') {
                            e.preventDefault()
                            window.location.hash = 'contact'
                            window.dispatchEvent(new HashChangeEvent('hashchange'))
                          }
                        }}
                        className="flex items-center px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                      >
                        <HelpCircle className="h-4 w-4 mr-3 text-gray-400" />
                        Contact Support
                      </Link>
                    </div>
                  </div>
                )}
              </div>
              
                  {/* User menu */}
              <div className="relative user-menu">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center space-x-3 p-2 rounded-lg hover:bg-gray-100 transition-colors border-2 border-transparent hover:border-gray-200"
                >
                  <div className="h-9 w-9 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center ring-2 ring-gray-200">
                    <span className="text-white text-sm font-semibold">
                      {getUserInitial()}
                    </span>
                  </div>
                  <div className="hidden sm:block text-left">
                    <p className="text-sm font-semibold text-gray-900">{localUser.name}</p>
                    <p className="text-xs text-gray-500">{localUser.email}</p>
                  </div>
                  <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
                </button>
                
                {userMenuOpen && (
                  <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-xl border-2 border-gray-100 z-50 overflow-hidden">
                    <div className="py-2">
                      <div className="px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-gray-50 to-blue-50/30">
                        <p className="text-sm font-semibold text-gray-900">{localUser.name}</p>
                        <p className="text-xs text-gray-500 truncate">{localUser.email}</p>
                      </div>
                      <Link
                        href="/app/settings"
                        onClick={() => setUserMenuOpen(false)}
                        className="flex items-center px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                      >
                        <Settings className="h-4 w-4 mr-3 text-gray-400" />
                        Settings
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>

        {/* Footer */}
        <footer className="bg-white border-t border-gray-200 py-4">
          <div className="container mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center text-sm text-gray-500">
              © {new Date().getFullYear()} AIRDOps. All rights reserved.
            </div>
          </div>
        </footer>
      </div>
      </div>
    </div>
  )
}
