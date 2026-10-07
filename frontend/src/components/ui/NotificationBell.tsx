'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import type { AppNotification } from '@/types/api';

function timeAgo(value: string): string {
  const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(value).toLocaleDateString();
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const fetchUnread = useCallback(async () => {
    try {
      const data = await apiClient.get<{ unread_count: number }>(API_ENDPOINTS.notifications.unreadCount);
      setUnread(data.unread_count);
    } catch {
      // Bell degrades silently; the notifications page shows errors.
    }
  }, []);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<{ items: AppNotification[]; total: number }>(
        `${API_ENDPOINTS.notifications.base}?limit=8&offset=0`
      );
      setItems(data.items);
    } catch {
      setError('Could not load notifications.');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUnread();
    const timer = setInterval(fetchUnread, 30000);
    return () => clearInterval(timer);
  }, [fetchUnread]);

  useEffect(() => {
    if (open) fetchItems();
  }, [open, fetchItems]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    if (open) {
      document.addEventListener('mousedown', onClick);
      document.addEventListener('keydown', onKey);
    }
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open ]);

  const markRead = async (id: string) => {
    try {
      await apiClient.patch(API_ENDPOINTS.notifications.markRead(id));
      setItems((prev) =>
        prev == null ? prev : prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
      );
      fetchUnread();
    } catch {
      // non-blocking
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg hover:bg-secondary-100"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
      >
        <svg className="w-6 h-6 text-secondary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[20px] h-5 px-1 rounded-full bg-red-600 text-white text-xs font-bold flex items-center justify-center">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-lg border border-secondary-200 bg-white shadow-xl z-50">
          <div className="flex items-center justify-between px-4 py-3 border-b border-secondary-100">
            <h2 className="text-sm font-semibold text-secondary-900">Notifications</h2>
            <Link href="/notifications" onClick={() => setOpen(false)} className="text-xs font-medium text-primary-600 hover:text-primary-700">
              View all
            </Link>
          </div>
          {loading ? (
            <div className="p-4 space-y-2" aria-label="Loading notifications">
              <div className="h-12 rounded bg-secondary-100 animate-pulse" />
              <div className="h-12 rounded bg-secondary-100 animate-pulse" />
            </div>
          ) : error ? (
            <p className="p-4 text-sm text-red-600" role="alert">{error}</p>
          ) : items == null || items.length === 0 ? (
            <p className="p-4 text-sm text-secondary-600">No notifications yet.</p>
          ) : (
            <ul className="max-h-96 overflow-y-auto divide-y divide-secondary-100">
              {items.map((n) => (
                <li key={n.id}>
                  <NotificationRow notification={n} onOpen={() => { markRead(n.id); setOpen(false); }} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function NotificationRow({
  notification,
  onOpen,
}: {
  notification: AppNotification;
  onOpen?: () => void;
}) {
  const target = notification.problem_id ? `/problems/${notification.problem_id}` : '/notifications';
  return (
    <Link
      href={target}
      onClick={onOpen}
      className={`block px-4 py-3 hover:bg-secondary-50 ${notification.read_at == null ? 'bg-primary-50/50' : ''}`}
    >
      <div className="flex items-start gap-2">
        {notification.read_at == null && (
          <span className="mt-1.5 w-2 h-2 rounded-full bg-primary-600 flex-shrink-0" aria-label="Unread" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-secondary-900 truncate">{notification.title}</p>
          <p className="text-xs text-secondary-600 line-clamp-2">{notification.message}</p>
          <p className="mt-0.5 text-xs text-secondary-400">{timeAgo(notification.created_at)}</p>
        </div>
      </div>
    </Link>
  );
}
