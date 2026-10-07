'use client';

import { RequireAuth } from '@/components/auth/RequireAuth';
import { WorklistPage } from '@/components/problems/WorklistPage';
import { API_ENDPOINTS } from '@/lib/api-config';

export default function MentoredPage() {
  return (
    <RequireAuth>
      <WorklistPage
        title="Mentored Problems"
        subtitle="Problems where you are the assigned faculty mentor."
        emptyText="No mentored problems yet. When an administrator assigns you as mentor, the report appears here."
        endpoint={API_ENDPOINTS.problems.mentoredMine}
      />
    </RequireAuth>
  );
}
