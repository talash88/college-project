/** Central status/priority color system (Step 14).
 *
 * One status value => exactly one badge style, everywhere.
 * Palette: slate neutrals, institutional blue/indigo, green success,
 * amber warning/review, red danger. Purple reserved for AI-analysis accents.
 */

export const PROBLEM_STATUS_STYLES: Record<string, string> = {
  SUBMITTED: 'bg-blue-100 text-blue-800',
  UNDER_REVIEW: 'bg-amber-100 text-amber-800',
  APPROVED: 'bg-cyan-100 text-cyan-800',
  ASSIGNED: 'bg-indigo-100 text-indigo-800',
  IN_PROGRESS: 'bg-blue-100 text-blue-800',
  AWAITING_VERIFICATION: 'bg-amber-100 text-amber-800',
  RESOLVED: 'bg-green-100 text-green-800',
  CLOSED: 'bg-green-100 text-green-800',
  REJECTED: 'bg-red-100 text-red-800',
  DUPLICATE: 'bg-secondary-100 text-secondary-600',
  WITHDRAWN: 'bg-secondary-100 text-secondary-600',
};

export const PRIORITY_STYLES: Record<string, string> = {
  LOW: 'bg-green-100 text-green-800',
  MEDIUM: 'bg-yellow-100 text-yellow-800',
  HIGH: 'bg-orange-100 text-orange-800',
  CRITICAL: 'bg-red-100 text-red-800',
};

export const TASK_STATUS_STYLES: Record<string, string> = {
  TODO: 'bg-secondary-100 text-secondary-700',
  IN_PROGRESS: 'bg-blue-100 text-blue-800',
  BLOCKED: 'bg-red-100 text-red-800',
  DONE: 'bg-green-100 text-green-800',
  CANCELLED: 'bg-secondary-100 text-secondary-500',
};

export const MILESTONE_STATUS_STYLES: Record<string, string> = {
  PLANNED: 'bg-secondary-100 text-secondary-700',
  IN_PROGRESS: 'bg-blue-100 text-blue-800',
  COMPLETED: 'bg-green-100 text-green-800',
  MISSED: 'bg-red-100 text-red-800',
  CANCELLED: 'bg-secondary-100 text-secondary-500',
};

export const REVIEW_DECISION_STYLES: Record<string, string> = {
  APPROVED: 'bg-green-100 text-green-800',
  CHANGES_REQUESTED: 'bg-amber-100 text-amber-800',
};

export const VERIFICATION_DECISION_STYLES: Record<string, string> = {
  RESOLVED: 'bg-green-100 text-green-800',
  NOT_RESOLVED: 'bg-red-100 text-red-800',
};

export const DUPLICATE_DECISION_STYLES: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-800',
  CONFIRMED_DUPLICATE: 'bg-indigo-100 text-indigo-800',
  REJECTED: 'bg-secondary-100 text-secondary-600',
  STALE: 'bg-secondary-100 text-secondary-500',
};

export const PUBLICATION_STATUS_STYLES: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-800',
  PUBLISHED: 'bg-green-100 text-green-800',
  FAILED: 'bg-red-100 text-red-800',
  ARCHIVED: 'bg-secondary-100 text-secondary-600',
};

export const CATEGORY_BADGE = 'bg-blue-100 text-blue-800';
export const SKILL_CHIP = 'bg-primary-50 text-primary-700';
export const NEUTRAL_BADGE = 'bg-secondary-100 text-secondary-700';

const FALLBACK_BADGE = 'bg-secondary-100 text-secondary-600';

export function problemStatusStyle(status: string | null | undefined): string {
  if (!status) return FALLBACK_BADGE;
  return PROBLEM_STATUS_STYLES[status] ?? FALLBACK_BADGE;
}

export function priorityStyle(level: string | null | undefined): string {
  if (!level) return FALLBACK_BADGE;
  return PRIORITY_STYLES[level] ?? FALLBACK_BADGE;
}

export function badgeStyle(map: Record<string, string>, value: string | null | undefined): string {
  if (!value) return FALLBACK_BADGE;
  return map[value] ?? FALLBACK_BADGE;
}
