export const API_CONFIG = {
  baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  apiPrefix: '/api/v1',
  timeout: 10000,
} as const;

export const API_ENDPOINTS = {
  health: `${API_CONFIG.baseUrl}${API_CONFIG.apiPrefix}/health`,
  root: `${API_CONFIG.baseUrl}${API_CONFIG.apiPrefix}/`,
  auth: {
    register: `${API_CONFIG.apiPrefix}/auth/register`,
    login: `${API_CONFIG.apiPrefix}/auth/login`,
    refresh: `${API_CONFIG.apiPrefix}/auth/refresh`,
    logout: `${API_CONFIG.apiPrefix}/auth/logout`,
    me: `${API_CONFIG.apiPrefix}/auth/me`,
  },
  profile: {
    me: `${API_CONFIG.apiPrefix}/profile/me`,
    mySkills: `${API_CONFIG.apiPrefix}/profile/me/skills`,
    mySkill: (skillId: string) => `${API_CONFIG.apiPrefix}/profile/me/skills/${skillId}`,
  },
  skills: `${API_CONFIG.apiPrefix}/skills`,
  problems: {
    base: `${API_CONFIG.apiPrefix}/problems`,
    mine: `${API_CONFIG.apiPrefix}/problems/me`,
    myStats: `${API_CONFIG.apiPrefix}/problems/me/stats`,
    detail: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}`,
    attachments: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/attachments`,
    attachment: (id: string, attachmentId: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/attachments/${attachmentId}`,
    activity: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/activity`,
    comments: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/comments`,
    classification: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/classification`,
    priority: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/priority`,
    requiredSkills: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/required-skills`,
    duplicates: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/duplicates`,
    teamRecommendations: (id: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/team-recommendations`,
    teamRecommendationHistory: (id: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/team-recommendations/history`,
    mentorRecommendations: (id: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/mentor-recommendations`,
    mentorRecommendationHistory: (id: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/mentor-recommendations/history`,
    assignedMine: `${API_CONFIG.apiPrefix}/problems/assigned/me`,
    mentoredMine: `${API_CONFIG.apiPrefix}/problems/mentored/me`,
    workspace: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/workspace`,
    tasks: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/tasks`,
    task: (id: string, taskId: string) => `${API_CONFIG.apiPrefix}/problems/${id}/tasks/${taskId}`,
    milestones: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/milestones`,
    milestone: (id: string, milestoneId: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/milestones/${milestoneId}`,
    progressUpdates: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/progress-updates`,
    workFiles: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/work-files`,
    workFile: (id: string, fileId: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/work-files/${fileId}`,
    workFileDownload: (id: string, fileId: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/work-files/${fileId}/download`,
    discussion: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/discussion`,
    publicProgress: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/public-progress`,
    solutionReadiness: (id: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/solution/readiness`,
    solutions: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/solutions`,
    latestSolution: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/solutions/latest`,
    solutionReview: (id: string, submissionId: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/solutions/${submissionId}/review`,
    relatedSolutions: (id: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/related-solutions`,
    verifications: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/verifications`,
    safeSolution: (id: string) => `${API_CONFIG.apiPrefix}/problems/${id}/solution/safe`,
    sharedEvidenceDownload: (id: string, fileId: string) =>
      `${API_CONFIG.apiPrefix}/problems/${id}/solution/evidence/${fileId}/download`,
  },
  notifications: {
    base: `${API_CONFIG.apiPrefix}/notifications`,
    unreadCount: `${API_CONFIG.apiPrefix}/notifications/unread-count`,
    markRead: (id: string) => `${API_CONFIG.apiPrefix}/notifications/${id}/read`,
    readAll: `${API_CONFIG.apiPrefix}/notifications/read-all`,
  },
  adminDuplicates: {
    reanalyze: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/duplicates/reanalyze`,
    confirm: (candidateId: string) =>
      `${API_CONFIG.apiPrefix}/admin/duplicate-candidates/${candidateId}/confirm`,
    reject: (candidateId: string) =>
      `${API_CONFIG.apiPrefix}/admin/duplicate-candidates/${candidateId}/reject`,
    clusters: `${API_CONFIG.apiPrefix}/admin/duplicate-clusters`,
    clusterDetail: (clusterId: string) =>
      `${API_CONFIG.apiPrefix}/admin/duplicate-clusters/${clusterId}`,
  },
  adminProblems: {
    base: `${API_CONFIG.apiPrefix}/admin/problems`,
    detail: (id: string) => `${API_CONFIG.apiPrefix}/admin/problems/${id}`,
    rerunClassification: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/classification/run`,
    reviewClassification: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/classification/review`,
    recalculatePriority: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/priority/recalculate`,
    reanalyzeSkills: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/skills/reanalyze`,
    recalculateTeam: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/recommendations/team/recalculate`,
    recalculateMentor: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/recommendations/mentor/recalculate`,
    startReview: (id: string) => `${API_CONFIG.apiPrefix}/admin/problems/${id}/review/start`,
    approve: (id: string) => `${API_CONFIG.apiPrefix}/admin/problems/${id}/approve`,
    reject: (id: string) => `${API_CONFIG.apiPrefix}/admin/problems/${id}/reject`,
    assign: (id: string) => `${API_CONFIG.apiPrefix}/admin/problems/${id}/assign`,
    assignment: (id: string) => `${API_CONFIG.apiPrefix}/admin/problems/${id}/assignment`,
    reassign: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/assignment/reassign`,
    cancelAssignment: (id: string) =>
      `${API_CONFIG.apiPrefix}/admin/problems/${id}/assignment/cancel`,
    close: (id: string) => `${API_CONFIG.apiPrefix}/admin/problems/${id}/close`,
    eligibleSolvers: `${API_CONFIG.apiPrefix}/admin/problems/eligible-solvers`,
  },
  knowledge: {
    base: `${API_CONFIG.apiPrefix}/knowledge`,
    detail: (ref: string) => `${API_CONFIG.apiPrefix}/knowledge/${ref}`,
    related: (ref: string) => `${API_CONFIG.apiPrefix}/knowledge/${ref}/related`,
    evidenceDownload: (ref: string, fileId: string) =>
      `${API_CONFIG.apiPrefix}/knowledge/${ref}/evidence/${fileId}/download`,
  },
  adminKnowledge: {
    base: `${API_CONFIG.apiPrefix}/admin/knowledge`,
    retry: (id: string) => `${API_CONFIG.apiPrefix}/admin/knowledge/${id}/retry`,
    archive: (id: string) => `${API_CONFIG.apiPrefix}/admin/knowledge/${id}/archive`,
    unarchive: (id: string) => `${API_CONFIG.apiPrefix}/admin/knowledge/${id}/unarchive`,
  },
  adminAnalytics: {
    dashboard: `${API_CONFIG.apiPrefix}/admin/analytics/dashboard`,
    trends: `${API_CONFIG.apiPrefix}/admin/analytics/trends`,
    exportProblems: `${API_CONFIG.apiPrefix}/admin/analytics/export/problems.csv`,
    exportSkills: `${API_CONFIG.apiPrefix}/admin/analytics/export/skills.csv`,
  },
} as const;
