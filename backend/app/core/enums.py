import enum


class UserRole(enum.StrEnum):
    REPORTER = "REPORTER"
    SOLVER = "SOLVER"
    MENTOR = "MENTOR"
    ADMIN = "ADMIN"


class Department(enum.StrEnum):
    COMPUTER_SCIENCE_ENGINEERING = "Computer Science & Engineering"
    INFORMATION_TECHNOLOGY = "Information Technology"
    ELECTRONICS = "Electronics"
    ELECTRICAL = "Electrical"
    MECHANICAL = "Mechanical"
    CIVIL = "Civil"
    ADMINISTRATION = "Administration"
    OTHER = "Other"


class AvailabilityStatus(enum.StrEnum):
    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


class SkillCategory(enum.StrEnum):
    SOFTWARE_DEVELOPMENT = "Software Development"
    AI_DATA = "AI / Data"
    INFRASTRUCTURE_NETWORKING = "Infrastructure / Networking"
    HARDWARE_CAMPUS_TECHNICAL = "Hardware / Campus Technical"
    DESIGN = "Design"
    GENERAL = "General"


class ProficiencyLevel(int, enum.Enum):
    BEGINNER = 1
    BASIC = 2
    INTERMEDIATE = 3
    ADVANCED = 4
    EXPERT = 5


class ProblemStatus(enum.StrEnum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_VERIFICATION = "AWAITING_VERIFICATION"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    WITHDRAWN = "WITHDRAWN"


class ProblemEventType(enum.StrEnum):
    SUBMITTED = "SUBMITTED"
    EDITED = "EDITED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    ATTACHMENT_REMOVED = "ATTACHMENT_REMOVED"
    COMMENT_ADDED = "COMMENT_ADDED"
    DUPLICATE_ANALYSIS_COMPLETED = "DUPLICATE_ANALYSIS_COMPLETED"
    DUPLICATE_CONFIRMED = "DUPLICATE_CONFIRMED"
    DUPLICATE_REJECTED = "DUPLICATE_REJECTED"
    JOINED_DUPLICATE_CLUSTER = "JOINED_DUPLICATE_CLUSTER"
    DUPLICATE_CLUSTER_MERGED = "DUPLICATE_CLUSTER_MERGED"
    TEAM_RECOMMENDATION_COMPLETED = "TEAM_RECOMMENDATION_COMPLETED"
    MENTOR_RECOMMENDATION_COMPLETED = "MENTOR_RECOMMENDATION_COMPLETED"
    REVIEW_STARTED = "REVIEW_STARTED"
    PROBLEM_APPROVED = "PROBLEM_APPROVED"
    PROBLEM_REJECTED = "PROBLEM_REJECTED"
    TEAM_CREATED = "TEAM_CREATED"
    TEAM_ASSIGNED = "TEAM_ASSIGNED"
    MENTOR_ASSIGNED = "MENTOR_ASSIGNED"
    ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    ASSIGNMENT_UPDATED = "ASSIGNMENT_UPDATED"
    ASSIGNMENT_CANCELLED = "ASSIGNMENT_CANCELLED"
    WORK_STARTED = "WORK_STARTED"
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_BLOCKED = "TASK_BLOCKED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_REASSIGNED = "TASK_REASSIGNED"
    TASK_UPDATED = "TASK_UPDATED"
    MILESTONE_CREATED = "MILESTONE_CREATED"
    MILESTONE_STARTED = "MILESTONE_STARTED"
    MILESTONE_COMPLETED = "MILESTONE_COMPLETED"
    MILESTONE_MISSED = "MILESTONE_MISSED"
    PROGRESS_UPDATED = "PROGRESS_UPDATED"
    WORK_FILE_ADDED = "WORK_FILE_ADDED"
    WORK_FILE_REMOVED = "WORK_FILE_REMOVED"
    SOLUTION_SUBMITTED = "SOLUTION_SUBMITTED"
    MENTOR_CHANGES_REQUESTED = "MENTOR_CHANGES_REQUESTED"
    MENTOR_SOLUTION_APPROVED = "MENTOR_SOLUTION_APPROVED"
    REPORTER_VERIFICATION_REQUESTED = "REPORTER_VERIFICATION_REQUESTED"
    REPORTER_CONFIRMED_RESOLUTION = "REPORTER_CONFIRMED_RESOLUTION"
    REPORTER_REJECTED_RESOLUTION = "REPORTER_REJECTED_RESOLUTION"
    PROBLEM_RESOLVED = "PROBLEM_RESOLVED"
    PROBLEM_CLOSED = "PROBLEM_CLOSED"
    KNOWLEDGE_ENTRY_PUBLISHED = "KNOWLEDGE_ENTRY_PUBLISHED"
    KNOWLEDGE_PUBLICATION_FAILED = "KNOWLEDGE_PUBLICATION_FAILED"
    KNOWLEDGE_ENTRY_ARCHIVED = "KNOWLEDGE_ENTRY_ARCHIVED"
    KNOWLEDGE_ENTRY_REPUBLISHED = "KNOWLEDGE_ENTRY_REPUBLISHED"


class DuplicateDecisionStatus(enum.StrEnum):
    PENDING = "PENDING"
    CONFIRMED_DUPLICATE = "CONFIRMED_DUPLICATE"
    REJECTED = "REJECTED"
    STALE = "STALE"


class DuplicateAnalysisStatus(enum.StrEnum):
    NOT_RUN = "NOT_RUN"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NO_MATCHES = "NO_MATCHES"
    POSSIBLE_DUPLICATES = "POSSIBLE_DUPLICATES"


class RecommendationStatus(enum.StrEnum):
    """Per-problem team/mentor recommendation lifecycle (Step 8)."""

    NOT_RUN = "NOT_RUN"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    NO_ELIGIBLE_CANDIDATES = "NO_ELIGIBLE_CANDIDATES"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAILED = "FAILED"


class AssignmentStatus(enum.StrEnum):
    """ProblemAssignment lifecycle (Step 9). Only one ACTIVE per problem."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REASSIGNED = "REASSIGNED"


class ClassificationStatus(enum.StrEnum):
    NOT_RUN = "NOT_RUN"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    FAILED = "FAILED"


class TaskStatus(enum.StrEnum):
    """ProblemTask lifecycle (Step 10)."""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskPriority(enum.StrEnum):
    """ProblemTask priority (Step 10)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MilestoneStatus(enum.StrEnum):
    """ProblemMilestone lifecycle (Step 10)."""

    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


# Central task transition table: action-free, state-to-state allow-list.
# DONE reopening is intentionally absent: only mentor/admin may reopen via
# the explicit `reopen` path in the workspace service.
TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.TODO: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset(
        {TaskStatus.BLOCKED, TaskStatus.DONE, TaskStatus.TODO, TaskStatus.CANCELLED}
    ),
    TaskStatus.BLOCKED: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

# Milestone transition allow-list. COMPLETED/MISSED/CANCELLED are terminal;
# only mentor/admin may move milestones at all (enforced in the service).
MILESTONE_TRANSITIONS: dict[MilestoneStatus, frozenset[MilestoneStatus]] = {
    MilestoneStatus.PLANNED: frozenset(
        {MilestoneStatus.IN_PROGRESS, MilestoneStatus.COMPLETED, MilestoneStatus.CANCELLED}
    ),
    MilestoneStatus.IN_PROGRESS: frozenset(
        {
            MilestoneStatus.COMPLETED,
            MilestoneStatus.MISSED,
            MilestoneStatus.CANCELLED,
            MilestoneStatus.PLANNED,
        }
    ),
    MilestoneStatus.MISSED: frozenset({MilestoneStatus.IN_PROGRESS, MilestoneStatus.CANCELLED}),
    MilestoneStatus.COMPLETED: frozenset(),
    MilestoneStatus.CANCELLED: frozenset(),
}


# Reports in these statuses are terminal: owners can no longer edit/withdraw them.
TERMINAL_PROBLEM_STATUSES = frozenset(
    {
        ProblemStatus.RESOLVED,
        ProblemStatus.CLOSED,
        ProblemStatus.REJECTED,
        ProblemStatus.DUPLICATE,
        ProblemStatus.WITHDRAWN,
    }
)


class SolutionStatus(enum.StrEnum):
    """ProblemSolutionSubmission lifecycle (Step 11)."""

    SUBMITTED = "SUBMITTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    MENTOR_APPROVED = "MENTOR_APPROVED"
    REPORTER_REJECTED = "REPORTER_REJECTED"
    VERIFIED = "VERIFIED"


class ReviewDecision(enum.StrEnum):
    """MentorSolutionReview decision (Step 11)."""

    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class VerificationDecision(enum.StrEnum):
    """ProblemResolutionVerification decision (Step 11)."""

    RESOLVED = "RESOLVED"
    NOT_RESOLVED = "NOT_RESOLVED"


class NotificationType(enum.StrEnum):
    """Controlled in-app notification vocabulary (Step 11).

    Only a subset is emitted today (see NotificationService); the rest of
    the vocabulary is reserved so future hooks do not invent ad-hoc types.
    """

    PROBLEM_SUBMITTED = "PROBLEM_SUBMITTED"
    PROBLEM_REVIEW_STARTED = "PROBLEM_REVIEW_STARTED"
    PROBLEM_APPROVED = "PROBLEM_APPROVED"
    PROBLEM_REJECTED = "PROBLEM_REJECTED"
    DUPLICATE_CONFIRMED = "DUPLICATE_CONFIRMED"
    TEAM_ASSIGNED = "TEAM_ASSIGNED"
    MENTOR_ASSIGNED = "MENTOR_ASSIGNED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_BLOCKED = "TASK_BLOCKED"
    SOLUTION_SUBMITTED = "SOLUTION_SUBMITTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    MENTOR_APPROVED = "MENTOR_APPROVED"
    REPORTER_VERIFICATION_REQUIRED = "REPORTER_VERIFICATION_REQUIRED"
    REPORTER_REJECTED_RESOLUTION = "REPORTER_REJECTED_RESOLUTION"
    PROBLEM_RESOLVED = "PROBLEM_RESOLVED"
    PROBLEM_CLOSED = "PROBLEM_CLOSED"
