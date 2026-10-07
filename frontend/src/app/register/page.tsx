'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';

type AccountType = 'REPORTER' | 'SOLVER';

export default function RegisterPage() {
  const router = useRouter();
  const { user, initializing, loading, error, register, clearError } = useAuth();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('REPORTER');
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!initializing && user) {
      router.replace('/dashboard');
    }
  }, [user, initializing, router]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    setFormError(null);
    if (fullName.trim().length === 0) {
      setFormError('Full name is required.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setFormError('Enter a valid email address.');
      return;
    }
    if (password.length < 8) {
      setFormError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setFormError('Passwords do not match.');
      return;
    }
    try {
      await register({ full_name: fullName.trim(), email: email.trim(), password, role: accountType });
      router.replace('/dashboard');
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Registration failed.');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-secondary-50 px-4 py-10">
      <div className="card w-full max-w-md p-8">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-primary-600 flex items-center justify-center mx-auto mb-4">
            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-secondary-900">Create your account</h1>
          <p className="mt-1 text-sm text-secondary-600">Join CampusXolve AI as a Reporter or Solver</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="fullName" className="block text-sm font-medium text-secondary-700 mb-1">
              Full name
            </label>
            <input
              id="fullName"
              type="text"
              autoComplete="name"
              className="input-field"
              placeholder="Aarav Patel"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={loading}
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-secondary-700 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              className="input-field"
              placeholder="you@college.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
            />
          </div>

          <div>
            <span className="block text-sm font-medium text-secondary-700 mb-1">Account type</span>
            <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="Account type">
              {(['REPORTER', 'SOLVER'] as AccountType[]).map((type) => (
                <button
                  key={type}
                  type="button"
                  role="radio"
                  aria-checked={accountType === type}
                  onClick={() => setAccountType(type)}
                  disabled={loading}
                  className={`rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
                    accountType === type
                      ? 'border-primary-600 bg-primary-50 text-primary-700'
                      : 'border-secondary-300 text-secondary-600 hover:border-secondary-400'
                  }`}
                >
                  {type === 'REPORTER' ? 'Reporter' : 'Solver'}
                  <span className="block text-xs font-normal text-secondary-500">
                    {type === 'REPORTER' ? 'Report campus issues' : 'Solve assigned problems'}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-secondary-700 mb-1">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                className="input-field pr-16"
                placeholder="Minimum 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-medium text-primary-600 hover:text-primary-700"
                disabled={loading}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-secondary-700 mb-1">
              Confirm password
            </label>
            <input
              id="confirmPassword"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              className="input-field"
              placeholder="Repeat your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={loading}
            />
          </div>

          {(formError || error) && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {formError || error}
            </div>
          )}

          <button type="submit" className="btn-primary w-full py-2.5" disabled={loading}>
            {loading ? 'Creating account…' : 'Register'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-secondary-600">
          Already have an account?{' '}
          <Link href="/login" className="font-medium text-primary-600 hover:text-primary-700">
            Login
          </Link>
        </p>
      </div>
    </div>
  );
}
