'use client';

import { RequireAuth } from '@/components/auth/RequireAuth';
import { WorklistPage } from '@/components/problems/WorklistPage';
import { API_ENDPOINTS } from '@/lib/api-config';

export default function AssignedPage() {
  return (
    <RequireAuth>
      <WorklistPage
        title="Assigned Problems"
        subtitle="Problems where you are an active team member."
        emptyText="No assigned problems yet. When an administrator assigns you to a report, it appears here."
        endpoint={API_ENDPOINTS.problems.assignedMine}
      />
    </RequireAuth>
  );
}
