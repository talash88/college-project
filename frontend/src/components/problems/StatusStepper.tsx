'use client';

const STEPS = ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'ASSIGNED'] as const;

const STEP_LABELS: Record<string, string> = {
  SUBMITTED: 'Submitted',
  UNDER_REVIEW: 'Review',
  APPROVED: 'Approved',
  ASSIGNED: 'Assigned',
};

const TERMINAL_LABELS: Record<string, string> = {
  REJECTED: 'Rejected',
  DUPLICATE: 'Duplicate',
  WITHDRAWN: 'Withdrawn',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
};

export function StatusStepper({ status }: { status: string }) {
  if (status in TERMINAL_LABELS) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium text-secondary-700">Status:</span>
        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-secondary-200 text-secondary-700">
          {TERMINAL_LABELS[status]}
        </span>
      </div>
    );
  }
  const currentIndex = STEPS.indexOf(status as (typeof STEPS)[number]);
  const activeIndex = currentIndex === -1 ? 0 : currentIndex;
  return (
    <ol className="flex items-center gap-1 sm:gap-2 text-xs sm:text-sm" aria-label="Report progress">
      {STEPS.map((step, i) => {
        const done = i < activeIndex;
        const current = i === activeIndex;
        return (
          <li key={step} className="flex items-center gap-1 sm:gap-2 flex-1 last:flex-none">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center font-semibold flex-shrink-0 ${
                done
                  ? 'bg-green-500 text-white'
                  : current
                    ? 'bg-primary-600 text-white'
                    : 'bg-secondary-100 text-secondary-500'
              }`}
              aria-current={current ? 'step' : undefined}
            >
              {done ? '✓' : i + 1}
            </span>
            <span
              className={`hidden sm:inline ${
                current ? 'font-semibold text-secondary-900' : 'text-secondary-500'
              }`}
            >
              {STEP_LABELS[step]}
            </span>
            {i < STEPS.length - 1 && <span className="flex-1 h-px bg-secondary-200 min-w-2" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}
