# Abstract

CampusXolve AI is an AI-assisted web platform for reporting, resolving, and
remembering campus problems. Students file issues in plain language and
receive a tracked ticket; a locally hosted DistilBERT classifier categorizes
each report with an explicit confidence score, an explainable engine scores
priority from severity, affected users, age, category, and confirmed
duplicates, and a hybrid extractor identifies required skills. Semantic search
over MiniLM embeddings finds duplicate reports and recommends skilled student
teams with faculty mentors, but every consequential step — category correction,
duplicate confirmation, assignment, solution approval, and reporter
verification — is decided by a human, making the system auditable and safe.
Solved problems become a searchable knowledge repository, and analytics give
administrators an honest operational picture. Built with Next.js, FastAPI, and
PostgreSQL with pgvector, the system is verified by 266 automated tests,
role-based browser audits across desktop, tablet, and mobile, and a
production-style Docker deployment proven locally. On held-out development
data the classifier reaches 0.659 accuracy with weak safety/infrastructure
classes explicitly reported rather than hidden — the human review gates exist
because of these measured limits. The result is a working, explainable,
demo-ready platform for institutional complaint resolution. (271 words)
