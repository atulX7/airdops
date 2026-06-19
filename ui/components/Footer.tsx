'use client'

import Link from 'next/link'
import { Mail, FileText, Shield, HelpCircle } from 'lucide-react'

export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="bg-gradient-to-br from-slate-900 via-blue-900 to-indigo-900 text-white">
      <div className="container mx-auto px-4 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 mb-8">
          {/* Brand Section */}
          <div className="lg:col-span-1">
            <Link 
              href="/" 
              className="block mb-4"
              aria-label="Go to AIRDOps homepage"
            >
              <h3 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent hover:from-blue-300 hover:to-indigo-300 transition-all duration-200 cursor-pointer">
                AIRDOps
              </h3>
            </Link>
            <p className="text-gray-300 text-sm leading-relaxed mb-4">
              Making Data AI-Ready. Transform your data into production-ready AI assets with enterprise-grade processing and validation.
            </p>
          </div>

          {/* Product Links */}
          <div>
            <h4 className="text-lg font-semibold mb-4 text-white">Product</h4>
            <ul className="space-y-3">
              <li>
                <Link href="/features" className="text-gray-300 hover:text-white transition-colors text-sm inline-flex items-center">
                  <span>Features</span>
                </Link>
              </li>
              <li>
                <Link href="/pricing" className="text-gray-300 hover:text-white transition-colors text-sm inline-flex items-center">
                  <span>Pricing</span>
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal & Support */}
          <div>
            <h4 className="text-lg font-semibold mb-4 text-white">Legal & Support</h4>
            <ul className="space-y-3">
              <li>
                <Link href="/terms" className="text-gray-300 hover:text-white transition-colors text-sm inline-flex items-center">
                  <FileText className="h-4 w-4 mr-2" />
                  <span>Terms & Conditions</span>
                </Link>
              </li>
              <li>
                <Link href="/privacy" className="text-gray-300 hover:text-white transition-colors text-sm inline-flex items-center">
                  <Shield className="h-4 w-4 mr-2" />
                  <span>Privacy Policy</span>
                </Link>
              </li>
              <li>
                <Link href="/contact" className="text-gray-300 hover:text-white transition-colors text-sm inline-flex items-center">
                  <Mail className="h-4 w-4 mr-2" />
                  <span>Support</span>
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="border-t border-gray-700 pt-8 mt-8">
          <div className="flex flex-col md:flex-row justify-between items-center space-y-4 md:space-y-0">
            <div className="text-gray-400 text-sm">
              © {currentYear} AIRDOps. All rights reserved.
            </div>
            <div className="flex flex-wrap justify-center md:justify-end gap-6 text-sm text-gray-400">
              <Link href="/terms" className="hover:text-white transition-colors">
                Terms
              </Link>
              <Link href="/privacy" className="hover:text-white transition-colors">
                Privacy
              </Link>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}

