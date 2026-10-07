import Link from 'next/link';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-secondary-50 px-4">
      <div className="card w-full max-w-md p-8 text-center">
        <div
          className="w-12 h-12 rounded-xl bg-secondary-100 flex items-center justify-center mx-auto mb-4"
          aria-hidden="true"
        >
          <svg
            className="w-7 h-7 text-secondary-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <p className="font-mono text-sm text-secondary-400">404</p>
        <h1 className="mt-1 text-2xl font-bold text-secondary-900">Page not found</h1>
        <p className="mt-2 text-sm text-secondary-600">
          This CampusXolve AI page does not exist or was moved. Check the address or head back
          to your dashboard.
        </p>
        <div className="mt-6 flex flex-wrap gap-3 justify-center">
          <Link href="/dashboard" className="btn-primary px-4 py-2 text-sm">
            Go to Dashboard
          </Link>
          <Link href="/knowledge" className="btn-secondary px-4 py-2 text-sm">
            Browse Knowledge
          </Link>
        </div>
      </div>
    </div>
  );
}
