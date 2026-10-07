'use client';

import { useState, type ChangeEvent, type FormEvent } from 'react';
import Link from 'next/link';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import { categoryLabel, type ProblemAttachment, type ProblemDetail } from '@/types/api';

const MAX_FILES = 5;
const MAX_FILE_MB = 10;
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

interface PendingFile {
  file: File;
  error: string | null;
}

function validateFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return `${file.name}: only JPEG, PNG, WEBP or PDF files are allowed.`;
  }
  if (file.size === 0) {
    return `${file.name}: file is empty.`;
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return `${file.name}: exceeds ${MAX_FILE_MB} MB.`;
  }
  return null;
}

function NewProblemContent() {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [building, setBuilding] = useState('');
  const [area, setArea] = useState('');
  const [affected, setAffected] = useState('');
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<ProblemDetail | null>(null);
  const [attachmentWarnings, setAttachmentWarnings] = useState<string[]>([]);

  const handleFiles = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    e.target.value = '';
    if (pending.length + selected.length > MAX_FILES) {
      setFormError(`At most ${MAX_FILES} attachments per report.`);
      return;
    }
    setPending((prev) => [...prev, ...selected.map((file) => ({ file, error: validateFile(file) }))]);
  };

  const removePending = (index: number) => {
    setPending((prev) => prev.filter((_, i) => i !== index));
  };

  const validateForm = (): string | null => {
    if (title.trim().length < 5) return 'Title must be at least 5 characters.';
    if (description.trim().length < 20) return 'Description must be at least 20 characters.';
    if (location.trim().length < 3) return 'Location must be at least 3 characters.';
    if (affected.trim() !== '') {
      const n = Number(affected);
      if (!Number.isInteger(n) || n < 1) return 'Affected people must be a whole number of 1 or more.';
    }
    const bad = pending.find((p) => p.error);
    if (bad?.error) return bad.error;
    return null;
  };

  const uploadOne = async (problemId: string, file: File): Promise<ProblemAttachment> => {
    const form = new FormData();
    form.append('file', file);
    const response = await apiClient.instance.post<ProblemAttachment>(
      API_ENDPOINTS.problems.attachments(problemId),
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event) => {
          const total = event.total ?? event.loaded;
          if (total > 0) {
            setUploadProgress((prev) => ({ ...prev, [file.name]: Math.round((event.loaded / total) * 100) }));
          }
        },
      }
    );
    return response.data;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setAttachmentWarnings([]);
    const problem = validateForm();
    if (problem) {
      setFormError(problem);
      return;
    }
    setSubmitting(true);
    setUploadProgress({});
    try {
      const createdProblem = await apiClient.post<ProblemDetail>(API_ENDPOINTS.problems.base, {
        title: title.trim(),
        description: description.trim(),
        location_text: location.trim(),
        building: building.trim() || undefined,
        area: area.trim() || undefined,
        affected_people_count: affected.trim() === '' ? undefined : Number(affected),
      });
      const warnings: string[] = [];
      for (const { file } of pending) {
        try {
          await uploadOne(createdProblem.id, file);
        } catch (err) {
          warnings.push(`${file.name}: ${getApiErrorMessage(err, 'upload failed')}`);
        }
      }
      if (warnings.length > 0) setAttachmentWarnings(warnings);
      setCreated(createdProblem);
    } catch (err) {
      setFormError(getApiErrorMessage(err, 'Failed to submit the report.'));
    } finally {
      setSubmitting(false);
    }
  };

  if (created) {
    return (
      <AppLayout>
        <div className="max-w-2xl mx-auto">
          <div className="card p-8 text-center">
            <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-7 h-7 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-secondary-900">Problem Reported Successfully</h1>
            <p className="mt-2 text-secondary-600">
              Ticket: <span className="font-mono font-semibold text-secondary-900">{created.ticket_number}</span>
            </p>
            <div className="mt-3 text-sm">
              {created.classification_status === 'FAILED' || !created.classification ? (
                <p className="text-secondary-600">
                  AI classification could not be completed. The report was saved successfully.
                </p>
              ) : (
                <p className="text-secondary-600">
                  AI Classification:{' '}
                  <span className="font-medium text-secondary-900">
                    {categoryLabel(created.classification.predicted_category)}
                  </span>{' '}
                  {created.classification.confidence != null && (
                    <span className="text-secondary-500">
                      ({(created.classification.confidence * 100).toFixed(1)}%)
                    </span>
                  )}
                  {created.classification.requires_manual_review && (
                    <span className="ml-1 text-yellow-700">— needs admin review</span>
                  )}
                </p>
              )}
              {created.priority_status === 'COMPLETED' && created.priority_level ? (
                <p className="mt-1 text-secondary-600">
                  Priority:{' '}
                  <span className="font-medium text-secondary-900">
                    {created.priority_level} ({Math.round(created.priority_score ?? 0)} / 100)
                  </span>
                </p>
              ) : (
                <p className="mt-1 text-secondary-600">Priority scoring could not be completed.</p>
              )}
              {created.required_skills_status === 'COMPLETED' && (
                <p className="mt-1 text-secondary-600">
                  Required skills:{' '}
                  <span className="font-medium text-secondary-900">
                    {created.required_skills.length === 0
                      ? 'none detected'
                      : created.required_skills.map((s) => s.skill_name ?? 'Skill').join(', ')}
                  </span>
                </p>
              )}
            </div>
            {attachmentWarnings.length > 0 && (
              <div role="alert" className="mt-4 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 text-left">
                <p className="font-medium mb-1">Some attachments could not be uploaded:</p>
                <ul className="list-disc list-inside">
                  {attachmentWarnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-6 flex flex-wrap gap-3 justify-center">
              <Link href={`/problems/${created.id}`} className="btn-primary px-4 py-2 text-sm">
                View Report
              </Link>
              <Link href="/problems" className="btn-secondary px-4 py-2 text-sm">
                Go to My Reports
              </Link>
              <button
                type="button"
                className="btn-secondary px-4 py-2 text-sm"
                onClick={() => window.location.reload()}
              >
                Report Another Problem
              </button>
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">Report a Campus Problem</h1>
          <p className="mt-1 text-secondary-600">Describe the issue in your own words. No categories or priorities to pick.</p>
        </div>

        <form onSubmit={handleSubmit} className="card p-6 space-y-4" noValidate>
          <div>
            <label htmlFor="title" className="block text-sm font-medium text-secondary-700 mb-1">
              Problem title
            </label>
            <input
              id="title"
              className="input-field"
              placeholder="e.g. Leaking water pipe near the library entrance"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={submitting}
              maxLength={200}
            />
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-secondary-700 mb-1">
              Detailed description <span className="text-secondary-400">(min 20 characters)</span>
            </label>
            <textarea
              id="description"
              rows={5}
              className="input-field"
              placeholder="What is happening, since when, and how does it affect campus life?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
              maxLength={10000}
            />
          </div>

          <div>
            <label htmlFor="location" className="block text-sm font-medium text-secondary-700 mb-1">
              Campus location
            </label>
            <input
              id="location"
              className="input-field"
              placeholder="e.g. Central Library, Ground Floor"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              disabled={submitting}
              maxLength={300}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="building" className="block text-sm font-medium text-secondary-700 mb-1">
                Building <span className="text-secondary-400">(optional)</span>
              </label>
              <input
                id="building"
                className="input-field"
                placeholder="e.g. Central Library"
                value={building}
                onChange={(e) => setBuilding(e.target.value)}
                disabled={submitting}
                maxLength={150}
              />
            </div>
            <div>
              <label htmlFor="area" className="block text-sm font-medium text-secondary-700 mb-1">
                Area <span className="text-secondary-400">(optional)</span>
              </label>
              <input
                id="area"
                className="input-field"
                placeholder="e.g. North Campus"
                value={area}
                onChange={(e) => setArea(e.target.value)}
                disabled={submitting}
                maxLength={150}
              />
            </div>
          </div>

          <div>
            <label htmlFor="affected" className="block text-sm font-medium text-secondary-700 mb-1">
              People affected <span className="text-secondary-400">(optional)</span>
            </label>
            <input
              id="affected"
              type="number"
              min={1}
              className="input-field md:w-48"
              placeholder="e.g. 150"
              value={affected}
              onChange={(e) => setAffected(e.target.value)}
              disabled={submitting}
            />
          </div>

          <div>
            <label htmlFor="attachments" className="block text-sm font-medium text-secondary-700 mb-1">
              Attachments <span className="text-secondary-400">(optional, up to {MAX_FILES}: JPEG, PNG, WEBP, PDF, {MAX_FILE_MB} MB each)</span>
            </label>
            <input
              id="attachments"
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,application/pdf"
              onChange={handleFiles}
              disabled={submitting}
              className="block w-full text-sm text-secondary-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100"
            />
            {pending.length > 0 && (
              <ul className="mt-3 space-y-2">
                {pending.map((p, i) => (
                  <li key={`${p.file.name}-${i}`} className="flex items-center gap-3 rounded-lg border border-secondary-200 px-3 py-2 text-sm">
                    <span className="flex-1 truncate text-secondary-800">{p.file.name}</span>
                    {p.error ? (
                      <span className="text-xs text-red-600">{p.error}</span>
                    ) : (
                      uploadProgress[p.file.name] != null && (
                        <span className="text-xs text-secondary-500">{uploadProgress[p.file.name]}%</span>
                      )
                    )}
                    <button
                      type="button"
                      onClick={() => removePending(i)}
                      disabled={submitting}
                      className="text-xs font-medium text-red-600 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {formError && (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {formError}
            </div>
          )}

          <button type="submit" className="btn-primary w-full py-2.5" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit Report'}
          </button>
        </form>
      </div>
    </AppLayout>
  );
}

export default function NewProblemPage() {
  return (
    <RequireAuth>
      <NewProblemContent />
    </RequireAuth>
  );
}
