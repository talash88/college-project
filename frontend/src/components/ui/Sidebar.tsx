'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { getNavForRole } from '@/lib/navigation';

function isRouteActive(pathname: string, href: string): boolean {
  if (pathname === href) return true;
  if (href === '/dashboard') return false;
  if (href === '/problems') {
    // My Reports stays active on the report detail page, but not on the
    // report form or the team workspace (those have their own context).
    return /^\/problems\/[^/]+$/.test(pathname);
  }
  // Highlight section roots for nested routes, without cross-matching
  // siblings (e.g. /problems/new must not activate /problems).
  return pathname.startsWith(`${href}/`);
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { user } = useAuth();
  const sections = getNavForRole(user?.role ?? null);

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-50 w-64 max-w-[85vw] bg-white border-r border-secondary-200 flex flex-col transform transition-transform duration-200 ${
        open ? 'translate-x-0 visible' : '-translate-x-full invisible lg:visible'
      } lg:translate-x-0`}
      aria-label="Sidebar navigation"
    >
      <div className="flex h-16 items-center justify-between px-4 sm:px-6 border-b border-secondary-200 flex-shrink-0">
        <Link href="/dashboard" className="flex items-center gap-2 min-w-0" onClick={onClose}>
          <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <span className="text-base sm:text-lg font-semibold text-primary-900 whitespace-nowrap truncate">
            CampusXolve AI
          </span>
        </Link>
        <button
          className="lg:hidden p-2 -mr-1 rounded-lg hover:bg-secondary-100 min-w-[2.75rem] min-h-[2.75rem] flex items-center justify-center"
          aria-label="Close sidebar"
          onClick={onClose}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto" aria-label="Main navigation">
        {sections.map((section) => (
          <div key={section.title} className="space-y-1">
            {section.title && (
              <h3 className="px-3 text-xs font-semibold text-secondary-400 uppercase tracking-wider mb-2">
                {section.title}
              </h3>
            )}
            <ul className="space-y-1" role="list">
              {section.items.map((item) => {
                const active = item.enabled && isRouteActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    {item.enabled ? (
                      <Link
                        href={item.href}
                        onClick={onClose}
                        className={`sidebar-link ${active ? 'sidebar-link-active' : ''}`}
                        aria-current={active ? 'page' : undefined}
                      >
                        <span className="w-5 h-5 flex-shrink-0" aria-hidden="true">
                          {item.icon}
                        </span>
                        {item.label}
                      </Link>
                    ) : (
                      <button
                        className="sidebar-link sidebar-link-disabled w-full text-left"
                        disabled
                        aria-disabled="true"
                      >
                        <span className="w-5 h-5 flex-shrink-0 opacity-50" aria-hidden="true">
                          {item.icon}
                        </span>
                        {item.label}
                        <span className="ml-auto text-xs text-secondary-400">Soon</span>
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="p-4 border-t border-secondary-200 flex-shrink-0">
        <div className="text-xs text-secondary-500 text-center">
          CampusXolve AI v0.1.0
        </div>
      </div>
    </aside>
  );
}
