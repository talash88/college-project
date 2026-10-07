'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { NotificationBell } from '@/components/ui/NotificationBell';

export function Header({ menuOpen, onMenuToggle }: { menuOpen: boolean; onMenuToggle: () => void }) {
  const { connected, loading, refetch } = useBackendHealth();
  const { user, initializing, logout } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  return (
    <header className="fixed top-0 right-0 left-0 z-40 h-16 bg-white border-b border-secondary-200 lg:left-64">
      <div className="flex h-full items-center justify-between px-4 lg:px-6">
        <div className="flex items-center gap-4">
          <button
            className="lg:hidden p-2 rounded-lg hover:bg-secondary-100 min-w-[2.75rem] min-h-[2.75rem] flex items-center justify-center"
            onClick={onMenuToggle}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {menuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>

          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-secondary-50">
            <span
              className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : loading ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'}`}
              aria-hidden="true"
            />
            <span className="text-xs font-medium text-secondary-600">
              {loading ? 'Connecting...' : connected ? 'Backend Connected' : 'Backend Offline'}
            </span>
            <button
              onClick={refetch}
              disabled={loading}
              className="p-1 rounded hover:bg-secondary-100 disabled:opacity-50"
              aria-label="Refresh backend status"
            >
              <svg className="w-4 h-4 text-secondary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {initializing ? (
            <div className="hidden lg:block text-xs text-secondary-400">Loading session…</div>
          ) : user ? (
            <>
              <NotificationBell />
              <Link
                href="/profile"
                className="hidden sm:flex items-center gap-3 px-3 py-1.5 rounded-lg bg-secondary-50 hover:bg-secondary-100"
                title="View profile"
              >
                <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center">
                  <span className="text-sm font-semibold text-primary-700">
                    {user.full_name.charAt(0).toUpperCase()}
                  </span>
                </div>
                <span className="text-left">
                  <span className="block text-sm font-medium text-secondary-800 leading-tight">{user.full_name}</span>
                  <span className="block text-xs text-secondary-500 leading-tight">{user.role}</span>
                </span>
              </Link>
              <button onClick={handleLogout} className="btn-secondary text-sm px-3 py-1.5">
                Logout
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="text-sm font-medium text-primary-700 hover:text-primary-800">
                Login
              </Link>
              <Link href="/register" className="btn-primary text-sm px-3 py-1.5">
                Register
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
