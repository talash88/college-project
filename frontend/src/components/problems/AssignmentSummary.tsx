'use client';

import type { ProblemAssignment } from '@/types/api';

function initials(name: string | null): string {
  if (!name) return '??';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Safe assignment summary for reporter/solver/mentor (no IDs, no reasons). */
export function AssignmentSummary({ assignment }: { assignment: ProblemAssignment }) {
  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-secondary-900 mb-1">Assignment</h2>
      <p className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-800 inline-block mb-3">
        {assignment.status === 'ACTIVE' ? 'Assigned' : assignment.status}
      </p>

      <h3 className="text-sm font-medium text-secondary-700">Assigned Team</h3>
      <p className="text-sm font-semibold text-secondary-900 mb-2">
        {assignment.team.display_label}
      </p>
      <ul className="space-y-2">
        {assignment.team.members
          .filter((m) => m.is_active)
          .map((m, mi) => (
            <li key={`${m.name ?? 'member'}-${mi}`} className="flex items-center gap-2 text-sm">
              <span
                className="w-7 h-7 rounded-full bg-primary-100 text-primary-700 font-semibold text-xs flex items-center justify-center flex-shrink-0"
                aria-hidden="true"
              >
                {initials(m.name)}
              </span>
              <span className="font-medium text-secondary-800">{m.name ?? 'Team member'}</span>
              {m.role_in_team && m.role_in_team !== 'Member' && (
                <span className="text-xs text-secondary-500">· {m.role_in_team}</span>
              )}
            </li>
          ))}
      </ul>

      <h3 className="text-sm font-medium text-secondary-700 mt-4">Faculty Mentor</h3>
      <div className="flex items-center gap-2 mt-1">
        <span
          className="w-7 h-7 rounded-full bg-primary-100 text-primary-700 font-semibold text-xs flex items-center justify-center flex-shrink-0"
          aria-hidden="true"
        >
          {initials(assignment.mentor.name)}
        </span>
        <div className="text-sm">
          <p className="font-medium text-secondary-800">{assignment.mentor.name ?? 'Faculty mentor'}</p>
          {(assignment.mentor.designation || assignment.mentor.specialization) && (
            <p className="text-xs text-secondary-500">
              {[assignment.mentor.designation, assignment.mentor.specialization]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
