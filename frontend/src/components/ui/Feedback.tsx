'use client';

import type { ReactNode } from 'react';

/** Small presentational badge. Color comes from the central status system. */
export function Badge({
  className = '',
  children,
  title,
}: {
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${className}`}
    >
      {children}
    </span>
  );
}

/** Card loading skeleton (avoids blank screens and layout jumps). */
export function LoadingSkeleton({ lines = 3, label = 'Loading…' }: { lines?: number; label?: string }) {
  return (
    <div className="card p-6" role="status" aria-live="polite" aria-label={label}>
      <div className="animate-pulse space-y-3">
        <div className="h-5 w-1/3 rounded bg-secondary-200" />
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="h-4 rounded bg-secondary-100" style={{ width: `${92 - i * 9}%` }} />
        ))}
      </div>
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Consistent empty state with an optional action. */
export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="card p-8 text-center">
      <div className="mx-auto w-11 h-11 rounded-full bg-secondary-100 flex items-center justify-center" aria-hidden="true">
        <svg className="w-5 h-5 text-secondary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
      </div>
      <h3 className="mt-3 text-base font-semibold text-secondary-900">{title}</h3>
      {message && <p className="mt-1 text-sm text-secondary-600">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Consistent error card with retry. Never renders backend tracebacks. */
export function ErrorState({
  message,
  onRetry,
  retryLabel = 'Retry',
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="card p-6" role="alert">
      <h3 className="text-base font-semibold text-secondary-900">Something went wrong</h3>
      <p className="mt-1 text-sm text-secondary-600">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary px-4 py-2 text-sm mt-4">
          {retryLabel}
        </button>
      )}
    </div>
  );
}

/** Standard table wrapper: horizontal scroll on small screens, hover rows. */
export function TableShell({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="card overflow-x-auto" role="region" aria-label={label} tabIndex={0}>
      <table className="min-w-full text-sm">{children}</table>
    </div>
  );
}
