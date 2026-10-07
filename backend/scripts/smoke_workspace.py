#!/usr/bin/env python3
"""Step 10 real E2E smoke: assign -> workspace -> tasks -> IN_PROGRESS ->
block -> milestone -> progress update -> complete -> file -> measured progress.

Runs through the live API with real seeded solver/mentor profiles and
prints measured progress before/after. Temp reporter data is removed
afterwards. Nothing is faked: every state comes from the database.

Usage: python3 scripts/smoke_workspace.py
"""

import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import httpx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

BASE = "http://localhost:8000"
PASSWORD = "Smoke10_pass_1"
TIMEOUT = 300.0

REPORT = {
    "title": "Campus WiFi network keeps disconnecting in the computer lab",
    "description": "Students cannot access the internet in the computer lab because the WiFi "
    "network and Linux lab systems keep disconnecting during practical hours. "
    "The network switch may need inspection.",
    "location_text": "Computer Lab",
}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

eng = create_engine("postgresql+psycopg2://campusxolve:campusxolve@localhost:5432/campusxolve")


def login(email: str, password: str) -> str:
    resp = httpx.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def main() -> int:
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email LIKE 'smoke10\\_%' ESCAPE '\\'"))
        for email, load in {
            "solver1@campusxolve.local": 0,
            "solver2@campusxolve.local": 0,
            "mentor1@campusxolve.local": 0,
        }.items():
            conn.execute(
                text("UPDATE student_profiles SET current_workload=:l WHERE user_id=("
                     "SELECT id FROM users WHERE email=:e)"),
                {"l": load, "e": email},
            )
            conn.execute(
                text("UPDATE faculty_profiles SET current_workload=:l WHERE user_id=("
                     "SELECT id FROM users WHERE email=:e)"),
                {"l": load, "e": email},
            )
    tag = uuid.uuid4().hex[:8]
    email = f"smoke10_{tag}@example.com"
    reg = httpx.post(
        f"{BASE}/api/v1/auth/register",
        json={"full_name": "Smoke Reporter", "email": email,
              "password": PASSWORD, "role": "REPORTER"},
        timeout=TIMEOUT,
    )
    reg.raise_for_status()
    rep_token = reg.json()["access_token"]
    admin_token = login("admin@campusxolve.local", "dev_admin_123")
    s1_token = login("solver1@campusxolve.local", "dev_solver_123")
    mentor_token = login("mentor1@campusxolve.local", "dev_mentor_123")

    with eng.begin() as conn:
        s1_id = conn.execute(
            text("SELECT id FROM users WHERE email='solver1@campusxolve.local'")).scalar_one()
        s2_id = conn.execute(
            text("SELECT id FROM users WHERE email='solver2@campusxolve.local'")).scalar_one()
        m1_id = conn.execute(
            text("SELECT id FROM users WHERE email='mentor1@campusxolve.local'")).scalar_one()

    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    created = httpx.post(f"{BASE}/api/v1/problems", json=REPORT, headers=auth(rep_token), timeout=TIMEOUT)
    created.raise_for_status()
    pid = created.json()["id"]
    print(f"report: {created.json()['ticket_number']} status={created.json()['status']}")

    httpx.post(f"{BASE}/api/v1/admin/problems/{pid}/review/start", headers=auth(admin_token), timeout=TIMEOUT).raise_for_status()
    httpx.post(f"{BASE}/api/v1/admin/problems/{pid}/approve", json={}, headers=auth(admin_token), timeout=TIMEOUT).raise_for_status()
    assign = httpx.post(
        f"{BASE}/api/v1/admin/problems/{pid}/assign",
        json={
            "solver_user_ids": [str(s1_id), str(s2_id)],
            "mentor_user_id": str(m1_id),
            "team_name": "Smoke Crew",
            "team_override_reason": "Smoke test team",
            "mentor_override_reason": "Smoke test mentor",
        },
        headers=auth(admin_token),
        timeout=TIMEOUT,
    )
    assign.raise_for_status()
    print(f"assigned: team={assign.json()['team']['display_label']} status=ASSIGNED")

    ws0 = httpx.get(f"{BASE}/api/v1/problems/{pid}/workspace", headers=auth(s1_token), timeout=TIMEOUT)
    ws0.raise_for_status()
    print(f"initial progress: {ws0.json()['progress']['percent']}%")

    # Solver: create + start a task -> ASSIGNED becomes IN_PROGRESS.
    t1 = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/tasks",
        json={"title": "Inspect the lab switch", "assigned_to_user_id": str(s1_id)},
        headers=auth(s1_token),
        timeout=TIMEOUT,
    )
    t1.raise_for_status()
    t1_id = t1.json()["id"]
    httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/tasks/{t1_id}", json={"status": "IN_PROGRESS"},
        headers=auth(s1_token), timeout=TIMEOUT,
    ).raise_for_status()
    detail = httpx.get(f"{BASE}/api/v1/problems/{pid}", headers=auth(s1_token), timeout=TIMEOUT).json()
    print(f"after first task start: status={detail['status']}")
    assert detail["status"] == "IN_PROGRESS"
    assert sum(1 for a in detail["activity"] if a["event_type"] == "WORK_STARTED") == 1

    # Solver: second task, blocked with a real reason.
    t2 = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/tasks",
        json={"title": "Replace faulty switch"},
        headers=auth(s1_token),
        timeout=TIMEOUT,
    )
    t2.raise_for_status()
    t2_id = t2.json()["id"]
    httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/tasks/{t2_id}", json={"status": "IN_PROGRESS"},
        headers=auth(s1_token), timeout=TIMEOUT,
    ).raise_for_status()
    blocked = httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/tasks/{t2_id}",
        json={"status": "BLOCKED", "blocker_reason": "Waiting on replacement switch from stores"},
        headers=auth(s1_token),
        timeout=TIMEOUT,
    )
    blocked.raise_for_status()
    print(f"blocked task reason kept: {blocked.json()['blocker_reason']!r}")

    # Mentor: milestone + progress update.
    ms = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/milestones",
        json={"title": "Problem Analysis"},
        headers=auth(mentor_token),
        timeout=TIMEOUT,
    )
    ms.raise_for_status()
    ms_id = ms.json()["id"]
    httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/milestones/{ms_id}", json={"status": "IN_PROGRESS"},
        headers=auth(mentor_token), timeout=TIMEOUT,
    ).raise_for_status()
    ms2 = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/milestones",
        json={"title": "Prototype Fix"},
        headers=auth(mentor_token),
        timeout=TIMEOUT,
    )
    ms2.raise_for_status()
    pu = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/progress-updates",
        json={"summary": "Switch inspected, replacement ordered", "next_steps": "Install and test"},
        headers=auth(mentor_token),
        timeout=TIMEOUT,
    )
    pu.raise_for_status()
    print(f"progress update snapshot: {pu.json()['progress_snapshot']}%")

    # Complete one task; upload evidence; measure.
    httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/tasks/{t1_id}", json={"status": "DONE"},
        headers=auth(s1_token), timeout=TIMEOUT,
    ).raise_for_status()
    up = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/work-files",
        files={"file": ("switch.png", PNG, "image/png")},
        data={"description": "Faulty switch photo"},
        headers=auth(s1_token),
        timeout=TIMEOUT,
    )
    up.raise_for_status()
    ws1 = httpx.get(f"{BASE}/api/v1/problems/{pid}/workspace", headers=auth(s1_token), timeout=TIMEOUT).json()
    p = ws1["progress"]
    print(f"after 1/2 tasks done, 0/2 milestones done: {p['percent']}% "
          f"({p['done_tasks']}/{p['total_tasks']} tasks, "
          f"{p['done_milestones']}/{p['total_milestones']} milestones)")
    assert p == {"percent": 35.0, "done_tasks": 1, "total_tasks": 2,
                 "done_milestones": 0, "total_milestones": 2}, p

    httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/milestones/{ms_id}", json={"status": "COMPLETED"},
        headers=auth(mentor_token), timeout=TIMEOUT,
    ).raise_for_status()
    httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/tasks/{t2_id}", json={"status": "IN_PROGRESS"},
        headers=auth(s1_token), timeout=TIMEOUT,
    ).raise_for_status()
    httpx.patch(
        f"{BASE}/api/v1/problems/{pid}/tasks/{t2_id}", json={"status": "DONE"},
        headers=auth(s1_token), timeout=TIMEOUT,
    ).raise_for_status()
    ws2 = httpx.get(f"{BASE}/api/v1/problems/{pid}/workspace", headers=auth(s1_token), timeout=TIMEOUT).json()
    p2 = ws2["progress"]
    print(f"after 2/2 tasks done, 1/2 milestones done: {p2['percent']}%")
    assert p2["percent"] == 85.0, p2

    # Reporter safe view: sees progress, not internals.
    pub = httpx.get(f"{BASE}/api/v1/problems/{pid}/public-progress", headers=auth(rep_token), timeout=TIMEOUT)
    pub.raise_for_status()
    body = pub.json()
    print(f"reporter sees: status={body['status']} progress={body['progress_percent']}% "
          f"team={body['team_name']} mentor={body['mentor_name']}")
    blob = pub.text
    assert "Waiting on replacement switch" not in blob
    assert "original_filename" not in blob
    assert body["progress_percent"] == 85.0
    ws_denied = httpx.get(f"{BASE}/api/v1/problems/{pid}/workspace", headers=auth(rep_token), timeout=TIMEOUT)
    assert ws_denied.status_code == 403, ws_denied.text
    print("reporter workspace access correctly denied (403); safe progress visible")

    with eng.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email.lower()})
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
