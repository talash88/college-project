'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { KnowledgeSearchResponse, SkillOption } from '@/types/api';

const PAGE_SIZE = 10;
const CATEGORIES = [
  '',
  'ACADEMIC',
  'CLEANLINESS_SANITATION',
  'ELECTRICAL',
  'HOSTEL',
  'INFRASTRUCTURE',
  'IT_NETWORK',
  'LABORATORY',
  'LIBRARY',
  'OTHER',
  'SAFETY_SECURITY',
  'TRANSPORT',
  'WATER_SANITATION',
];
const MODES = ['ALL', 'HYBRID', 'KEYWORD', 'SEMANTIC'] as const;
const SORTS = ['relevance', 'newest', 'oldest'] as const;

function formatScore(value: number | null): string {
  if (value == null) return '—';
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString();
}

function KnowledgeListContent() {
  const [data, setData] = useState<KnowledgeSearchResponse | null>(null);
  const [skills, setSkills] = useState<SkillOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [mode, setMode] = useState<(typeof MODES)[number]>('ALL');
  const [category, setCategory] = useState('');
  const [skillId, setSkillId] = useState('');
  const [location, setLocation] = useState('');
  const [sort, setSort] = useState<(typeof SORTS)[number]>('newest');
  const [page, setPage] = useState(1);

  useEffect(() => {
    (async () => {
      try {
        const list = await apiClient.get<SkillOption[]>(API_ENDPOINTS.skills);
        setSkills(Array.isArray(list) ? list : []);
      } catch {
        setSkills([]);
      }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
        search_mode: mode,
        sort,
      });
      if (appliedSearch.trim()) params.set('q', appliedSearch.trim());
      if (category) params.set('category', category);
      if (skillId) params.set('skill_id', skillId);
      if (location.trim()) params.set('location', location.trim());
      const result = await apiClient.get<KnowledgeSearchResponse>(
        `${API_ENDPOINTS.knowledge.base}?${params}`
      );
      setData(result);
    } catch (err) {
      setError(getApiErrorMessage(err, 'Failed to load the Knowledge Repository.'));
    } finally {
      setLoading(false);
    }
  }, [page, mode, sort, appliedSearch, category, skillId, location]);

  useEffect(() => {
    load();
  }, [load]);

  const applySearch = () => {
    setPage(1);
    setAppliedSearch(search);
  };

  const showSemantic = appliedSearch.trim().length > 0 && mode !== 'KEYWORD';

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">Knowledge Repository</h1>
          <p className="mt-1 text-secondary-600">
            Previously solved campus issues and reusable solutions.
          </p>
        </div>

        <div className="card p-4 md:p-6 space-y-4">
          <div className="flex flex-col md:flex-row gap-3">
            <input
              id="kb-search"
              className="input-field md:flex-1"
              placeholder="Search solved issues — keywords or meaning…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') applySearch();
              }}
              aria-label="Search knowledge repository"
            />
            <button type="button" className="btn-primary" onClick={applySearch}>
              Search
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <label className="block">
              <span className="label">Search mode</span>
              <select
                className="input-field"
                value={mode}
                onChange={(e) => {
                  setMode(e.target.value as (typeof MODES)[number]);
                  setPage(1);
                }}
                aria-label="Search mode"
              >
                {MODES.map((m) => (
                  <option key={m} value={m}>
                    {m === 'ALL' ? 'All (hybrid)' : m.charAt(0) + m.slice(1).toLowerCase()}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Category</span>
              <select
                className="input-field"
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setPage(1);
                }}
                aria-label="Filter by category"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c === '' ? 'All categories' : c}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Skill</span>
              <select
                className="input-field"
                value={skillId}
                onChange={(e) => {
                  setSkillId(e.target.value);
                  setPage(1);
                }}
                aria-label="Filter by skill"
              >
                <option value="">All skills</option>
                {skills.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">Location</span>
              <input
                className="input-field"
                placeholder="e.g. Library"
                value={location}
                onChange={(e) => {
                  setLocation(e.target.value);
                  setPage(1);
                }}
                aria-label="Filter by location"
              />
            </label>
            <label className="block">
              <span className="label">Sort</span>
              <select
                className="input-field"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value as (typeof SORTS)[number]);
                  setPage(1);
                }}
                aria-label="Sort results"
              >
                {SORTS.map((s) => (
                  <option key={s} value={s}>
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {loading ? (
          <div className="card p-6 text-sm text-secondary-600">Loading solved issues…</div>
        ) : error ? (
          <div className="card p-6 text-sm text-red-700" role="alert">
            {error}
          </div>
        ) : !data || data.total === 0 ? (
          <div className="card p-6 text-sm text-secondary-600">
            No solved problems have been published to the Knowledge Repository yet.
          </div>
        ) : (
          <>
            {data.error && (
              <div className="card p-4 text-sm text-amber-800 bg-amber-50" role="status">
                {data.error}
              </div>
            )}
            <p className="text-sm text-secondary-600" role="status">
              {data.total} solved {data.total === 1 ? 'issue' : 'issues'} found.
            </p>
            <ul className="space-y-4">
              {data.items.map((item) => (
                <li key={item.id} className="card p-5 md:p-6">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-mono text-secondary-500">{item.public_id}</span>
                    {item.final_category && (
                      <span className="font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-800">
                        {item.final_category}
                      </span>
                    )}
                    {showSemantic && (
                      <span className="font-medium px-2 py-0.5 rounded-full bg-secondary-100 text-secondary-600">
                        {formatScore(item.semantic_similarity)} relevant
                      </span>
                    )}
                  </div>
                  <Link
                    href={`/knowledge/${item.public_id}`}
                    className="mt-2 block text-lg font-semibold text-primary-700 hover:text-primary-800"
                  >
                    {item.title}
                  </Link>
                  <p className="mt-1 text-sm text-secondary-600">{item.problem_preview}</p>
                  {item.skills.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {item.skills.map((s) => (
                        <span
                          key={s.skill_id}
                          className="text-xs px-2 py-0.5 rounded-full bg-primary-50 text-primary-700"
                        >
                          {s.name}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="mt-2 text-xs text-secondary-500">
                    {item.location_summary ? `${item.location_summary} · ` : ''}
                    Resolved {formatDate(item.published_at)}
                  </p>
                </li>
              ))}
            </ul>
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </button>
              <span className="text-sm text-secondary-600">Page {page}</span>
              <button
                type="button"
                className="btn-secondary px-3 py-1.5 text-sm"
                disabled={data.items.length < PAGE_SIZE}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function KnowledgePage() {
  return (
    <RequireAuth>
      <KnowledgeListContent />
    </RequireAuth>
  );
}
