'use client'

interface ComingSoonBadgeInlineProps {
  /**
   * Optional additional className for positioning/spacing
   * Default: "ml-2" (for navigation menus)
   */
  className?: string
}

/**
 * Inline "Coming Soon" badge component
 * 
 * Consistent badge styling for navigation menus and inline use.
 * Matches the design language of ComingSoonBadge component.
 * 
 * @example
 * ```tsx
 * // In navigation (default spacing)
 * <ComingSoonBadgeInline />
 * 
 * // With custom positioning
 * <ComingSoonBadgeInline className="absolute top-3 right-3" />
 * ```
 */
export function ComingSoonBadgeInline({ className = "ml-2" }: ComingSoonBadgeInlineProps) {
  return (
    <span className={`${className} inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 text-white shadow-sm flex-shrink-0`}>
      Coming Soon
    </span>
  )
}

