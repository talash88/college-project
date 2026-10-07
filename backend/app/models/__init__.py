from app.models.assignment import ProblemAssignment, ProblemTeam, ProblemTeamMember
from app.models.faculty_profile import FacultyProfile
from app.models.knowledge import KnowledgeEmbedding, KnowledgeEntry, KnowledgeEntrySkill
from app.models.notification import Notification
from app.models.problem import (
    Problem,
    ProblemActivity,
    ProblemAttachment,
    ProblemComment,
    TicketCounter,
)
from app.models.problem_analysis import (
    ProblemPriorityAnalysis,
    ProblemRequiredSkill,
    ProblemSkillAnalysis,
    SkillEmbedding,
)
from app.models.problem_classification import ProblemClassification
from app.models.problem_duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
    ProblemDuplicateCandidate,
    ProblemEmbedding,
)
from app.models.recommendation import (
    MentorRecommendation,
    TeamRecommendation,
    TeamRecommendationMember,
)
from app.models.refresh_token import RefreshToken
from app.models.skill import Skill
from app.models.solution import (
    MentorSolutionReview,
    ProblemResolutionVerification,
    ProblemSolutionSubmission,
)
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.models.user_skill import UserSkill
from app.models.workspace import (
    ProblemMilestone,
    ProblemProgressUpdate,
    ProblemTask,
    ProblemWorkAttachment,
)

__all__ = [
    "User",
    "StudentProfile",
    "FacultyProfile",
    "Skill",
    "UserSkill",
    "RefreshToken",
    "Problem",
    "ProblemAttachment",
    "ProblemActivity",
    "ProblemComment",
    "ProblemClassification",
    "ProblemEmbedding",
    "ProblemDuplicateCandidate",
    "DuplicateCluster",
    "DuplicateClusterMember",
    "ProblemPriorityAnalysis",
    "ProblemSkillAnalysis",
    "ProblemRequiredSkill",
    "SkillEmbedding",
    "TeamRecommendation",
    "TeamRecommendationMember",
    "MentorRecommendation",
    "ProblemTeam",
    "ProblemTeamMember",
    "ProblemAssignment",
    "ProblemTask",
    "ProblemMilestone",
    "ProblemProgressUpdate",
    "ProblemWorkAttachment",
    "KnowledgeEntry",
    "KnowledgeEntrySkill",
    "KnowledgeEmbedding",
    "ProblemSolutionSubmission",
    "MentorSolutionReview",
    "ProblemResolutionVerification",
    "Notification",
    "TicketCounter",
]
