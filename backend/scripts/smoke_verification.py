#!/usr/bin/env python3
"""Step 11 real E2E smoke: work -> submit -> mentor changes -> resubmit ->
approve -> reporter NO -> resubmit -> approve -> reporter YES -> close.

Runs through the live API with real seeded solver/mentor profiles and
prints measured statuses, workloads, and notification counts. Temp
reporter data is removed afterwards. Nothing is faked: every state comes
from the database. Do NOT run with uncommitted migrations.

Usage: python3 scripts/smoke_verification.py
"""

import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import httpx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

BASE = "http://localhost:8000"
PASSWORD = "Smoke11_pass_1"
TIMEOUT = 300.0

REPORT = {
    "title": "Campus WiFi network keeps disconnecting in the computer lab",
    "description": "Students cannot access the internet in the computer lab because the WiFi "
    "network and Linux lab systems keep disconnecting during practical hours. "
    "The network switch may need inspection.",
    "location_text": "Computer Lab",
}

SOLUTION = {
    "solution_summary": "Replaced the faulty lab switch and verified connectivity across the lab",
    "root_cause": "An aging access switch was dropping packets under load in the computer lab",
    "work_performed": "Diagnosed port errors, replaced the switch, re-terminated two uplinks, "
    "and load-tested the lab network through a full practical session.",
    "testing_performed": "Ping and iperf runs from every lab terminal for one hour.",
}

eng = create_engine("postgresql+psycopg2://campusxolve:campusxolve@localhost:5432/campusxolve")


def login(email: str, password: str) -> str:
    resp = httpx.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def workloads(*emails: str) -> dict[str, str]:
    with eng.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT u.email, COALESCE(sp.current_workload, fp.current_workload), "
                "COALESCE(sp.max_workload, fp.max_workload) FROM users u "
                "LEFT JOIN student_profiles sp ON sp.user_id=u.id "
                "LEFT JOIN faculty_profiles fp ON fp.user_id=u.id "
                "WHERE u.email IN :emails"
            ),
            {"emails": tuple(e.lower() for e in emails)},
        ).all()
    return {r[0]: f"{r[1]}/{r[2]}" for r in rows}


def unread(token: str) -> int:
    resp = httpx.get(
        f"{BASE}/api/v1/notifications/unread-count",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return int(resp.json()["unread_count"])


def types_for(token: str) -> list[str]:
    resp = httpx.get(
        f"{BASE}/api/v1/notifications?limit=100",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return [n["type"] for n in resp.json()["items"]]


def main() -> int:
    with eng.begin() as conn:
        conn.execute(
            text("DELETE FROM problems WHERE reporter_id IN ("
                 "SELECT id FROM users WHERE email LIKE 'smoke11\\_%' ESCAPE '\\')")
        )
        conn.execute(text("DELETE FROM users WHERE email LIKE 'smoke11\\_%' ESCAPE '\\'"))
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
    email = f"smoke11_{tag}@example.com"
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
            "team_name": "Smoke Verify Crew",
            "team_override_reason": "Smoke test team",
            "mentor_override_reason": "Smoke test mentor",
        },
        headers=auth(admin_token),
        timeout=TIMEOUT,
    )
    assign.raise_for_status()
    print(f"assigned: status=ASSIGNED workloads={workloads('solver1@campusxolve.local', 'solver2@campusxolve.local', 'mentor1@campusxolve.local')}")

    # Solver completes the work so readiness passes.
    for title in ("Replace the switch", "Test every terminal"):
        task = httpx.post(
            f"{BASE}/api/v1/problems/{pid}/tasks", json={"title": title},
            headers=auth(s1_token), timeout=TIMEOUT,
        )
        task.raise_for_status()
        tid = task.json()["id"]
        for target in ("IN_PROGRESS", "DONE"):
            httpx.patch(
                f"{BASE}/api/v1/problems/{pid}/tasks/{tid}", json={"status": target},
                headers=auth(s1_token), timeout=TIMEOUT,
            ).raise_for_status()
    print("work complete: 2/2 tasks DONE")

    mentor_unread_before = unread(mentor_token)
    sub1 = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/solutions", json=SOLUTION,
        headers=auth(s1_token), timeout=TIMEOUT,
    )
    sub1.raise_for_status()
    sub1_id = sub1.json()["id"]
    print(f"solution rev1 submitted: status={sub1.json()['status']}")
    mentor_unread_after = unread(mentor_token)
    assert "SOLUTION_SUBMITTED" in types_for(mentor_token)
    print(f"mentor unread {mentor_unread_before} -> {mentor_unread_after} (SOLUTION_SUBMITTED delivered)")

    changes = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/solutions/{sub1_id}/review",
        json={"decision": "CHANGES_REQUESTED", "review_comment": "Add load-test evidence photos."},
        headers=auth(mentor_token),
        timeout=TIMEOUT,
    )
    changes.raise_for_status()
    detail = httpx.get(f"{BASE}/api/v1/problems/{pid}", headers=auth(s1_token), timeout=TIMEOUT).json()
    assert detail["status"] == "IN_PROGRESS", detail["status"]
    assert "CHANGES_REQUESTED" in types_for(s1_token)
    print("mentor requested changes: problem stays IN_PROGRESS, team notified")

    sub2 = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/solutions", json=SOLUTION,
        headers=auth(s1_token), timeout=TIMEOUT,
    )
    sub2.raise_for_status()
    assert sub2.json()["revision_number"] == 2
    print("revision 2 submitted")
    httpx.post(
        f"{BASE}/api/v1/problems/{pid}/solutions/{sub2.json()['id']}/review",
        json={"decision": "APPROVED", "review_comment": "Evidence complete."},
        headers=auth(mentor_token),
        timeout=TIMEOUT,
    ).raise_for_status()
    detail = httpx.get(f"{BASE}/api/v1/problems/{pid}", headers=auth(rep_token), timeout=TIMEOUT).json()
    assert detail["status"] == "AWAITING_VERIFICATION", detail["status"]
    assert "REPORTER_VERIFICATION_REQUIRED" in types_for(rep_token)
    print("mentor approved rev2: AWAITING_VERIFICATION, reporter notified")

    no = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/verifications",
        json={"decision": "NOT_RESOLVED", "reason": "WiFi still drops every afternoon."},
        headers=auth(rep_token),
        timeout=TIMEOUT,
    )
    no.raise_for_status()
    detail = httpx.get(f"{BASE}/api/v1/problems/{pid}", headers=auth(s1_token), timeout=TIMEOUT).json()
    assert detail["status"] == "IN_PROGRESS", detail["status"]
    assert "REPORTER_REJECTED_RESOLUTION" in types_for(s1_token)
    assert "REPORTER_REJECTED_RESOLUTION" in types_for(mentor_token)
    print("reporter said NO: back to IN_PROGRESS, team + mentor notified")

    sub3 = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/solutions", json=SOLUTION,
        headers=auth(s1_token), timeout=TIMEOUT,
    )
    sub3.raise_for_status()
    assert sub3.json()["revision_number"] == 3
    httpx.post(
        f"{BASE}/api/v1/problems/{pid}/solutions/{sub3.json()['id']}/review",
        json={"decision": "APPROVED"},
        headers=auth(mentor_token),
        timeout=TIMEOUT,
    ).raise_for_status()
    before_close = workloads('solver1@campusxolve.local', 'solver2@campusxolve.local', 'mentor1@campusxolve.local')
    yes = httpx.post(
        f"{BASE}/api/v1/problems/{pid}/verifications",
        json={"decision": "RESOLVED"},
        headers=auth(rep_token),
        timeout=TIMEOUT,
    )
    yes.raise_for_status()
    detail = httpx.get(f"{BASE}/api/v1/problems/{pid}", headers=auth(rep_token), timeout=TIMEOUT).json()
    assert detail["status"] == "RESOLVED", detail["status"]
    assert detail["resolved_at"] is not None
    at_resolve = workloads('solver1@campusxolve.local', 'solver2@campusxolve.local', 'mentor1@campusxolve.local')
    assert at_resolve == before_close, (at_resolve, before_close)
    assert "PROBLEM_RESOLVED" in types_for(s1_token)
    print(f"reporter said YES: RESOLVED, workloads still allocated {at_resolve}")

    close = httpx.post(
        f"{BASE}/api/v1/admin/problems/{pid}/close",
        json={"reason": "Fix holding for a week."},
        headers=auth(admin_token),
        timeout=TIMEOUT,
    )
    close.raise_for_status()
    assert close.json()["status"] == "CLOSED"
    after_close = workloads('solver1@campusxolve.local', 'solver2@campusxolve.local', 'mentor1@campusxolve.local')
    print(f"admin closed: workloads before={before_close} after={after_close}")
    for address, load in before_close.items():
        current, maximum = load.split("/")
        assert current == "1", (address, load)
        assert after_close[address] == f"0/{maximum}", after_close
    retry = httpx.post(
        f"{BASE}/api/v1/admin/problems/{pid}/close", json={}, headers=auth(admin_token), timeout=TIMEOUT
    )
    assert retry.status_code == 409, retry.text
    assert workloads('solver1@campusxolve.local')['solver1@campusxolve.local'].startswith("0/")
    print("retry close rejected (409): no double release")
    assert "PROBLEM_CLOSED" in types_for(rep_token)
    assert "PROBLEM_CLOSED" in types_for(s1_token)
    assert "PROBLEM_CLOSED" in types_for(mentor_token)
    print("PROBLEM_CLOSED delivered to reporter, team, and mentor")

    # Read-state smoke: mark one notification read, unread count drops by one.
    items = httpx.get(
        f"{BASE}/api/v1/notifications?unread_only=true&limit=100",
        headers=auth(rep_token), timeout=TIMEOUT,
    ).json()["items"]
    count_before = unread(rep_token)
    assert count_before >= 1
    httpx.patch(
        f"{BASE}/api/v1/notifications/{items[0]['id']}/read",
        headers=auth(rep_token), timeout=TIMEOUT,
    ).raise_for_status()
    count_after = unread(rep_token)
    assert count_after == count_before - 1, (count_before, count_after)
    print(f"reporter unread {count_before} -> {count_after} after marking one read")

    with eng.begin() as conn:
        conn.execute(text("DELETE FROM problems WHERE id=:p"), {"p": pid})
        conn.execute(text("DELETE FROM users WHERE email=:e"), {"e": email.lower()})
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
