import Link from 'next/link';

export default function ForbiddenPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-secondary-50 px-4">
      <div className="card w-full max-w-md p-8 text-center">
        <div className="w-12 h-12 rounded-xl bg-red-100 flex items-center justify-center mx-auto mb-4">
          <svg className="w-7 h-7 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-secondary-900">403 — Access denied</h1>
        <p className="mt-2 text-sm text-secondary-600">
          Your account role does not have permission to view this page.
        </p>
        <div className="mt-6 flex gap-3 justify-center">
          <Link href="/dashboard" className="btn-primary px-4 py-2 text-sm">
            Go to Dashboard
          </Link>
          <Link href="/profile" className="btn-secondary px-4 py-2 text-sm">
            View Profile
          </Link>
        </div>
      </div>
    </div>
  );
}
