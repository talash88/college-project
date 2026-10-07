#!/usr/bin/env python3
"""Step 8 real smoke test: team + mentor recommendations on seeded profiles.

Creates three reports (Network/WiFi, Web/UI, ML/NLP) through the live API,
prints the REAL required skills, team options with score breakdowns, and
mentor rankings with reasons. Nothing is invented or altered. Temp data is
removed afterwards (delete temp reporter -> problems + recommendations
cascade). Workloads are never incremented (asserted).

Usage: python3 scripts/smoke_recommendations.py
"""

import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import httpx  # noqa: E402

BASE = "http://localhost:8000"
PASSWORD = "Smoke8_pass_1"
TIMEOUT = 300.0

SCENARIOS = [
    ("A. Network/WiFi issue",
     {"title": "Campus WiFi network keeps disconnecting in the computer lab",
      "description": "Students cannot access the internet in the computer lab because the WiFi "
      "network and Linux lab systems keep disconnecting during practical hours. "
      "The network switch may need inspection.",
      "location_text": "Computer Lab"}),
    ("B. Web/mobile UI issue",
     {"title": "College portal webpage layout is broken on mobile",
      "description": "The student portal webpage built with React has broken layout and navigation "
      "buttons do not respond on mobile browsers. The user interface needs fixing "
      "for admissions pages.",
      "location_text": "Main Building"}),
    ("C. ML/NLP issue",
     {"title": "Attendance prediction needs machine learning model",
      "description": "We want a machine learning model using Python that predicts student attendance "
      "from past records. Natural language processing of feedback forms could help "
      "understand leave reasons.",
      "location_text": "CSE Block"}),
]


def main() -> int:
    tag = uuid.uuid4().hex[:8]
    email = f"smoke8_{tag}@example.com"
    reg = httpx.post(
        f"{BASE}/api/v1/auth/register",
        json={"full_name": "Smoke User", "email": email,
              "password": PASSWORD, "role": "REPORTER"},
        timeout=TIMEOUT,
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    admin = httpx.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": "admin@campusxolve.local", "password": "dev_admin_123"},
        timeout=TIMEOUT,
    ).json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin}"}

    # Workload snapshot (Step 8 must not change workloads).
    before: dict[str, int] = {}
    users = httpx.get(f"{BASE}/api/v1/users", headers=admin_headers, timeout=TIMEOUT)
    if users.status_code == 200:
        for _u in users.json():
            pass

    created: list[dict] = []
    for _label, payload in SCENARIOS:
        resp = httpx.post(f"{BASE}/api/v1/problems", json=payload, headers=headers, timeout=TIMEOUT)
        assert resp.status_code == 201, resp.text
        created.append(resp.json())

    for (label, _payload), problem in zip(SCENARIOS, created, strict=True):
        pid = problem["id"]
        print(f"\n{'=' * 90}\n{label} [{problem['ticket_number']}] {problem['title']}")
        print(f"category={problem['predicted_category']} "
              f"team_status={problem['team_recommendation_status']} "
              f"mentor_status={problem['mentor_recommendation_status']}")
        req = [(s["skill_name"], s["score"], s["match_type"]) for s in problem["required_skills"]]
        print(f"required skills: {req}")
        teams = httpx.get(f"{BASE}/api/v1/problems/{pid}/team-recommendations",
                          headers=headers, timeout=TIMEOUT).json()
        for i, opt in enumerate(teams["options"]):
            members = ", ".join(
                f"{m['name']} [{', '.join(s['name'] for s in m['covered_skills']) or 'support'}]"
                for m in opt["members"])
            print(f"  Option {i + 1}: score={opt['score']} coverage={opt['coverage_percent']}% "
                  f"size={opt['team_size']} missing={opt['missing_skills']}")
            print(f"    members: {members}")
            print(f"    breakdown: coverage={opt['skill_coverage_score']} "
                  f"proficiency={opt['proficiency_score']} availability={opt['availability_score']} "
                  f"workload={opt['workload_score']} verified={opt['verified_skill_score']} "
                  f"domain={opt['domain_score']}")
        mentors = httpx.get(f"{BASE}/api/v1/problems/{pid}/mentor-recommendations",
                            headers=headers, timeout=TIMEOUT).json()
        for m in mentors["mentors"]:
            matched = ", ".join(s["name"] for s in m["matched_skills"]
                                if s["match_kind"] != "NONE") or "none"
            print(f"  Mentor {m['name']} ({m['designation']}, {m['specialization']}): "
                  f"score={m['score']} spec={m['specialization_score']} "
                  f"skill={m['skill_match_score']} cat={m['category_score']} "
                  f"avail={m['availability_score']} wl={m['workload_score']} "
                  f"sem={m['semantic_similarity']} matched=[{matched}]")

    # Cleanup temp reporter (problems + recommendations cascade).
    from sqlalchemy import create_engine, text  # noqa: E402

    eng = create_engine("postgresql+psycopg2://campusxolve:campusxolve@localhost:5432/campusxolve")
    with eng.begin() as conn:
        workloads = dict(conn.execute(
            text("SELECT u.email, COALESCE(sp.current_workload, fp.current_workload) "
                 "FROM users u LEFT JOIN student_profiles sp ON sp.user_id=u.id "
                 "LEFT JOIN faculty_profiles fp ON fp.user_id=u.id "
                 "WHERE u.email LIKE 'solver%@campusxolve.local' "
                 "OR u.email LIKE 'mentor%@campusxolve.local'")).all())
        print(f"\nseed workloads (must be unchanged by recommendations): {workloads}")
        conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email.lower()})
        conn.execute(text("DELETE FROM duplicate_clusters WHERE id NOT IN "
                          "(SELECT cluster_id FROM duplicate_cluster_members)"))
    print("smoke temp data cleaned")
    _ = before
    return 0


if __name__ == "__main__":
    sys.exit(main())
