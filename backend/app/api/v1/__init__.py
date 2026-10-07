from app.api.v1.admin import candidates_router as admin_candidates_router
from app.api.v1.admin import clusters_router as admin_clusters_router
from app.api.v1.admin import recommendations_router as admin_recommendations_router
from app.api.v1.admin import router as admin_router
from app.api.v1.admin import workflow_router as admin_workflow_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.development import router as development_router
from app.api.v1.development import skill_router
from app.api.v1.health import router as health_router
from app.api.v1.knowledge import admin_router as knowledge_admin_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.problems import router as problems_router
from app.api.v1.profile import router as profile_router
from app.api.v1.solutions import router as solutions_router
from app.api.v1.workspace import router as workspace_router

__all__ = [
    "health_router",
    "development_router",
    "skill_router",
    "auth_router",
    "profile_router",
    "problems_router",
    "workspace_router",
    "solutions_router",
    "notifications_router",
    "knowledge_router",
    "knowledge_admin_router",
    "analytics_router",
    "admin_router",
    "admin_candidates_router",
    "admin_clusters_router",
    "admin_recommendations_router",
    "admin_workflow_router",
]
