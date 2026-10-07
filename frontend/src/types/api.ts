export interface HealthResponse {
  status: string;
  service: string;
  database: string;
  pgvector_available: boolean;
  environment: string;
}

export interface RootResponse {
  name: string;
  description: string;
  version: string;
  docs_url: string;
}

export interface BackendStatus {
  connected: boolean;
  loading: boolean;
  error: string | null;
  data: HealthResponse | null;
}

export type UserRole = 'REPORTER' | 'SOLVER' | 'MENTOR' | 'ADMIN';

export interface StudentProfile {
  id: string;
  user_id: string;
  student_identifier: string;
  department: string;
  academic_year: number;
  semester: number | null;
  bio: string | null;
  availability_status: string;
  current_workload: number;
  max_workload: number;
  created_at: string;
  updated_at: string;
}

export interface FacultyProfile {
  id: string;
  user_id: string;
  employee_identifier: string;
  department: string;
  designation: string;
  specialization: string;
  bio: string | null;
  availability_status: string;
  current_workload: number;
  max_workload: number;
  created_at: string;
  updated_at: string;
}

export interface AuthUser {
  id: string;
  full_name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  student_profile?: StudentProfile | null;
  faculty_profile?: FacultyProfile | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterResponse extends TokenResponse {
  user: AuthUser;
}

export interface Skill {
  id: string;
  name: string;
  normalized_name: string;
  category: string;
  description: string | null;
  is_active: boolean;
}

export interface UserSkill {
  id: string;
  user_id: string;
  skill_id: string;
  proficiency_level: number;
  years_experience: number | null;
  is_verified: boolean;
  skill: Skill | null;
}

export interface ApiErrorBody {
  detail?: string | Array<{ msg?: string; loc?: Array<string | number> }>;
}

export type ProblemStatus =
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'ASSIGNED'
  | 'IN_PROGRESS'
  | 'AWAITING_VERIFICATION'
  | 'RESOLVED'
  | 'CLOSED'
  | 'REJECTED'
  | 'DUPLICATE'
  | 'WITHDRAWN';

export interface ReporterSummary {
  id: string;
  full_name: string;
  role: string;
}

export interface ProblemAttachment {
  id: string;
  problem_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  uploaded_by: string;
  created_at: string;
}

export interface ProblemActivity {
  id: string;
  problem_id: string;
  actor_user_id: string | null;
  event_type: string;
  old_status: string | null;
  new_status: string | null;
  message: string | null;
  created_at: string;
}

export interface ProblemComment {
  id: string;
  problem_id: string;
  author_id: string;
  author_name: string | null;
  content: string;
  is_internal: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProblemSummary {
  id: string;
  ticket_number: string;
  title: string;
  status: ProblemStatus;
  location_text: string;
  affected_people_count: number | null;
  classification_status: ClassificationStatus;
  created_at: string;
  submitted_at: string;
}

export type ClassificationStatus =
  | 'NOT_RUN'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'LOW_CONFIDENCE'
  | 'FAILED';

export interface ProblemClassification {
  id: string;
  problem_id: string;
  predicted_category: string | null;
  confidence: number | null;
  model_name: string;
  model_version: string;
  status: ClassificationStatus;
  requires_manual_review: boolean;
  classified_at: string | null;
  created_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  final_category: string | null;
  review_note: string | null;
}

export interface PriorityComponent {
  component: string;
  raw_value: unknown;
  contribution: number;
  max_contribution: number;
  reason: string;
}

export interface PriorityAnalysis {
  id: string;
  problem_id: string;
  score: number | null;
  priority_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | null;
  severity_component: number;
  affected_people_component: number;
  age_component: number;
  category_component: number;
  duplicate_component: number;
  reasons: string[];
  component_details: { components?: PriorityComponent[] };
  algorithm_version: string;
  status: string;
  recalculation_reason: string | null;
  calculated_at: string | null;
  created_at: string;
}

export interface RequiredSkill {
  id: string;
  problem_id: string;
  skill_id: string;
  skill_name: string | null;
  skill_category: string | null;
  score: number;
  match_type: 'EXACT' | 'SEMANTIC' | 'HYBRID';
  reason: string | null;
  model_name: string;
  model_version: string;
  created_at: string;
}

export interface SkillAnalysis {
  id: string;
  problem_id: string;
  model_name: string;
  model_version: string;
  status: string;
  recalculation_reason: string | null;
  created_at: string;
  required_skills: RequiredSkill[];
}

export const CATEGORY_LABELS: Record<string, string> = {
  IT_NETWORK: 'IT / Network',
  ELECTRICAL: 'Electrical',
  INFRASTRUCTURE: 'Infrastructure',
  CLEANLINESS_SANITATION: 'Cleanliness / Sanitation',
  SAFETY_SECURITY: 'Safety / Security',
  LABORATORY: 'Laboratory',
  LIBRARY: 'Library',
  ACADEMIC: 'Academic',
  HOSTEL: 'Hostel',
  TRANSPORT: 'Transport',
  WATER_SANITATION: 'Water / Sanitation',
  OTHER: 'Other',
};

export function categoryLabel(code: string | null): string {
  if (!code) return '—';
  return CATEGORY_LABELS[code] ?? code;
}

export interface DuplicateCandidateSummary {
  id: string;
  ticket_number: string;
  title: string;
  status: string;
}

export interface DuplicateCandidate {
  id: string;
  source_problem_id: string;
  candidate_problem_id: string;
  candidate: DuplicateCandidateSummary | null;
  semantic_similarity: number;
  location_score: number | null;
  category_support_score: number | null;
  final_match_score: number;
  match_strength: string;
  decision_status: string;
  embedding_version: string;
  algorithm_version: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string;
}

export interface CanonicalSummary {
  id: string;
  ticket_number: string;
  title: string;
  status: string;
  location_text: string;
  created_at: string;
}

export interface ClusterMember {
  problem_id: string;
  ticket_number: string;
  title: string;
  status: string;
  reporter_name: string | null;
  is_canonical: boolean;
  joined_at: string;
}

export interface DuplicateCluster {
  id: string;
  cluster_number: string;
  canonical_problem_id: string | null;
  canonical: CanonicalSummary | null;
  members: ClusterMember[];
  created_at: string;
}

export type DuplicateAnalysisStatus =
  | 'NOT_RUN'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'FAILED'
  | 'NO_MATCHES'
  | 'POSSIBLE_DUPLICATES';

export interface OwnerDuplicatesResponse {
  analysis_status: string;
  candidates: DuplicateCandidate[];
  cluster: DuplicateCluster | null;
  canonical: CanonicalSummary | null;
}

export interface ProblemDetail extends ProblemSummary {
  description: string;
  reporter_id: string;
  reporter: ReporterSummary | null;
  building: string | null;
  area: string | null;
  predicted_category: string | null;
  classification_confidence: number | null;
  classification_status: ClassificationStatus;
  classification: ProblemClassification | null;
  priority_score: number | null;
  priority_level: string | null;
  priority_status: string;
  progress_percent: number;
  required_skills_status: string;
  duplicate_status: DuplicateAnalysisStatus;
  team_recommendation_status: string;
  mentor_recommendation_status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  canonical: CanonicalSummary | null;
  resolved_at: string | null;
  closed_at: string | null;
  updated_at: string;
  priority: PriorityAnalysis | null;
  required_skills: RequiredSkill[];
  attachments: ProblemAttachment[];
  activity: ProblemActivity[];
  comments: ProblemComment[];
  assignment: ProblemAssignment | null;
}

export interface ProblemListResponse {
  items: ProblemSummary[];
  total: number;
  skip: number;
  limit: number;
}

export interface AdminProblemSummary extends ProblemSummary {
  reporter_name: string | null;
  reporter_email: string | null;
}

export interface AdminProblemListResponse {
  items: AdminProblemSummary[];
  total: number;
  skip: number;
  limit: number;
}

export interface ProblemStats {
  total: number;
  by_status: Record<string, number>;
}

export type AssignmentStatus = 'ACTIVE' | 'COMPLETED' | 'CANCELLED' | 'REASSIGNED';

export interface AssignmentMember {
  user_id: string | null;
  name: string | null;
  role_in_team: string | null;
  joined_at: string | null;
  is_active: boolean;
}

export interface AssignmentTeam {
  id: string;
  name: string | null;
  display_label: string;
  is_active: boolean;
  members: AssignmentMember[];
  created_at: string;
}

export interface AssignmentMentor {
  user_id: string | null;
  name: string | null;
  designation: string | null;
  specialization: string | null;
}

export interface ProblemAssignment {
  id: string;
  problem_id: string;
  ticket_number: string | null;
  team: AssignmentTeam;
  mentor: AssignmentMentor;
  source_team_recommendation_id: string | null;
  source_mentor_recommendation_id: string | null;
  assigned_by: string | null;
  assigned_at: string;
  team_was_overridden: boolean;
  mentor_was_overridden: boolean;
  team_override_reason: string | null;
  mentor_override_reason: string | null;
  status: AssignmentStatus;
  unassigned_at: string | null;
  unassigned_by: string | null;
  unassignment_reason: string | null;
  created_at: string;
  idempotent_replay: boolean;
}

export interface AssignmentHistoryEntry {
  id: string;
  status: AssignmentStatus;
  team_name: string | null;
  member_count: number;
  mentor_name: string | null;
  team_was_overridden: boolean;
  mentor_was_overridden: boolean;
  assigned_by: string | null;
  assigned_at: string;
  unassigned_at: string | null;
  unassignment_reason: string | null;
}

export interface AssignmentDetail {
  active: ProblemAssignment | null;
  history: AssignmentHistoryEntry[];
}

export interface AssignedProblem {
  id: string;
  ticket_number: string;
  title: string;
  status: string;
  priority_level: string | null;
  priority_score: number | null;
  location_text: string;
  team_name: string | null;
  team_member_names: string[];
  mentor_name: string | null;
  assigned_at: string | null;
  submitted_at: string;
}

export interface EligibleSolver {
  user_id: string;
  name: string;
  availability: string;
  current_workload: number;
  max_workload: number;
  department: string | null;
  academic_year: number | null;
  skills: Array<{
    skill_id: string;
    name: string;
    proficiency: number;
    is_verified: boolean;
    category: string | null;
  }>;
}

export interface ReviewActionResult {
  id: string;
  ticket_number: string;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  already_in_state: boolean;
}

export type RecommendationStatus =
  | 'NOT_RUN'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'NO_ELIGIBLE_CANDIDATES'
  | 'INSUFFICIENT_DATA'
  | 'FAILED';

export interface CoveredSkill {
  skill_id: string | null;
  name: string;
  relevance: number | null;
  match_kind: string | null;
  proficiency: number | null;
  proficiency_label: string | null;
  verified: boolean | null;
}

export interface TeamMember {
  user_id: string | null;
  name: string;
  individual_score: number | null;
  availability: string | null;
  current_workload: number | null;
  max_workload: number | null;
  department: string | null;
  academic_year: number | null;
  covered_skills: CoveredSkill[];
  high_relevance_covered: string[];
}

export interface TeamOption {
  id: string;
  run_id: string;
  score: number;
  skill_coverage_score: number;
  proficiency_score: number;
  availability_score: number;
  workload_score: number;
  verified_skill_score: number;
  domain_score: number;
  coverage_percent: number;
  team_size: number;
  missing_skills: string[];
  members: TeamMember[];
  algorithm_version: string;
  created_at: string;
}

export interface CanonicalPointer {
  id: string;
  ticket_number: string;
  title: string;
  status: string;
}

export interface TeamRecommendations {
  status: string;
  options: TeamOption[];
  canonical: CanonicalPointer | null;
  message: string | null;
}

export interface TeamHistoryEntry {
  run_id: string;
  created_at: string;
  options: number;
}

export interface MentorMatchedSkill {
  skill_id: string | null;
  name: string;
  relevance: number | null;
  match_kind: string | null;
  proficiency: number | null;
  proficiency_label: string | null;
}

export interface MentorCandidate {
  id: string;
  run_id: string;
  mentor_user_id: string | null;
  name: string | null;
  designation: string | null;
  specialization: string | null;
  department: string | null;
  score: number;
  specialization_score: number;
  skill_match_score: number;
  category_score: number;
  availability_score: number;
  workload_score: number;
  semantic_similarity: number;
  availability: string | null;
  current_workload: number | null;
  max_workload: number | null;
  matched_skills: MentorMatchedSkill[];
  algorithm_version: string;
  created_at: string;
}

export interface MentorRecommendations {
  status: string;
  mentors: MentorCandidate[];
  canonical: CanonicalPointer | null;
  message: string | null;
}

export interface MentorHistoryEntry {
  run_id: string;
  created_at: string;
  candidates: number;
}

export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'BLOCKED' | 'DONE' | 'CANCELLED';
export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type MilestoneStatus = 'PLANNED' | 'IN_PROGRESS' | 'COMPLETED' | 'MISSED' | 'CANCELLED';

export interface WorkspaceTask {
  id: string;
  problem_id: string;
  team_id: string;
  title: string;
  description: string | null;
  assigned_to_user_id: string | null;
  assignee_name: string | null;
  created_by_user_id: string;
  creator_name: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  order_index: number;
  blocker_reason: string | null;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface WorkspaceMilestone {
  id: string;
  problem_id: string;
  title: string;
  description: string | null;
  target_date: string | null;
  status: MilestoneStatus;
  order_index: number;
  created_by: string | null;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface WorkspaceProgressUpdate {
  id: string;
  problem_id: string;
  author_user_id: string;
  author_name: string | null;
  author_role: string | null;
  summary: string;
  details: string | null;
  blockers: string | null;
  next_steps: string | null;
  progress_snapshot: number;
  created_at: string;
}

export interface WorkspaceFile {
  id: string;
  problem_id: string;
  task_id: string | null;
  uploaded_by: string;
  uploader_name: string | null;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  description: string | null;
  is_knowledge_shareable: boolean;
  created_at: string;
}

export interface WorkspaceProgress {
  percent: number;
  done_tasks: number;
  total_tasks: number;
  done_milestones: number;
  total_milestones: number;
}

export interface WorkspaceOverview {
  problem_id: string;
  ticket_number: string;
  title: string;
  status: string;
  priority_level: string | null;
  priority_score: number | null;
  predicted_category: string | null;
  required_skills: string[];
  team: {
    id: string;
    name: string | null;
    display_label: string | null;
    members: { user_id: string | null; name: string | null; role_in_team: string | null; joined_at: string | null }[];
  } | null;
  mentor: { name: string | null; designation: string | null; specialization: string | null } | null;
  assigned_at: string | null;
  progress: WorkspaceProgress;
}

export interface PublicProgress {
  problem_id: string;
  ticket_number: string;
  title: string;
  status: string;
  progress_percent: number;
  completed_tasks: number;
  total_tasks: number;
  completed_milestones: number;
  total_milestones: number;
  team_name: string | null;
  team_member_names: string[];
  mentor_name: string | null;
  assignment_active: boolean;
  recent_updates: {
    summary: string;
    progress_snapshot: number;
    author_role: string | null;
    created_at: string;
  }[];
  solution: SafeSolution | null;
}

export interface SolutionReview {
  id: string;
  solution_submission_id: string;
  mentor_user_id: string;
  mentor_name: string | null;
  decision: 'APPROVED' | 'CHANGES_REQUESTED';
  review_comment: string | null;
  is_admin_override: boolean;
  created_at: string;
}

export interface SolutionSubmission {
  id: string;
  problem_id: string;
  assignment_id: string;
  submitted_by_user_id: string;
  submitter_name: string | null;
  revision_number: number;
  solution_summary: string;
  root_cause: string;
  work_performed: string;
  testing_performed: string | null;
  deployment_notes: string | null;
  limitations: string | null;
  evidence_attachment_ids: string[];
  readiness_override_reason: string | null;
  status: 'SUBMITTED' | 'CHANGES_REQUESTED' | 'MENTOR_APPROVED' | 'REPORTER_REJECTED' | 'VERIFIED';
  submitted_at: string;
  updated_at: string;
  reviews: SolutionReview[];
}

export interface ReadinessCheck {
  ready: boolean;
  reasons: string[];
  progress_percent: number;
  done_tasks: number;
  total_tasks: number;
  done_milestones: number;
  total_milestones: number;
  blocked_tasks: number;
}

export interface VerificationRecord {
  id: string;
  problem_id: string;
  solution_submission_id: string | null;
  reporter_user_id: string;
  decision: 'RESOLVED' | 'NOT_RESOLVED';
  reason: string | null;
  created_at: string;
}

export interface SafeSolution {
  revision_number: number;
  solution_summary: string;
  work_performed: string;
  testing_performed: string | null;
  limitations: string | null;
  status: string;
  submitted_at: string;
  evidence: {
    id: string;
    original_filename: string;
    mime_type: string;
    size_bytes: number;
    description: string | null;
  }[];
}

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  message: string;
  problem_id: string | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationList {
  items: AppNotification[];
  total: number;
  limit: number;
  offset: number;
}

export interface KnowledgeSkill {
  skill_id: string;
  name: string;
  relevance_score: number | null;
}

export interface KnowledgeEntrySummary {
  id: string;
  public_id: string;
  title: string;
  problem_preview: string;
  final_category: string | null;
  location_summary: string | null;
  skills: KnowledgeSkill[];
  resolution_duration_minutes: number | null;
  published_at: string | null;
  relevance: number | null;
  semantic_similarity: number | null;
  keyword_score: number | null;
}

export interface RelatedKnowledgeItem {
  entry: KnowledgeEntrySummary;
  semantic_similarity: number;
}

export interface KnowledgeEvidenceFile {
  file_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
}

export interface KnowledgeEntryDetail {
  id: string;
  public_id: string;
  title: string;
  problem_summary: string;
  final_category: string | null;
  location_summary: string | null;
  root_cause: string | null;
  solution_summary: string;
  work_performed: string;
  testing_performed: string | null;
  deployment_notes: string | null;
  known_limitations: string | null;
  skills: KnowledgeSkill[];
  resolution_duration_minutes: number | null;
  team_names: string[];
  mentor_name: string | null;
  mentor_designation: string | null;
  evidence_files: KnowledgeEvidenceFile[];
  published_at: string | null;
  related: RelatedKnowledgeItem[];
}

export interface KnowledgeSearchResponse {
  items: KnowledgeEntrySummary[];
  total: number;
  page: number;
  page_size: number;
  search_mode: string;
  semantic_available: boolean;
  error: string | null;
}

export interface RelatedSolutionsResponse {
  items: RelatedKnowledgeItem[];
  semantic_available: boolean;
}

export interface AdminKnowledgeEntry {
  id: string;
  public_id: string;
  problem_id: string;
  problem_ticket: string | null;
  title: string;
  publication_status: string;
  is_published: boolean;
  published_at: string | null;
  archived_at: string | null;
  failure_reason: string | null;
  created_at: string;
}

export interface SkillOption {
  id: string;
  name: string;
  category: string;
  normalized_name: string;
  created_at: string;
  updated_at: string;
}

export interface AnalyticsOverview {
  total_problems: number;
  open_problems: number;
  status_counts: Record<string, number>;
  high_priority: number;
  critical_priority: number;
  resolved_problems: number;
  avg_resolution_seconds: number | null;
  active_assignments: number;
  duplicate_clusters: number;
  published_knowledge: number;
}

export interface AnalyticsBucket {
  bucket: string;
  reported: number;
  resolved: number;
}

export interface AnalyticsCategory {
  category: string;
  count: number;
  percentage: number;
}

export interface AnalyticsHotIssue {
  problem_id: string;
  ticket_number: string;
  title: string;
  priority_level: string | null;
  priority_score: number | null;
  status: string;
  submitted_at: string | null;
}

export interface AnalyticsLocation {
  location: string;
  count: number;
  open_count: number;
  resolved_count: number;
  common_categories: string[];
}

export interface AnalyticsSkillRow {
  skill_id: string;
  name: string;
  category: string | null;
  problems: number;
  avg_relevance: number | null;
}

export interface AnalyticsModelQuality {
  available: boolean;
  label?: string;
  model_version?: string;
  base_model?: string;
  dataset_version?: string;
  train_samples?: number;
  val_samples?: number;
  test_samples?: number;
  test_accuracy?: number;
  macro_f1?: number;
  weighted_f1?: number;
  confidence_threshold?: number;
  per_class_f1?: { label: string; f1: number }[];
  note?: string;
}

export interface AnalyticsWorkItem {
  id: string;
  problem_id: string;
  title: string;
  due_date?: string | null;
  target_date?: string | null;
}

export interface AnalyticsDashboard {
  generated_at: string;
  filters: { date_from: string | null; date_to: string | null; category: string | null; location: string | null };
  overview: AnalyticsOverview;
  categories: { total: number; items: AnalyticsCategory[] };
  locations?: { items: AnalyticsLocation[] };
  priorities: {
    counts: Record<string, number>;
    average_score: number | null;
    high_critical_open: AnalyticsHotIssue[];
  };
  resolution: {
    count: number;
    average_seconds: number | null;
    median_seconds: number | null;
    min_seconds: number | null;
    max_seconds: number | null;
    p90_seconds: number | null;
  };
  duplicates: {
    confirmed_duplicate_problems: number;
    duplicate_reduction_ratio: number;
    active_clusters: number;
    average_reports_per_cluster: number;
    largest_cluster_size: number;
    pending_candidates: number;
    confirmed_candidates: number;
    rejected_candidates: number;
    confirmation_rate: number | null;
    avoided_assignments: number;
  };
  skill_demand: { items: AnalyticsSkillRow[] };
  workloads: {
    solvers: {
      by_availability: Record<string, { count: number; used: number; capacity: number }>;
      total_used: number;
      total_capacity: number;
      utilization: number;
    };
    mentors: {
      by_availability: Record<string, { count: number; used: number; capacity: number }>;
      total_used: number;
      total_capacity: number;
      utilization: number;
    };
    solver_workload_distribution: { current_workload: number; people: number }[];
    busiest_solvers: { name: string; current_workload: number; max_workload: number }[];
    busiest_mentors: { name: string; current_workload: number; max_workload: number }[];
  };
  assignments: {
    counts: Record<string, number>;
    total: number;
    team_override_count: number;
    team_override_rate: number | null;
    team_accepted_count: number;
    mentor_override_count: number;
    mentor_accepted_count: number;
    mentor_override_rate: number | null;
  };
  classification: {
    counts: Record<string, number>;
    total: number;
    low_confidence: number;
    low_confidence_rate: number | null;
    failed: number;
    reviewed: number;
    override_count: number;
    override_rate: number | null;
    model_quality: AnalyticsModelQuality;
  };
  verification: {
    resolved_confirmations: number;
    not_resolved_responses: number;
    reopen_rate: number | null;
    resolved_on_first_submission: number;
    average_revisions: number | null;
    mentor_changes_requested: number;
  };
  knowledge: {
    counts: Record<string, number>;
    published: number;
    archived: number;
    failed: number;
    top_categories: { category: string; count: number }[];
  };
  operations: {
    task_counts: Record<string, number>;
    blocked_tasks: AnalyticsWorkItem[];
    overdue_tasks: AnalyticsWorkItem[];
    milestone_counts: Record<string, number>;
    overdue_milestones: AnalyticsWorkItem[];
    upcoming_milestones: AnalyticsWorkItem[];
    pending_duplicate_reviews: number;
  };
}

export interface AnalyticsTrends {
  granularity: string;
  start: string;
  end: string;
  buckets: AnalyticsBucket[];
}
