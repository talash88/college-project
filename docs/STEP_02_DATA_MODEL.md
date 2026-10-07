# Step 2: Database Models, Users, Profiles & Skills

This document records the implementation of the CampusXolve AI data foundation layer.

## Entity Design Overview

```
┌─────────────┐       ┌──────────────────────┐       ┌─────────────────────┐
│    User     │───────│  StudentProfile      │       │    UserSkill        │
│             │  1:1  │                      │       │                     │
│ id (UUID)   │       │ user_id (FK)         │       │ user_id (FK)        │
│ email       │       │ student_identifier   │       │ skill_id (FK)       │
│ role        │       │ department           │       │ proficiency_level   │
│ password_hash│      │ academic_year        │       │ years_experience    │
│ is_active   │       │ semester             │       │ is_verified         │
│ is_verified │       │ availability_status  │       │                     │
└─────────────┘       │ current_workload     │       └──────────┬──────────┘
       │              │ max_workload         │                  │
       │ 1:1          └──────────────────────┘                  │
       │                                                       │
       ▼                                                       ▼
┌─────────────────────┐                              ┌─────────────────┐
│  FacultyProfile     │                              │     Skill       │
│                     │                              │                 │
│ user_id (FK)        │                              │ id (UUID)       │
│ employee_identifier │                              │ name            │
│ department          │                              │ normalized_name │
│ designation         │                              │ category        │
│ specialization      │                              │ description     │
│ availability_status │                              │ is_active       │
│ current_workload    │                              └─────────────────┘
│ max_workload        │
└─────────────────────┘
```

## Table Definitions

### 1. users
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() |
| full_name | VARCHAR(255) | NOT NULL |
| email | VARCHAR(255) | UNIQUE, NOT NULL, INDEX |
| password_hash | VARCHAR(255) | NOT NULL |
| role | user_role | NOT NULL, CHECK (REPORTER, SOLVER, MENTOR, ADMIN) |
| is_active | BOOLEAN | DEFAULT TRUE, NOT NULL |
| is_verified | BOOLEAN | DEFAULT FALSE, NOT NULL |
| created_at | TIMESTAMPTZ | DEFAULT now(), NOT NULL |
| updated_at | TIMESTAMPTZ | DEFAULT now(), NOT NULL |

**Indexes:**
- `ix_users_email` (UNIQUE) on email
- `ix_users_email_lower` (text_pattern_ops) on email for prefix searches

### 2. student_profiles
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY |
| user_id | UUID | FK → users.id ON DELETE CASCADE, UNIQUE |
| student_identifier | VARCHAR(50) | UNIQUE, NOT NULL, INDEX |
| department | department | NOT NULL |
| academic_year | INTEGER | NOT NULL, CHECK (1-5) |
| semester | INTEGER | NULLABLE, CHECK (1-8) |
| bio | VARCHAR(2000) | NULLABLE |
| availability_status | availability_status | DEFAULT AVAILABLE |
| current_workload | INTEGER | DEFAULT 0, CHECK (>= 0) |
| max_workload | INTEGER | DEFAULT 3, CHECK (> 0) |
| created_at | TIMESTAMPTZ | DEFAULT now() |
| updated_at | TIMESTAMPTZ | DEFAULT now() |

**Constraints:**
- `ck_student_profiles_current_workload_nonneg`: current_workload >= 0
- `ck_student_profiles_max_workload_pos`: max_workload > 0
- `ck_student_profiles_workload_valid`: current_workload <= max_workload

### 3. faculty_profiles
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY |
| user_id | UUID | FK → users.id ON DELETE CASCADE, UNIQUE |
| employee_identifier | VARCHAR(50) | UNIQUE, NOT NULL, INDEX |
| department | department | NOT NULL |
| designation | VARCHAR(100) | NOT NULL |
| specialization | VARCHAR(500) | NOT NULL |
| bio | VARCHAR(2000) | NULLABLE |
| availability_status | availability_status | DEFAULT AVAILABLE |
| current_workload | INTEGER | DEFAULT 0, CHECK (>= 0) |
| max_workload | INTEGER | DEFAULT 5, CHECK (> 0) |
| created_at | TIMESTAMPTZ | DEFAULT now() |
| updated_at | TIMESTAMPTZ | DEFAULT now() |

**Constraints:**
- `ck_faculty_profiles_current_workload_nonneg`: current_workload >= 0
- `ck_faculty_profiles_max_workload_pos`: max_workload > 0
- `ck_faculty_profiles_workload_valid`: current_workload <= max_workload

### 4. skills
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY |
| name | VARCHAR(100) | NOT NULL |
| normalized_name | VARCHAR(100) | UNIQUE, NOT NULL, INDEX |
| category | skill_category | NOT NULL |
| description | VARCHAR(1000) | NULLABLE |
| is_active | BOOLEAN | DEFAULT TRUE |
| created_at | TIMESTAMPTZ | DEFAULT now() |
| updated_at | TIMESTAMPTZ | DEFAULT now() |

### 5. user_skills
| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY |
| user_id | UUID | FK → users.id ON DELETE CASCADE |
| skill_id | UUID | FK → skills.id ON DELETE CASCADE |
| proficiency_level | INTEGER | NOT NULL, CHECK (1-5) |
| years_experience | INTEGER | NULLABLE, CHECK (>= 0) |
| is_verified | BOOLEAN | DEFAULT FALSE |
| created_at | TIMESTAMPTZ | DEFAULT now() |
| updated_at | TIMESTAMPTZ | DEFAULT now() |

**Constraints:**
- `uq_user_skills_user_skill`: UNIQUE (user_id, skill_id)
- `ck_user_skills_proficiency_range`: proficiency_level BETWEEN 1 AND 5
- `ck_user_skills_years_exp_nonneg`: years_experience >= 0

## Enums

### UserRole (PostgreSQL enum: user_role)
- `REPORTER` - Student/faculty/staff who can report campus problems
- `SOLVER` - Student who may be recommended/assigned to solve problems
- `MENTOR` - Faculty member who may supervise assigned teams
- `ADMIN` - Administrator who approves recommendations and controls workflow

### Department (PostgreSQL enum: department)
- `Computer Science & Engineering`
- `Information Technology`
- `Electronics`
- `Electrical`
- `Mechanical`
- `Civil`
- `Administration`
- `Other`

### AvailabilityStatus (PostgreSQL enum: availability_status)
- `AVAILABLE` - Currently available for assignments
- `LIMITED` - Limited availability
- `UNAVAILABLE` - Not available for assignments

### SkillCategory (PostgreSQL enum: skill_category)
- `Software Development`
- `AI / Data`
- `Infrastructure / Networking`
- `Hardware / Campus Technical`
- `Design`
- `General`

### ProficiencyLevel (PostgreSQL enum: proficiency_level)
- `1` = Beginner
- `2` = Basic
- `3` = Intermediate
- `4` = Advanced
- `5` = Expert

## Relationships

| From | To | Type | Cascade | Notes |
|------|-----|------|---------|-------|
| User | StudentProfile | One-to-One | DELETE CASCADE | Optional |
| User | FacultyProfile | One-to-One | DELETE CASCADE | Optional |
| User | UserSkill | One-to-Many | DELETE CASCADE | |
| Skill | UserSkill | One-to-Many | DELETE CASCADE | |

**Cascade Behavior:**
- Deleting a User cascades to StudentProfile, FacultyProfile, and UserSkill
- Deleting a Skill cascades to UserSkill
- UserSkill records are deleted when either User or Skill is deleted

## Constraints Summary

| Table | Constraint | Purpose |
|-------|------------|---------|
| users | UNIQUE (email) | Prevent duplicate emails |
| student_profiles | UNIQUE (student_identifier) | Unique student IDs |
| student_profiles | CHECK (current_workload >= 0) | No negative workload |
| student_profiles | CHECK (max_workload > 0) | Positive max workload |
| student_profiles | CHECK (current_workload <= max_workload) | Workload consistency |
| faculty_profiles | UNIQUE (employee_identifier) | Unique employee IDs |
| faculty_profiles | CHECK (current_workload >= 0) | No negative workload |
| faculty_profiles | CHECK (max_workload > 0) | Positive max workload |
| faculty_profiles | CHECK (current_workload <= max_workload) | Workload consistency |
| skills | UNIQUE (normalized_name) | Case-insensitive skill uniqueness |
| user_skills | UNIQUE (user_id, skill_id) | One skill per user |
| user_skills | CHECK (proficiency_level BETWEEN 1 AND 5) | Valid proficiency range |
| user_skills | CHECK (years_experience >= 0) | No negative experience |

## Indexes

| Table | Index | Purpose |
|-------|-------|---------|
| users | ix_users_email (UNIQUE) | Email lookups |
| users | ix_users_email_lower | Prefix email searches |
| student_profiles | ix_student_profiles_student_identifier (UNIQUE) | Student ID lookups |
| student_profiles | ix_student_profiles_department | Department filtering |
| student_profiles | ix_student_profiles_availability | Availability filtering |
| faculty_profiles | ix_faculty_profiles_employee_identifier (UNIQUE) | Employee ID lookups |
| faculty_profiles | ix_faculty_profiles_department | Department filtering |
| faculty_profiles | ix_faculty_profiles_availability | Availability filtering |
| skills | ix_skills_normalized_name (UNIQUE) | Skill name lookups |
| skills | ix_skills_category | Category filtering |
| skills | ix_skills_is_active | Active skill filtering |
| user_skills | ix_user_skills_user_id | User's skills |
| user_skills | ix_user_skills_skill_id | Skill's users |
| user_skills | ix_user_skills_proficiency | Proficiency filtering |

## Skill Taxonomy (46 skills seeded)

### Software Development (17)
- Frontend Development, Backend Development, Full Stack Development
- React, Next.js, JavaScript, TypeScript, HTML, CSS
- Python, FastAPI, Django
- REST API Development
- PostgreSQL, MongoDB, SQL

### AI / Data (8)
- Machine Learning, Natural Language Processing, Computer Vision
- Data Analysis, Data Visualization
- scikit-learn, PyTorch, TensorFlow

### Infrastructure / Networking (7)
- Computer Networking, Linux, System Administration
- Cybersecurity, Cloud Computing
- Docker, Git

### Hardware / Campus Technical (6)
- Hardware Troubleshooting, Electrical Maintenance, Electronics
- IoT, Embedded Systems, CCTV Systems

### Design (3)
- UI/UX Design, Graphic Design, Responsive Web Design

### General (6)
- Communication, Documentation, Research
- Problem Solving, Project Management, Team Leadership

## Development Users (7 accounts seeded)

| Email | Role | Password (dev only) |
|-------|------|---------------------|
| admin@campusxolve.local | ADMIN | dev_admin_123 |
| reporter@campusxolve.local | REPORTER | dev_reporter_123 |
| solver1@campusxolve.local | SOLVER | dev_solver_123 |
| solver2@campusxolve.local | SOLVER | dev_solver_123 |
| solver3@campusxolve.local | SOLVER | dev_solver_123 |
| mentor1@campusxolve.local | MENTOR | dev_mentor_123 |
| mentor2@campusxolve.local | MENTOR | dev_mentor_123 |

**Note:** All passwords are bcrypt-hashed. Never use these in production.

### Development Profiles

#### SOLVER 1 (solver1@campusxolve.local)
- Department: Computer Science & Engineering
- Student ID: CS2021001
- Year: 3, Semester: 6
- Skills: React (5), Next.js (5), TypeScript (5), UI/UX Design (4)

#### SOLVER 2 (solver2@campusxolve.local)
- Department: Computer Science & Engineering
- Student ID: CS2021002
- Year: 4, Semester: 8
- Skills: Python (5), FastAPI (5), Machine Learning (5), NLP (5)

#### SOLVER 3 (solver3@campusxolve.local)
- Department: Computer Science & Engineering
- Student ID: CS2021003
- Year: 3, Semester: 6
- Skills: PostgreSQL (5), Backend Development (5), Docker (4), Linux (4)

#### MENTOR 1 (mentor1@campusxolve.local)
- Department: Computer Science & Engineering
- Employee ID: FAC001
- Designation: Associate Professor
- Specialization: Artificial Intelligence / Machine Learning
- Skills: Machine Learning (5), NLP (5), Python (5)

#### MENTOR 2 (mentor2@campusxolve.local)
- Department: Computer Science & Engineering
- Employee ID: FAC002
- Designation: Professor
- Specialization: Computer Networks / Systems
- Skills: Computer Networking (5), Linux (5), Cybersecurity (5)

## Migration

**Migration ID:** 002_users_profiles_skills
**Revises:** 001 (initial)

Commands:
```bash
cd backend
python -m alembic upgrade head
```

Applied successfully on fresh database and upgraded from Step 1 database.

## Development APIs (Read-Only)

All endpoints prefixed with `/api/v1`:

### Users
- `GET /users` - List users (paginated)
- `GET /users/{user_id}` - Get user by ID
- `GET /users/{user_id}/student-profile` - Get student profile
- `GET /users/{user_id}/faculty-profile` - Get faculty profile
- `GET /users/{user_id}/skills` - Get user's skills with proficiency

### Skills
- `GET /skills` - List skills (filterable by category, active, search)
- `GET /skills/{skill_id}` - Get skill by ID

## Verification Results

### Backend Tests
- ✅ Foundation tests: 3/3 passed
- ✅ Type checking: `mypy app/` - Success
- ✅ Linting: Minor style issues (non-blocking)

### Database
- ✅ PostgreSQL connection: OK
- ✅ Migration 002 applied: OK
- ✅ All tables created: users, student_profiles, faculty_profiles, skills, user_skills
- ✅ Constraints verified: Unique, CHECK, FK constraints active

### Seed Scripts
- ✅ `seed_skills.py`: 46 skills seeded, idempotent (2nd run = 0 new)
- ✅ `seed_users.py`: 7 users + 4 student + 2 faculty + 18 skills assigned, idempotent

### pgvector
- ✅ Enabled: `CREATE EXTENSION vector` successful
- ✅ Health endpoint: `"pgvector_available": true`

### Step 1 Regression
- ✅ Health endpoint: `/api/v1/health` returns 200
- ✅ Root endpoint: `/api/v1/` returns 200
- ✅ API docs: `/docs` accessible

## Design Supporting Future Recommendation Algorithms

### Skill Matching
- `user_skills` table with proficiency_level (1-5) enables weighted matching
- `years_experience` provides additional signal
- `is_verified` flags mentor-validated skills

### Student Team Recommendation
- `StudentProfile.availability_status` filters available students
- `current_workload` vs `max_workload` prevents over-assignment
- `department` enables same-department team formation
- `academic_year`/`semester` enables peer-level grouping

### Faculty Mentor Recommendation
- `FacultyProfile.specialization` maps to problem domain
- `availability_status` + `current_workload` prevents mentor overload
- `skills` on mentors enable domain expertise matching

### Duplicate Detection (Future)
- Skills taxonomy provides vocabulary for keyword extraction
- Normalized skill names enable fuzzy matching

## Pydantic Schemas

All models have separate Create/Update/Response schemas:
- `UserCreate`, `UserUpdate`, `UserResponse`, `UserSummary`
- `StudentProfileCreate`, `StudentProfileUpdate`, `StudentProfileResponse`
- `FacultyProfileCreate`, `FacultyProfileUpdate`, `FacultyProfileResponse`
- `SkillCreate`, `SkillUpdate`, `SkillResponse`
- `UserSkillCreate`, `UserSkillUpdate`, `UserSkillResponse`, `UserSkillWithSkill`

**Security:** `password_hash` never exposed in response schemas.

## Repository/Service Layer

### Repositories
- `UserRepository` - CRUD + email lookup
- `StudentProfileRepository` - CRUD + student_identifier lookup
- `FacultyProfileRepository` - CRUD + employee_identifier lookup
- `UserSkillRepository` - CRUD + user/skill lookups
- `SkillRepository` - CRUD + normalized_name lookup + get_or_create

### Services
- `UserService` - Business logic for users, profiles, skills
- `SkillService` - Skill management + idempotent seeding
- `Security` - bcrypt password hashing/verification

## Remaining Limitations

1. **No Authentication Yet** - Development APIs are unprotected (Step 3)
2. **No Problem Domain Models** - Step 4 will add problems, teams, tasks
3. **No AI/ML Integration** - Step 5+ will add classification, embeddings
4. **Development Passwords** - Hardcoded bcrypt hashes, not for production
5. **Limited Validation** - API-level validation only, no frontend forms yet

## Next Step

**Step 3: Authentication & Authorization**
- JWT access/refresh tokens
- User registration & login
- Role-based access control (RBAC)
- Protected API routes
- Frontend authentication flow