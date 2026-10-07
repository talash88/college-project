"""Controlled skill aliases for exact/phrase matching.

Small, curated, campus-relevant. Generic words that would misfire
("design", "system", "management", ...) live in EXCLUDE_GENERIC and are
never used as match phrases, even if listed below.
"""

# skill name -> aliases (all matched case-insensitively, word boundaries)
SKILL_ALIASES: dict[str, list[str]] = {
    "Frontend Development": ["frontend", "front-end", "client-side", "user interface development"],
    "Backend Development": ["backend", "back-end", "server-side", "server side"],
    "Full Stack Development": ["full stack", "full-stack"],
    "React": ["react", "reactjs", "react.js"],
    "Next.js": ["nextjs", "next.js"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript", "ts"],
    "HTML": ["html", "webpage markup"],
    "CSS": ["css", "stylesheet", "stylesheets"],
    "Responsive Web Design": ["responsive", "mobile-friendly", "mobile friendly", "mobile layout"],
    "UI/UX Design": ["ui/ux", "user experience", "ux design", "interface design"],
    "Graphic Design": ["graphic design", "poster design", "photoshop", "illustrator"],
    "Django": ["django"],
    "FastAPI": ["fastapi", "fast api"],
    "REST API Development": ["rest api", "restful", "restful api", "api development"],
    "Python": ["python"],
    "SQL": ["sql", "database query", "database queries"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo"],
    "Machine Learning": ["machine learning", "ml model", "ml models"],
    "Natural Language Processing": ["nlp", "natural language"],
    "Computer Vision": ["computer vision", "image recognition", "opencv"],
    "Data Analysis": ["data analysis", "data analytics"],
    "Data Visualization": ["data visualization", "dashboard", "charts"],
    "PyTorch": ["pytorch", "torch"],
    "TensorFlow": ["tensorflow"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "Computer Networking": [
        "network",
        "networking",
        "wi-fi",
        "wifi",
        "wireless",
        "wifi hotspot",
        "lan",
        "router",
        "routers",
        "internet connectivity",
    ],
    "System Administration": ["system administration", "sysadmin", "server administration"],
    "Linux": ["linux", "ubuntu"],
    "Docker": ["docker", "container", "containers", "containerization"],
    "Cloud Computing": ["cloud", "aws", "azure", "gcp"],
    "Git": ["git", "version control"],
    "Cybersecurity": ["cybersecurity", "cyber security", "hacking", "phishing", "malware"],
    "CCTV Systems": [
        "cctv",
        "surveillance camera",
        "surveillance cameras",
        "security camera",
        "security cameras",
    ],
    "Hardware Troubleshooting": [
        "hardware",
        "troubleshoot",
        "troubleshooting",
        "repair",
        "faulty equipment",
    ],
    "Electrical Maintenance": [
        "electrical",
        "wiring",
        "electrician",
        "electrical work",
        "switchboard",
    ],
    "Electronics": ["electronics", "circuit", "circuits", "oscilloscope", "microcontroller"],
    "Embedded Systems": ["embedded", "microcontroller", "arduino", "raspberry pi", "iot device"],
    "IoT": ["iot", "internet of things", "smart device", "smart devices", "sensor", "sensors"],
    "Communication": ["communication", "announcement", "notice drafting"],
    "Documentation": ["documentation", "technical writing", "manual", "user guide"],
    "Problem Solving": ["problem solving", "troubleshoot", "troubleshooting", "diagnose"],
    "Project Management": ["project management", "planning", "coordination", "scheduling"],
    "Team Leadership": ["team leadership", "team lead", "leading a team"],
    "Research": ["research", "survey", "literature review", "case study"],
}

# Generic words that must never trigger an exact match on their own.
EXCLUDE_GENERIC = frozenset(
    {
        "design",
        "system",
        "systems",
        "service",
        "services",
        "management",
        "support",
        "general",
        "development",
        "application",
        "applications",
        "data",
        "network",
    }
)

# Problem category -> skill categories that get a small relevance bonus.
CATEGORY_SKILL_BONUS: dict[str, set[str]] = {
    "IT_NETWORK": {"Infrastructure / Networking", "Software Development"},
    "LABORATORY": {"Hardware / Campus Technical", "Software Development", "AI / Data"},
    "ELECTRICAL": {"Hardware / Campus Technical"},
    "SAFETY_SECURITY": {"Hardware / Campus Technical", "Infrastructure / Networking"},
    "LIBRARY": {"Software Development", "Infrastructure / Networking"},
    "ACADEMIC": {"General", "Software Development"},
    "WATER_SANITATION": {"Hardware / Campus Technical"},
    "INFRASTRUCTURE": {"Hardware / Campus Technical", "Infrastructure / Networking"},
    "CLEANLINESS_SANITATION": {"General"},
    "HOSTEL": {"General", "Hardware / Campus Technical"},
    "TRANSPORT": {"General"},
    "OTHER": set(),
}


# Typical complaint wordings, used ONLY to enrich the embedded representation
# text (never for exact matching). Kept small and campus-specific: complaint
# vocabulary often differs from technical vocabulary ("wifi disconnects" vs
# "TCP/IP troubleshooting").
SKILL_CONTEXT: dict[str, list[str]] = {
    "Computer Networking": [
        "wifi keeps disconnecting",
        "no internet access",
        "internet is very slow",
        "connection drops frequently",
    ],
    "System Administration": [
        "server is down",
        "systems are very slow",
        "computer keeps hanging",
    ],
    "Linux": [
        "server administration",
        "command line setup",
    ],
    "Electrical Maintenance": [
        "sparking switchboard",
        "power cut",
        "fused lights",
        "short circuit",
    ],
    "Hardware Troubleshooting": [
        "computer does not start",
        "system not booting",
        "printer not working",
    ],
    "CCTV Systems": [
        "camera is offline",
        "camera stopped recording",
    ],
    "Responsive Web Design": [
        "website unusable on mobile phones",
        "page layout broken on small screens",
    ],
    "UI/UX Design": [
        "portal is confusing to use",
        "website navigation is difficult",
    ],
}


def aliases_for(skill_name: str) -> list[str]:
    return SKILL_ALIASES.get(skill_name, [])


def usable_phrases(skill_name: str) -> list[str]:
    """Aliases safe for exact matching (drops generic single words)."""
    phrases: list[str] = []
    for alias in [skill_name, *aliases_for(skill_name)]:
        text = alias.strip().lower()
        if not text or len(text) < 3:
            continue
        if " " not in text and text in EXCLUDE_GENERIC:
            continue
        if text not in phrases:
            phrases.append(text)
    return phrases


def representation_text(skill_name: str, category: str, description: str | None) -> str:
    """Semantic text embedded for a skill: name + category + description + aliases."""
    parts = [skill_name, f"Category: {category}."]
    if description and description.strip():
        parts.append(description.strip())
    alias_list = aliases_for(skill_name)
    if alias_list:
        parts.append("Related terms: " + ", ".join(alias_list) + ".")
    context = SKILL_CONTEXT.get(skill_name, [])
    if context:
        parts.append("Typical complaints: " + " / ".join(context) + ".")
    return "\n".join(parts)
