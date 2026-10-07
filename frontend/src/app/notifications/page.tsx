'use client';

import { useCallback, useEffect, useState } from 'react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { NotificationRow } from '@/components/ui/NotificationBell';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { AppNotification, NotificationList } from '@/types/api';

const PAGE_SIZE = 20;

function NotificationsContent() {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(
    async (nextOffset: number, append: boolean) => {
      if (append) setLoadingMore(true);
      else {
        setLoading(true);
        setError(null);
      }
      try {
        const data = await apiClient.get<NotificationList>(
          `${API_ENDPOINTS.notifications.base}?unread_only=${unreadOnly}&limit=${PAGE_SIZE}&offset=${nextOffset}`
        );
        setItems((prev) => (append ? [...prev, ...data.items] : data.items));
        setTotal(data.total);
        setOffset(nextOffset);
      } catch (err) {
        if (!append) setError(getApiErrorMessage(err, 'Could not load notifications.'));
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [unreadOnly]
  );

  useEffect(() => {
    load(0, false);
  }, [load]);

  const markRead = async (id: string) => {
    try {
      await apiClient.patch(API_ENDPOINTS.notifications.markRead(id));
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
    } catch {
      setNotice('Could not mark the notification read.');
    }
  };

  const markAllRead = async () => {
    setNotice(null);
    try {
      const data = await apiClient.post<{ marked_read: number }>(API_ENDPOINTS.notifications.readAll);
      setItems((prev) => prev.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })));
      setNotice(`Marked ${data.marked_read} notification${data.marked_read === 1 ? '' : 's'} read.`);
    } catch (err) {
      setNotice(getApiErrorMessage(err, 'Could not mark all read.'));
    }
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">Notifications</h1>
            <p className="mt-1 text-secondary-600">
              {total} total · solution reviews, verification requests, assignments, and task updates.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-secondary-700">
              <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
              Unread only
            </label>
            <button type="button" onClick={markAllRead} className="btn-secondary px-4 py-2 text-sm">
              Mark all read
            </button>
          </div>
        </div>

        {notice && (
          <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
            {notice}
          </div>
        )}

        {loading ? (
          <div className="space-y-2" aria-label="Loading notifications">
            <div className="h-16 rounded-lg bg-secondary-100 animate-pulse" />
            <div className="h-16 rounded-lg bg-secondary-100 animate-pulse" />
            <div className="h-16 rounded-lg bg-secondary-100 animate-pulse" />
          </div>
        ) : error ? (
          <div className="card p-6 text-sm text-red-700" role="alert">
            {error}{' '}
            <button type="button" className="font-medium underline" onClick={() => load(0, false)}>
              Retry
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="card p-8 text-center">
            <p className="text-sm text-secondary-600">
              {unreadOnly ? 'No unread notifications. You are all caught up.' : 'No notifications yet.'}
            </p>
          </div>
        ) : (
          <>
            <ul className="card divide-y divide-secondary-100">
              {items.map((n) => (
                <li key={n.id} className="flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <NotificationRow notification={n} />
                  </div>
                  {n.read_at == null && (
                    <button
                      type="button"
                      onClick={() => markRead(n.id)}
                      className="mr-3 flex-shrink-0 text-xs font-medium text-primary-600 hover:text-primary-700"
                    >
                      Mark read
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {offset + PAGE_SIZE < total && (
              <button
                type="button"
                onClick={() => load(offset + PAGE_SIZE, true)}
                disabled={loadingMore}
                className="btn-secondary px-4 py-2 text-sm"
              >
                {loadingMore ? 'Loading…' : `Load more (${total - offset - PAGE_SIZE} remaining)`}
              </button>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function NotificationsPage() {
  return (
    <RequireAuth>
      <NotificationsContent />
    </RequireAuth>
  );
}
