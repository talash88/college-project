#!/usr/bin/env python3
"""Step 17: curated college-demo seed — clearly fictional data, honest AI outputs.

Seeds a FRESH database (default: campusxolve_demo) with demo accounts
(`demo.*@campusxolve.local`), skill profiles, and 8 problems driven through
REAL API workflows into varied lifecycle states:

  1. Library WiFi outage ............ CLOSED (+ Knowledge article)
  2. Main Gate CCTV failure ......... CLOSED (+ Knowledge article)
  3. Campus portal mobile login ..... IN_PROGRESS (tasks + milestone + progress)
  4. Canteen electrical sparking .... UNDER_REVIEW
  5. Hostel drinking water .......... ASSIGNED
  6. Portal login portal (paraphrase) DUPLICATE of #3 (confirmed cluster)
  7. Hostel cleanliness ............. SUBMITTED
  8. Evening bus delays ............. AWAITING_VERIFICATION (mentor-approved solution)

Nothing is faked: every state comes from the live API (the script spawns a
temporary uvicorn pointed at the demo DB). AI outputs are left honest —
low-confidence predictions stay low-confidence.

Usage:
  1. createdb campusxolve_demo  (or let the script note the missing DB)
  2. DATABASE_URL=...demo... python3 -m alembic upgrade head
  3. python3 scripts/seed_demo.py [--api-port 8001] [--database-url ...]

Refuses to run against the `campusxolve` dev DB and `campusxolve_test`
unless --allow-dev is passed explicitly.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

PROTECTED_DB_NAMES = {"campusxolve", "campusxolve_test"}

DEMO_PASSWORD = "demo_college_123"

DEMO_USERS = [
    {"email": "demo.admin@campusxolve.local", "full_name": "Demo Admin", "role": "ADMIN"},
    {"email": "demo.ananya@campusxolve.local", "full_name": "Ananya Rao", "role": "REPORTER"},
    {"email": "demo.kabir@campusxolve.local", "full_name": "Kabir Shah", "role": "REPORTER"},
    {"email": "demo.rohan@campusxolve.local", "full_name": "Rohan Verma", "role": "SOLVER"},
    {"email": "demo.sneha@campusxolve.local", "full_name": "Sneha Iyer", "role": "SOLVER"},
    {"email": "demo.aditya@campusxolve.local", "full_name": "Aditya Kulkarni", "role": "SOLVER"},
    {"email": "demo.ishita@campusxolve.local", "full_name": "Ishita Bose", "role": "SOLVER"},
    {"email": "demo.vikram@campusxolve.local", "full_name": "Vikram Singh", "role": "SOLVER"},
    {"email": "demo.meera@campusxolve.local", "full_name": "Dr. Meera Krishnan", "role": "MENTOR"},
    {"email": "demo.arjun@campusxolve.local", "full_name": "Prof. Arjun Nair", "role": "MENTOR"},
]

DEMO_PROFILES = {
    "demo.rohan@campusxolve.local": ("DEMO-CS-101", "Computer Networking", "Linux"),
    "demo.sneha@campusxolve.local": ("DEMO-CS-102", "Frontend Development", "UI/UX Design"),
    "demo.aditya@campusxolve.local": ("DEMO-EE-103", "Electrical Maintenance", "Electronics"),
    "demo.ishita@campusxolve.local": ("DEMO-CS-104", "Python", "Problem Solving"),
    "demo.vikram@campusxolve.local": ("DEMO-ME-105", "Hardware Troubleshooting", "Documentation"),
    "demo.ananya@campusxolve.local": ("DEMO-CS-106", None, None),
    "demo.kabir@campusxolve.local": ("DEMO-EC-107", None, None),
}

DEMO_MENTORS = {
    "demo.meera@campusxolve.local": ("DEMO-FAC-201", "Professor", "Computer Networks / Systems"),
    "demo.arjun@campusxolve.local": ("DEMO-FAC-202", "Associate Professor", "Electrical Systems / Safety"),
}


def db_name_of(url: str) -> str:
    return (urlparse(url).path or "/").lstrip("/").split("?")[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the college demo environment.")
    parser.add_argument("--database-url", default=os.environ.get(
        "DEMO_DATABASE_URL",
        "postgresql+asyncpg://campusxolve:campusxolve@localhost:5432/campusxolve_demo"))
    parser.add_argument("--api-port", type=int, default=8001)
    parser.add_argument("--allow-dev", action="store_true",
                        help="Permit running against dev/test databases (NOT recommended).")
    args = parser.parse_args()

    name = db_name_of(args.database_url)
    if name in PROTECTED_DB_NAMES and not args.allow_dev:
        print(f"Refusing to seed protected database '{name}' without --allow-dev.")
        return 2

    import httpx  # noqa: E402
    from sqlalchemy import select  # noqa: E402

    # Engine binds at import: point at the demo DB BEFORE any app import.
    os.environ["DATABASE_URL"] = args.database_url

    from app.core.enums import (  # noqa: E402
        AvailabilityStatus,
        Department,
        ProficiencyLevel,
        UserRole,
    )
    from app.db.session import async_session_factory  # noqa: E402
    from app.models.faculty_profile import FacultyProfile  # noqa: E402
    from app.models.skill import Skill  # noqa: E402
    from app.models.student_profile import StudentProfile  # noqa: E402
    from app.models.user import User  # noqa: E402
    from app.models.user_skill import UserSkill  # noqa: E402
    from app.services.security import hash_password  # noqa: E402

    async def seed_accounts() -> None:
        async with async_session_factory() as s:
            for u in DEMO_USERS:
                row = (await s.execute(select(User).where(User.email == u["email"]))).scalar_one_or_none()
                if row is not None:
                    print(f"  exists: {u['email']}")
                    continue
                row = User(full_name=u["full_name"], email=u["email"],
                           password_hash=hash_password(DEMO_PASSWORD),
                           role=UserRole(u["role"]), is_verified=True)
                s.add(row)
                await s.flush()
                if u["role"] == "MENTOR":
                    emp, desig, spec = DEMO_MENTORS[u["email"]]
                    s.add(FacultyProfile(user_id=row.id, employee_identifier=emp,
                                         department=Department.COMPUTER_SCIENCE_ENGINEERING,
                                         designation=desig, specialization=spec,
                                         availability_status=AvailabilityStatus.AVAILABLE,
                                         current_workload=0, max_workload=5))
                elif u["role"] in ("SOLVER", "REPORTER"):
                    ident, sk1, sk2 = DEMO_PROFILES[u["email"]]
                    s.add(StudentProfile(user_id=row.id, student_identifier=ident,
                                         department=Department.COMPUTER_SCIENCE_ENGINEERING,
                                         academic_year=3,
                                         availability_status=AvailabilityStatus.AVAILABLE,
                                         current_workload=0, max_workload=3))
                    await s.flush()
                    for sk in (sk1, sk2):
                        if not sk:
                            continue
                        skill = (await s.execute(select(Skill).where(Skill.name == sk))).scalar_one_or_none()
                        if skill is None:
                            print(f"  WARNING: skill missing: {sk}")
                            continue
                        s.add(UserSkill(user_id=row.id, skill_id=skill.id,
                                        proficiency_level=ProficiencyLevel.ADVANCED,
                                        is_verified=True))
                print(f"  created: {u['email']} ({u['role']})")
            await s.commit()

    print(f"Seeding demo accounts into '{name}' ...")
    asyncio.run(seed_accounts())

    # Temporary API server pointed at the demo DB for the workflow stages.
    base = f"http://localhost:{args.api_port}"
    env = {**os.environ, "DATABASE_URL": args.database_url, "ENVIRONMENT": "development"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(args.api_port)],
        cwd=str(BACKEND_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if httpx.get(f"{base}/api/v1/health", timeout=5).json().get("status") == "healthy":
                    break
            except Exception:
                time.sleep(2)
        else:
            print("Demo API server did not become healthy.")
            return 1
        print("Demo API healthy; driving workflows ...")
        run_workflows(base)
    finally:
        proc.terminate()
    print("DEMO SEED OK")
    return 0


def run_workflows(base: str) -> None:
    import httpx

    T = 120.0

    def login(email: str) -> str:
        r = httpx.post(f"{base}/api/v1/auth/login",
                       json={"email": email, "password": DEMO_PASSWORD}, timeout=T)
        r.raise_for_status()
        return r.json()["access_token"]

    admin = login("demo.admin@campusxolve.local")
    rep1 = login("demo.ananya@campusxolve.local")
    rep2 = login("demo.kabir@campusxolve.local")
    AH = {"Authorization": f"Bearer {admin}"}
    R1H = {"Authorization": f"Bearer {rep1}"}
    R2H = {"Authorization": f"Bearer {rep2}"}

    def report(token_h: dict, title: str, desc: str, loc: str, affected: int = 0) -> dict:
        payload = {"title": title, "description": desc, "location_text": loc}
        if affected:
            payload["affected_people_count"] = affected
        r = httpx.post(f"{base}/api/v1/problems", json=payload, headers=token_h, timeout=T)
        r.raise_for_status()
        body = r.json()
        print(f"  {body['ticket_number']} {body['status']} "
              f"cat={body.get('predicted_category')} pri={body.get('priority_level')}")
        return body

    def approve(pid: str) -> None:
        httpx.post(f"{base}/api/v1/admin/problems/{pid}/review/start", json={}, headers=AH, timeout=T).raise_for_status()
        httpx.post(f"{base}/api/v1/admin/problems/{pid}/approve", json={}, headers=AH, timeout=T).raise_for_status()

    def assign(pid: str, solvers: list[str], mentor: str) -> None:
        import sqlalchemy
        eng = sqlalchemy.create_engine(
            "postgresql+psycopg2://campusxolve:campusxolve@localhost:5432/"
            + urlparse(os.environ["DATABASE_URL"]).path.lstrip("/"))
        with eng.begin() as conn:
            sids = [str(conn.execute(sqlalchemy.text(
                "SELECT id FROM users WHERE email=:e"), {"e": e}).scalar()) for e in solvers]
            mid = str(conn.execute(sqlalchemy.text(
                "SELECT id FROM users WHERE email=:e"), {"e": mentor}).scalar())
        teams = httpx.get(f"{base}/api/v1/problems/{pid}/team-recommendations", headers=AH, timeout=T).json()
        mentors = httpx.get(f"{base}/api/v1/problems/{pid}/mentor-recommendations", headers=AH, timeout=T).json()
        want = set(sids)
        opts = teams.get("options", [])
        opt = next((o for o in opts
                    if {m["user_id"] for m in o["members"]} == want), opts[0] if opts else None)
        mrecs = mentors.get("mentors", [])
        mrec = next((m for m in mrecs if m["mentor_user_id"] == mid), mrecs[0] if mrecs else None)
        if opt is None or mrec is None:
            print(f"  NOTE: no AI options for {pid} (sparse demo skills); assigning curated team with override.")
        curated_team = opt is not None and [m["user_id"] for m in opt["members"]] == sids
        curated_mentor = mrec is not None and mrec["mentor_user_id"] == mid
        payload = {"solver_user_ids": sids,
                   "mentor_user_id": mid,
                   "team_override_reason": None if curated_team else "Demo curated team",
                   "mentor_override_reason": None if curated_mentor else "Demo curated mentor"}
        if opt is not None:
            payload["team_recommendation_id"] = opt["id"]
        if mrec is not None:
            payload["mentor_recommendation_id"] = mrec["id"]
        r = httpx.post(f"{base}/api/v1/admin/problems/{pid}/assign", json=payload, headers=AH, timeout=T)
        r.raise_for_status()

    # 1 + 2: CLOSED (full lifecycle each).
    closed_defs = [
        (R1H, rep1, "Central library WiFi keeps disconnecting in the reading room",
         "Students cannot study in the central library reading room because the wireless network "
         "keeps disconnecting laptops every few minutes. The access point on the second floor "
         "seems faulty and needs replacement. Dozens of students are affected during exam week.",
         "Central Library Reading Room", 45,
         ["demo.rohan@campusxolve.local", "demo.sneha@campusxolve.local"], "demo.meera@campusxolve.local"),
        (R2H, rep2, "Main gate CCTV camera stopped recording footage",
         "The CCTV camera at the main entrance gate stopped recording three days ago. The security "
         "office reports a blank feed and the night guard cannot review incidents. Camera power and "
         "network cabling need inspection and repair.",
         "Main Entrance Gate", 12,
         ["demo.aditya@campusxolve.local", "demo.ishita@campusxolve.local"], "demo.arjun@campusxolve.local"),
    ]
    for tok_h, tok_raw, title, desc, loc, aff, team, mentor in closed_defs:
        p = report(tok_h, title, desc, loc, aff)
        pid = p["id"]
        approve(pid)
        assign(pid, team, mentor)
        solver_tok = login(team[0])
        SH = {"Authorization": f"Bearer {solver_tok}"}
        mentor_tok = login(mentor)
        MH = {"Authorization": f"Bearer {mentor_tok}"}
        for t in ("Diagnose the fault on site", "Apply the fix and test"):
            tresp = httpx.post(f"{base}/api/v1/problems/{pid}/tasks", json={"title": t}, headers=SH, timeout=T)
            if tresp.status_code != 201:
                raise RuntimeError(f"task create failed: {tresp.status_code} {tresp.text[:300]}")
            task = tresp.json()
            httpx.patch(f"{base}/api/v1/problems/{pid}/tasks/{task['id']}",
                        json={"status": "IN_PROGRESS"}, headers=SH, timeout=T).raise_for_status()
            httpx.patch(f"{base}/api/v1/problems/{pid}/tasks/{task['id']}",
                        json={"status": "DONE"}, headers=SH, timeout=T).raise_for_status()
        ms = httpx.post(f"{base}/api/v1/problems/{pid}/milestones", json={"title": "Fix verified"}, headers=MH, timeout=T).json()
        httpx.patch(f"{base}/api/v1/problems/{pid}/milestones/{ms['id']}",
                    json={"status": "COMPLETED"}, headers=MH, timeout=T).raise_for_status()
        sol = httpx.post(f"{base}/api/v1/problems/{pid}/solutions", json={
            "solution_summary": f"Fault isolated and repaired for: {title[:60]}",
            "root_cause": "Field diagnosis identified the failing component.",
            "work_performed": "Replaced/reconfigured the faulty unit and retested with users present.",
            "testing_performed": "Verified with affected users over two working days."},
            headers=SH, timeout=T).json()
        httpx.post(f"{base}/api/v1/problems/{pid}/solutions/{sol['id']}/review",
                   json={"decision": "APPROVED", "review_comment": "Verified on site."},
                   headers=MH, timeout=T).raise_for_status()
        # Reporter verifies (reporter token that filed it).
        httpx.post(f"{base}/api/v1/problems/{pid}/verifications", json={"decision": "RESOLVED"},
                   headers={"Authorization": f"Bearer {tok_raw}"}, timeout=T).raise_for_status()
        httpx.post(f"{base}/api/v1/admin/problems/{pid}/close",
                   json={"reason": "Demo: fix holding."}, headers=AH, timeout=T).raise_for_status()
        print(f"  {p['ticket_number']} CLOSED")

    # 3: IN_PROGRESS with visible work.
    p3 = report(R1H, "Campus portal login fails on mobile browsers",
                "Students cannot log in to the campus portal from mobile browsers. The login page "
                "reloads in a loop on phones while desktop browsers work fine. The issue started after "
                "the weekend maintenance and affects hostel students filing complaints.",
                "Online Campus Portal", 120)
    approve(p3["id"])
    assign(p3["id"], ["demo.rohan@campusxolve.local", "demo.sneha@campusxolve.local",
                      "demo.vikram@campusxolve.local"], "demo.meera@campusxolve.local")
    s3 = {"Authorization": f"Bearer {login('demo.rohan@campusxolve.local')}"}
    t = httpx.post(f"{base}/api/v1/problems/{p3['id']}/tasks",
                   json={"title": "Reproduce the mobile login loop"}, headers=s3, timeout=T).json()
    httpx.patch(f"{base}/api/v1/problems/{p3['id']}/tasks/{t['id']}",
                json={"status": "IN_PROGRESS"}, headers=s3, timeout=T).raise_for_status()
    httpx.post(f"{base}/api/v1/problems/{p3['id']}/progress-updates",
               json={"summary": "Loop reproduced on two phone models", "next_steps": "Trace auth redirect"},
               headers={"Authorization": f"Bearer {login('demo.meera@campusxolve.local')}"}, timeout=T).raise_for_status()

    # 4: UNDER_REVIEW (electrical, urgency visible).
    p4 = report(R2H, "Sparking switchboard near the canteen needs urgent attention",
                "There is a burning smell from the switchboard near the canteen and visible sparks when "
                "switches are flipped. Students gather nearby during lunch hours. An electrician should "
                "isolate the board immediately.",
                "Canteen Switchboard Area", 200)
    httpx.post(f"{base}/api/v1/admin/problems/{p4['id']}/review/start", json={}, headers=AH, timeout=T).raise_for_status()

    # 5: ASSIGNED (drinking water).
    p5 = report(R1H, "Drinking water taps on hostel floor 3 run dry by evening",
                "The drinking water taps on floor 3 of the girls hostel run dry every evening. Residents "
                "must climb down two floors for water. The overhead tank valve or pipeline needs checking.",
                "Girls Hostel Floor 3", 60)
    approve(p5["id"])
    assign(p5["id"], ["demo.aditya@campusxolve.local", "demo.ishita@campusxolve.local"], "demo.arjun@campusxolve.local")

    # 6: confirmed DUPLICATE of #3 (paraphrase).
    p6 = report(R2H, "Portal sign-in loops forever on phones",
                "The campus portal sign-in page keeps looping on mobile phones and never completes login. "
                "Desktop access works. Hostel students cannot raise complaints from their phones since "
                "the weekend maintenance.",
                "Online Campus Portal", 90)
    cands = httpx.get(f"{base}/api/v1/problems/{p6['id']}/duplicates", headers=AH, timeout=T).json()["candidates"]
    match = next((c for c in cands if c["candidate"]["id"] == p3["id"]), None)
    if match is None:
        print(f"  WARNING: no duplicate candidate surfaced for {p6['ticket_number']} (left SUBMITTED)")
    else:
        httpx.post(f"{base}/api/v1/admin/duplicate-candidates/{match['id']}/confirm",
                   json={"review_note": "Demo: same portal login loop."}, headers=AH, timeout=T).raise_for_status()
        print(f"  {p6['ticket_number']} confirmed DUPLICATE of {p3['ticket_number']}")

    # 7: SUBMITTED (hostel cleanliness).
    report(R2H, "Hostel corridor cleaning missed for a week on block C",
           "The third-floor corridor of hostel block C has not been cleaned for a week. Dustbins "
           "overflow near the staircase and the washroom floor stays wet. Residents have raised this "
           "with the warden twice already.",
           "Hostel Block C", 40)

    # 8: AWAITING_VERIFICATION (bus delays).
    p8 = report(R1H, "Evening campus bus leaves early and skips the hostel stop",
                "The 6:30 pm campus bus has left five minutes early all week and skips the hostel stop, "
                "stranding day scholars. The driver should follow the posted timetable and halt at every "
                "marked stop.",
                "Hostel Bus Stop", 80)
    approve(p8["id"])
    assign(p8["id"], ["demo.vikram@campusxolve.local", "demo.ishita@campusxolve.local"], "demo.meera@campusxolve.local")
    s8 = {"Authorization": f"Bearer {login('demo.vikram@campusxolve.local')}"}
    for t in ("Ride along and log actual timings", "Confirm timetable with transport office"):
        task = httpx.post(f"{base}/api/v1/problems/{p8['id']}/tasks", json={"title": t}, headers=s8, timeout=T).json()
        httpx.patch(f"{base}/api/v1/problems/{p8['id']}/tasks/{task['id']}",
                    json={"status": "IN_PROGRESS"}, headers=s8, timeout=T).raise_for_status()
        httpx.patch(f"{base}/api/v1/problems/{p8['id']}/tasks/{task['id']}",
                    json={"status": "DONE"}, headers=s8, timeout=T).raise_for_status()
    m8 = {"Authorization": f"Bearer {login('demo.meera@campusxolve.local')}"}
    sol8 = httpx.post(f"{base}/api/v1/problems/{p8['id']}/solutions", json={
        "solution_summary": "Timetable re-issued; driver roster updated; stop compliance logged for a week.",
        "root_cause": "Driver followed an outdated roster with an early departure.",
        "work_performed": "Verified timings on three evenings with the transport office.",
        "testing_performed": "One week of on-time departures with hostel-stop halts."},
        headers=s8, timeout=T).json()
    httpx.post(f"{base}/api/v1/problems/{p8['id']}/solutions/{sol8['id']}/review",
               json={"decision": "APPROVED"}, headers=m8, timeout=T).raise_for_status()
    d8 = httpx.get(f"{base}/api/v1/problems/{p8['id']}", headers=AH, timeout=T).json()
    assert d8["status"] == "AWAITING_VERIFICATION", d8["status"]
    print(f"  {p8['ticket_number']} AWAITING_VERIFICATION")


if __name__ == "__main__":
    raise SystemExit(main())
