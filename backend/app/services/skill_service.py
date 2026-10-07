from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SkillCategory
from app.models.skill import Skill
from app.repositories.skill_repository import SkillRepository, normalize_skill_name
from app.schemas.skill import SkillCreate, SkillUpdate

if TYPE_CHECKING:
    from app.repositories.skill_repository import SkillRepository


class SkillService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.skill_repo = SkillRepository(session)

    async def create_skill(self, skill_data: SkillCreate) -> Skill:
        try:
            skill = await self.skill_repo.create(skill_data)
            await self.session.commit()
            return skill
        except IntegrityError as e:
            await self.session.rollback()
            if "uq_skills_normalized_name" in str(e):
                raise ValueError("Skill with this name already exists") from e
            raise

    async def get_skill(self, skill_id: UUID) -> Skill | None:
        return await self.skill_repo.get_by_id(skill_id)

    async def get_skill_by_name(self, name: str) -> Skill | None:
        return await self.skill_repo.get_by_normalized_name(normalize_skill_name(name))

    async def list_skills(
        self,
        skip: int = 0,
        limit: int = 100,
        category: SkillCategory | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> list[Skill]:
        return await self.skill_repo.get_all(skip=skip, limit=limit, category=category, is_active=is_active, search=search)

    async def count_skills(
        self,
        category: SkillCategory | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> int:
        return await self.skill_repo.count_all(category=category, is_active=is_active, search=search)

    async def update_skill(self, skill_id: UUID, skill_data: SkillUpdate) -> Skill | None:
        skill = await self.skill_repo.update(skill_id, skill_data)
        if skill:
            await self.session.commit()
        return skill

    async def delete_skill(self, skill_id: UUID) -> bool:
        result = await self.skill_repo.delete(skill_id)
        if result:
            await self.session.commit()
        return result

    async def get_or_create_skill(self, name: str, category: SkillCategory, description: str | None = None) -> Skill:
        """Idempotent skill creation - returns existing or creates new."""
        skill = await self.skill_repo.get_or_create_by_name(name, category, description)
        await self.session.commit()
        return skill

    async def seed_skills(self) -> list[Skill]:
        """Seed the initial skill taxonomy. Idempotent."""
        skills_to_seed = [
            # SOFTWARE DEVELOPMENT
            ("Frontend Development", SkillCategory.SOFTWARE_DEVELOPMENT, "Building user interfaces and client-side applications"),
            ("Backend Development", SkillCategory.SOFTWARE_DEVELOPMENT, "Server-side logic, APIs, and database design"),
            ("Full Stack Development", SkillCategory.SOFTWARE_DEVELOPMENT, "End-to-end web application development"),
            ("React", SkillCategory.SOFTWARE_DEVELOPMENT, "React.js library for building user interfaces"),
            ("Next.js", SkillCategory.SOFTWARE_DEVELOPMENT, "React framework for production applications"),
            ("JavaScript", SkillCategory.SOFTWARE_DEVELOPMENT, "JavaScript programming language"),
            ("TypeScript", SkillCategory.SOFTWARE_DEVELOPMENT, "Typed superset of JavaScript"),
            ("HTML", SkillCategory.SOFTWARE_DEVELOPMENT, "HyperText Markup Language"),
            ("CSS", SkillCategory.SOFTWARE_DEVELOPMENT, "Cascading Style Sheets"),
            ("Python", SkillCategory.SOFTWARE_DEVELOPMENT, "Python programming language"),
            ("FastAPI", SkillCategory.SOFTWARE_DEVELOPMENT, "Modern Python web framework for APIs"),
            ("Django", SkillCategory.SOFTWARE_DEVELOPMENT, "High-level Python web framework"),
            ("REST API Development", SkillCategory.SOFTWARE_DEVELOPMENT, "Designing and implementing RESTful APIs"),
            ("PostgreSQL", SkillCategory.SOFTWARE_DEVELOPMENT, "Advanced open-source relational database"),
            ("MongoDB", SkillCategory.SOFTWARE_DEVELOPMENT, "Document-oriented NoSQL database"),
            ("SQL", SkillCategory.SOFTWARE_DEVELOPMENT, "Structured Query Language for databases"),

            # AI / DATA
            ("Machine Learning", SkillCategory.AI_DATA, "Algorithms that learn from data"),
            ("Natural Language Processing", SkillCategory.AI_DATA, "Processing and understanding human language"),
            ("Computer Vision", SkillCategory.AI_DATA, "Enabling computers to interpret visual data"),
            ("Data Analysis", SkillCategory.AI_DATA, "Inspecting, cleaning, and modeling data"),
            ("Data Visualization", SkillCategory.AI_DATA, "Graphical representation of data"),
            ("scikit-learn", SkillCategory.AI_DATA, "Machine learning library for Python"),
            ("PyTorch", SkillCategory.AI_DATA, "Open-source machine learning framework"),
            ("TensorFlow", SkillCategory.AI_DATA, "End-to-end open-source ML platform"),

            # INFRASTRUCTURE / NETWORKING
            ("Computer Networking", SkillCategory.INFRASTRUCTURE_NETWORKING, "Network protocols, routing, and infrastructure"),
            ("Linux", SkillCategory.INFRASTRUCTURE_NETWORKING, "Linux system administration and scripting"),
            ("System Administration", SkillCategory.INFRASTRUCTURE_NETWORKING, "Managing and maintaining computer systems"),
            ("Cybersecurity", SkillCategory.INFRASTRUCTURE_NETWORKING, "Protecting systems and networks from threats"),
            ("Cloud Computing", SkillCategory.INFRASTRUCTURE_NETWORKING, "Cloud platforms and services (AWS, GCP, Azure)"),
            ("Docker", SkillCategory.INFRASTRUCTURE_NETWORKING, "Containerization platform"),
            ("Git", SkillCategory.INFRASTRUCTURE_NETWORKING, "Distributed version control system"),

            # HARDWARE / CAMPUS TECHNICAL
            ("Hardware Troubleshooting", SkillCategory.HARDWARE_CAMPUS_TECHNICAL, "Diagnosing and fixing hardware issues"),
            ("Electrical Maintenance", SkillCategory.HARDWARE_CAMPUS_TECHNICAL, "Maintaining electrical systems and equipment"),
            ("Electronics", SkillCategory.HARDWARE_CAMPUS_TECHNICAL, "Electronic circuits and components"),
            ("IoT", SkillCategory.HARDWARE_CAMPUS_TECHNICAL, "Internet of Things devices and protocols"),
            ("Embedded Systems", SkillCategory.HARDWARE_CAMPUS_TECHNICAL, "Microcontroller and embedded programming"),
            ("CCTV Systems", SkillCategory.HARDWARE_CAMPUS_TECHNICAL, "Video surveillance system installation and maintenance"),

            # DESIGN
            ("UI/UX Design", SkillCategory.DESIGN, "User interface and user experience design"),
            ("Graphic Design", SkillCategory.DESIGN, "Visual communication and design"),
            ("Responsive Web Design", SkillCategory.DESIGN, "Designing for multiple screen sizes"),

            # GENERAL
            ("Communication", SkillCategory.GENERAL, "Effective verbal and written communication"),
            ("Documentation", SkillCategory.GENERAL, "Technical writing and documentation"),
            ("Research", SkillCategory.GENERAL, "Information gathering and analysis"),
            ("Problem Solving", SkillCategory.GENERAL, "Analytical and creative problem solving"),
            ("Project Management", SkillCategory.GENERAL, "Planning and executing projects"),
            ("Team Leadership", SkillCategory.GENERAL, "Leading and coordinating teams"),
        ]

        seeded = []
        for name, category, description in skills_to_seed:
            skill = await self.get_or_create_skill(name, category, description)
            seeded.append(skill)

        return seeded
