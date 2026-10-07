#!/usr/bin/env python3
"""Step 9 real E2E smoke: review -> approve -> assign (+override +failure).

Runs the full workflow through the live API with real seeded profiles and
prints measured workloads before/after. Temp data is removed afterwards.
Nothing is faked: every state comes from the database.

Usage: python3 scripts/smoke_assignment.py
"""

import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import httpx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

BASE = "http://localhost:8000"
PASSWORD = "Smoke9_pass_1"
TIMEOUT = 300.0

REPORT = {
    "title": "Campus WiFi network keeps disconnecting in the computer lab",
    "description": "Students cannot access the internet in the computer lab because the WiFi "
    "network and Linux lab systems keep disconnecting during practical hours. "
    "The network switch may need inspection.",
    "location_text": "Computer Lab",
}

REPORT2 = {
    "title": "Library computers cannot reach the internet during lab hours",
    "description": "The library computer systems lose network and internet access every afternoon, "
    "and Linux terminals show disconnected status. Students cannot complete online coursework.",
    "location_text": "Library Computer Section",
}

eng = create_engine("postgresql+psycopg2://campusxolve:campusxolve@localhost:5432/campusxolve")


def workloads(*emails: str) -> dict[str, str]:
    with eng.begin() as conn:
        rows = conn.execute(
            text("SELECT u.email, COALESCE(sp.current_workload, fp.current_workload), "
                 "COALESCE(sp.max_workload, fp.max_workload) FROM users u "
                 "LEFT JOIN student_profiles sp ON sp.user_id=u.id "
                 "LEFT JOIN faculty_profiles fp ON fp.user_id=u.id "
                 "WHERE u.email IN :emails"),
            {"emails": tuple(e.lower() for e in emails)},
        ).all()
    return {r[0]: f"{r[1]}/{r[2]}" for r in rows}


def main() -> int:
    # Hermetic smoke: drop leftovers from interrupted runs and reset seed
    # workloads to their repo baseline (solver3 starts 1/3 LIMITED).
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email LIKE 'smoke9\\_%' ESCAPE '\\'"))
        conn.execute(text("DELETE FROM duplicate_clusters WHERE id NOT IN "
                          "(SELECT cluster_id FROM duplicate_cluster_members)"))
        baselines = {"solver1@campusxolve.local": 0, "solver2@campusxolve.local": 0,
                     "solver3@campusxolve.local": 1,
                     "mentor1@campusxolve.local": 0, "mentor2@campusxolve.local": 0}
        for email, load in baselines.items():
            conn.execute(
                text("UPDATE student_profiles SET current_workload=:l WHERE user_id=("
                     "SELECT id FROM users WHERE email=:e)"), {"l": load, "e": email})
            conn.execute(
                text("UPDATE faculty_profiles SET current_workload=:l WHERE user_id=("
                     "SELECT id FROM users WHERE email=:e)"), {"l": load, "e": email})
    tag = uuid.uuid4().hex[:8]
    email = f"smoke9_{tag}@example.com"
    reg = httpx.post(
        f"{BASE}/api/v1/auth/register",
        json={"full_name": "Smoke Reporter", "email": email,
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

    # ---------- Report 1: accept recommendations ----------
    p1 = httpx.post(f"{BASE}/api/v1/problems", json=REPORT, headers=headers,
                    timeout=TIMEOUT).json()
    pid = p1["id"]
    print(f"created {p1['ticket_number']} category={p1['predicted_category']} "
          f"priority={p1['priority_level']}/{p1['priority_score']}")
    print("required skills:", [(s["skill_name"], s["score"]) for s in p1["required_skills"]])

    teams = httpx.get(f"{BASE}/api/v1/problems/{pid}/team-recommendations",
                      headers=headers, timeout=TIMEOUT).json()
    option = teams["options"][0]
    team_ids = [m["user_id"] for m in
                httpx.get(f"{BASE}/api/v1/problems/{pid}/team-recommendations",
                          headers=admin_headers, timeout=TIMEOUT).json()["options"][0]["members"]]
    mentor_ranking = httpx.get(
        f"{BASE}/api/v1/problems/{pid}/mentor-recommendations",
        headers=admin_headers, timeout=TIMEOUT).json()["mentors"]
    mentor_id = mentor_ranking[0]["mentor_user_id"]
    print(f"AI team option 1 ({option['score']}): "
          f"{[m['name'] for m in option['members']]}; AI mentor: {mentor_ranking[0]['name']} "
          f"({mentor_ranking[0]['score']})")

    solver_emails = ["solver1@campusxolve.local", "solver2@campusxolve.local",
                     "solver3@campusxolve.local"]
    mentor_email = "mentor2@campusxolve.local" if "Torres" in mentor_ranking[0]["name"] \
        else "mentor1@campusxolve.local"
    print("BEFORE workloads:", workloads(*solver_emails, mentor_email))

    for action, body, expect in [
        ("review/start", {}, 200),
        ("approve", {}, 200),
    ]:
        r = httpx.post(f"{BASE}/api/v1/admin/problems/{pid}/{action}", json=body,
                       headers=admin_headers, timeout=TIMEOUT)
        assert r.status_code == expect, (action, r.text)
        print(f"{action}: status={r.json()['status']}")

    team_rec_id = httpx.get(f"{BASE}/api/v1/problems/{pid}/team-recommendations",
                            headers=admin_headers, timeout=TIMEOUT).json()["options"][0]["id"]
    mentor_rec_id = mentor_ranking[0]["id"]
    assign = httpx.post(
        f"{BASE}/api/v1/admin/problems/{pid}/assign",
        json={"solver_user_ids": team_ids, "mentor_user_id": mentor_id,
              "team_recommendation_id": team_rec_id, "mentor_recommendation_id": mentor_rec_id},
        headers=admin_headers, timeout=TIMEOUT)
    assert assign.status_code == 201, assign.text
    data = assign.json()
    print(f"assigned: team_overridden={data['team_was_overridden']} "
          f"mentor_overridden={data['mentor_was_overridden']}")
    print("AFTER workloads:", workloads(*solver_emails, mentor_email))

    detail = httpx.get(f"{BASE}/api/v1/problems/{pid}", headers=headers, timeout=TIMEOUT).json()
    assert detail["status"] == "ASSIGNED"
    print("reporter sees team:",
          [m["name"] for m in detail["assignment"]["team"]["members"]],
          "mentor:", detail["assignment"]["mentor"]["name"])

    # Solver + mentor worklists (seed passwords are dev fixtures).
    solver_tok = httpx.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": solver_emails[0], "password": "dev_solver_123"},
        timeout=TIMEOUT).json()["access_token"]
    assigned_list = httpx.get(
        f"{BASE}/api/v1/problems/assigned/me",
        headers={"Authorization": f"Bearer {solver_tok}"}, timeout=TIMEOUT).json()
    print(f"solver1 assigned/me: {[p['ticket_number'] for p in assigned_list]}")
    mentor_tok = httpx.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": mentor_email, "password": "dev_mentor_123"},
        timeout=TIMEOUT).json()["access_token"]
    mentored_list = httpx.get(
        f"{BASE}/api/v1/problems/mentored/me",
        headers={"Authorization": f"Bearer {mentor_tok}"}, timeout=TIMEOUT).json()
    print(f"mentor mentored/me: {[p['ticket_number'] for p in mentored_list]}")

    # ---------- Report 2: override smoke ----------
    p2 = httpx.post(f"{BASE}/api/v1/problems", json=REPORT2, headers=headers,
                    timeout=TIMEOUT).json()
    pid2 = p2["id"]
    httpx.post(f"{BASE}/api/v1/admin/problems/{pid2}/review/start", json={},
               headers=admin_headers, timeout=TIMEOUT)
    httpx.post(f"{BASE}/api/v1/admin/problems/{pid2}/approve", json={},
               headers=admin_headers, timeout=TIMEOUT)
    t2 = httpx.get(f"{BASE}/api/v1/problems/{pid2}/team-recommendations",
                   headers=admin_headers, timeout=TIMEOUT).json()["options"]
    m2 = httpx.get(f"{BASE}/api/v1/problems/{pid2}/mentor-recommendations",
                   headers=admin_headers, timeout=TIMEOUT).json()["mentors"]
    ai_team = sorted(m["user_id"] for m in t2[0]["members"])
    ai_mentor = m2[0]["mentor_user_id"]
    # Different team (swap last member for solver3 if present, else solver1).
    with eng.begin() as conn:
        seed_ids = [
            str(conn.execute(text("SELECT id FROM users WHERE email=:e"), {"e": e}).scalar())
            for e in ("solver1@campusxolve.local", "solver2@campusxolve.local",
                      "solver3@campusxolve.local")
        ]
    manual_team = sorted(ai_team[:-1])
    if len(manual_team) < 2:
        manual_team = sorted(manual_team + [next(s for s in seed_ids if s not in ai_team)])
    assert manual_team != ai_team, (ai_team, manual_team)
    assert len(manual_team) >= 2
    other_mentor = m2[1]["mentor_user_id"]
    assert other_mentor != ai_mentor
    override = httpx.post(
        f"{BASE}/api/v1/admin/problems/{pid2}/assign",
        json={"solver_user_ids": manual_team, "mentor_user_id": other_mentor,
              "team_override_reason": "Smoke: prefer hardware-adjacent solver for lab switches",
              "mentor_override_reason": "Smoke: second mentor knows this building"},
        headers=admin_headers, timeout=TIMEOUT)
    assert override.status_code == 201, override.text
    odata = override.json()
    assert odata["team_was_overridden"] is True
    assert odata["mentor_was_overridden"] is True
    # Recommendations immutable: still the AI originals.
    t2_again = httpx.get(f"{BASE}/api/v1/problems/{pid2}/team-recommendations",
                         headers=admin_headers, timeout=TIMEOUT).json()["options"]
    assert sorted(m["user_id"] for m in t2_again[0]["members"]) == ai_team
    print(f"override OK: AI team {ai_team} -> final {manual_team}; "
          f"AI mentor {ai_mentor} -> final {other_mentor}")
    print(f"reasons stored: {odata['team_override_reason']!r} / {odata['mentor_override_reason']!r}")

    # ---------- Failure smoke: maxed-out member ----------
    p3 = httpx.post(f"{BASE}/api/v1/problems", json=REPORT, headers=headers,
                    timeout=TIMEOUT).json()
    pid3 = p3["id"]
    httpx.post(f"{BASE}/api/v1/admin/problems/{pid3}/review/start", json={},
               headers=admin_headers, timeout=TIMEOUT)
    httpx.post(f"{BASE}/api/v1/admin/problems/{pid3}/approve", json={},
               headers=admin_headers, timeout=TIMEOUT)
    with eng.begin() as conn:
        conn.execute(text("UPDATE student_profiles SET current_workload=max_workload "
                          "WHERE user_id=(SELECT id FROM users WHERE email='solver1@campusxolve.local')"))
    with eng.begin() as conn:
        s1id = str(conn.execute(
            text("SELECT id FROM users WHERE email='solver1@campusxolve.local'")).scalar())
    bad = httpx.post(
        f"{BASE}/api/v1/admin/problems/{pid3}/assign",
        json={"solver_user_ids": [s1id, team_ids[1]], "mentor_user_id": mentor_id,
              "team_override_reason": "smoke", "mentor_override_reason": "smoke"},
        headers=admin_headers, timeout=TIMEOUT)
    assert bad.status_code == 422, bad.text
    with eng.begin() as conn:
        n_assign = conn.execute(
            text("SELECT count(*) FROM problem_assignments WHERE problem_id=:p"),
            {"p": pid3}).scalar()
        n_teams = conn.execute(
            text("SELECT count(*) FROM problem_teams WHERE problem_id=:p"),
            {"p": pid3}).scalar()
        status = conn.execute(
            text("SELECT status FROM problems WHERE id=:p"), {"p": pid3}).scalar()
    assert (n_assign, n_teams, status) == (0, 0, "APPROVED"), (n_assign, n_teams, status)
    print(f"failure rollback OK: assignments={n_assign} teams={n_teams} status={status}")
    with eng.begin() as conn:
        conn.execute(text("UPDATE student_profiles SET current_workload=0 "
                          "WHERE user_id=(SELECT id FROM users WHERE email='solver1@campusxolve.local')"))

    # ---------- Cleanup ----------
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email.lower()})
        conn.execute(text("DELETE FROM duplicate_clusters WHERE id NOT IN "
                          "(SELECT cluster_id FROM duplicate_cluster_members)"))
    print("smoke temp data cleaned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
