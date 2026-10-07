# Complete Workflow

One campus problem, reporter to knowledge. Every transition below was executed
live in Steps 16–17.

| # | Step | Who | Backend service | DB state change | User sees |
|---|---|---|---|---|---|
| 1 | Submit report | Reporter | `ProblemService` | `problems` SUBMITTED + ticket | Ticket + success panel |
| 2 | AI classification | System | `ClassificationService` (DistilBERT) | `problem_classifications` row (status OK/LOW_CONFIDENCE/FAILED) | Category + confidence band |
| 3 | Priority scoring | System | `PriorityService` | `problem_priority_analyses` row | Level + score + reasons |
| 4 | Skill extraction | System | `SkillExtractionService` | `problem_skill_analyses` + `problem_required_skills` | Skill chips + relevance |
| 5 | Duplicate detection | System | `DuplicateService` | `problem_duplicate_candidates` (+ embeddings) | "Possible similar issue" (safe view) |
| 6 | Team recommendation | System | `TeamRecommendationService` | `team_recommendations` + members | 3 options + breakdown (admin sees workloads) |
| 7 | Mentor recommendation | System | `MentorRecommendationService` | `mentor_recommendations` | Ranked mentors + why |
| 8 | Admin review | Admin | workflow endpoints | UNDER_REVIEW; classification review sets `final_category` | Intake table, review panel |
| 9 | Approve / reject | Admin | approve / reject+reason | APPROVED or REJECTED | Status stepper advances |
| 10 | Assignment | Admin | `AssignmentService` (one transaction) | `problem_teams`+members, `problem_assignments`, workloads +1, status ASSIGNED | Assignment summary, notifications |
| 11 | Workspace | Solver/Mentor | `WorkspaceService` | tasks/milestones/files/discussion rows | Workspace boards |
| 12 | Tasks/milestones | Solver/Mentor | strict transitions | status flow, `problem_progress_updates` snapshots | Progress % (reporter sees % only) |
| 13 | Solution submit | Solver | `SolutionService` + readiness gate | `problem_solution_submissions` rev N | Revision history |
| 14 | Mentor review | Mentor | review endpoint | `mentor_solution_reviews`; CHANGES→IN_PROGRESS, APPROVE→AWAITING_VERIFICATION | Review thread |
| 15 | Reporter verification | Reporter | verifications endpoint | `problem_resolution_verifications`; NO→IN_PROGRESS, YES→RESOLVED+timestamp | Verify prompt |
| 16 | Close | Admin | close endpoint | CLOSED, workloads released once, retry 409 | Closed state |
| 17 | Knowledge publication | System | `KnowledgeService` | `knowledge_entries` + embeddings + entry-skills | KB article, searchable |
| 18 | Analytics | Admin | `AnalyticsService` | read-only aggregates | Dashboard + CSV |

Duplicate branch: admin confirms a candidate → `duplicate_clusters` +
`duplicate_cluster_members`, member status DUPLICATE, canonical priority
recount (+duplicate component). The member can never be independently
assigned (409). Reassignment/cancel release and re-apply workloads atomically.
