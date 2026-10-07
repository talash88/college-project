'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { AppLayout } from '@/components/ui/AppLayout';
import { useAuth } from '@/context/AuthContext';
import { apiClient } from '@/lib/api-client';
import { API_ENDPOINTS } from '@/lib/api-config';
import { getApiErrorMessage } from '@/lib/auth-service';
import type { AuthUser, Skill, UserSkill } from '@/types/api';

const DEPARTMENTS = [
  'Computer Science & Engineering',
  'Information Technology',
  'Electronics',
  'Electrical',
  'Mechanical',
  'Civil',
  'Administration',
  'Other',
];

const AVAILABILITY = ['AVAILABLE', 'LIMITED', 'UNAVAILABLE'];

function isStudentRole(role: string): boolean {
  return role === 'REPORTER' || role === 'SOLVER';
}

function ProfileContent() {
  const { user, refreshUser } = useAuth();
  const [profile, setProfile] = useState<AuthUser | null>(user);
  const [skills, setSkills] = useState<UserSkill[]>([]);
  const [catalog, setCatalog] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);

  // Edit form state
  const [fullName, setFullName] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [department, setDepartment] = useState(DEPARTMENTS[0]);
  const [academicYear, setAcademicYear] = useState('3');
  const [semester, setSemester] = useState('');
  const [designation, setDesignation] = useState('');
  const [specialization, setSpecialization] = useState('');
  const [bio, setBio] = useState('');
  const [availability, setAvailability] = useState('AVAILABLE');

  // Skill form state
  const [newSkillId, setNewSkillId] = useState('');
  const [newProficiency, setNewProficiency] = useState('3');
  const [newYears, setNewYears] = useState('');
  const [editingSkillId, setEditingSkillId] = useState<string | null>(null);
  const [editProficiency, setEditProficiency] = useState('3');
  const [editYears, setEditYears] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [me, mySkills, allSkills] = await Promise.all([
        apiClient.get<AuthUser>(API_ENDPOINTS.profile.me),
        apiClient.get<{ skills: UserSkill[] }>(API_ENDPOINTS.profile.mySkills),
        apiClient.get<Skill[]>(`${API_ENDPOINTS.skills}?limit=100`),
      ]);
      setProfile(me);
      setSkills(mySkills.skills);
      setCatalog(allSkills.filter((s) => s.is_active));
      setFullName(me.full_name);
      const student = me.student_profile;
      const faculty = me.faculty_profile;
      setIdentifier(student?.student_identifier ?? faculty?.employee_identifier ?? '');
      setDepartment(student?.department ?? faculty?.department ?? DEPARTMENTS[0]);
      setAcademicYear(String(student?.academic_year ?? 3));
      setSemester(student?.semester != null ? String(student.semester) : '');
      setDesignation(faculty?.designation ?? '');
      setSpecialization(faculty?.specialization ?? '');
      setBio(student?.bio ?? faculty?.bio ?? '');
      setAvailability(student?.availability_status ?? faculty?.availability_status ?? 'AVAILABLE');
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to load profile.') });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setMessage(null);
    try {
      const student = isStudentRole(profile.role);
      const payload: Record<string, unknown> = { full_name: fullName.trim() };
      if (student) {
        payload.student_profile = {
          student_identifier: identifier.trim() || undefined,
          department,
          academic_year: Number(academicYear),
          semester: semester ? Number(semester) : undefined,
          bio: bio.trim() || undefined,
          availability_status: availability,
        };
      } else {
        payload.faculty_profile = {
          employee_identifier: identifier.trim() || undefined,
          department,
          designation: designation.trim() || undefined,
          specialization: specialization.trim() || undefined,
          bio: bio.trim() || undefined,
          availability_status: availability,
        };
      }
      const updated = await apiClient.patch<AuthUser>(API_ENDPOINTS.profile.me, payload);
      setProfile(updated);
      await refreshUser();
      setMessage({ kind: 'success', text: 'Profile saved.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to save profile.') });
    } finally {
      setSaving(false);
    }
  };

  const handleAddSkill = async (e: FormEvent) => {
    e.preventDefault();
    if (!newSkillId) {
      setMessage({ kind: 'error', text: 'Select a skill to add.' });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const created = await apiClient.post<UserSkill>(API_ENDPOINTS.profile.mySkills, {
        skill_id: newSkillId,
        proficiency_level: Number(newProficiency),
        years_experience: newYears === '' ? undefined : Number(newYears),
      });
      setSkills((prev) => [created, ...prev.filter((s) => s.skill_id !== created.skill_id)]);
      setNewSkillId('');
      setNewYears('');
      setMessage({ kind: 'success', text: 'Skill added.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to add skill.') });
    } finally {
      setSaving(false);
    }
  };

  const startEditSkill = (skill: UserSkill) => {
    setEditingSkillId(skill.skill_id);
    setEditProficiency(String(skill.proficiency_level));
    setEditYears(skill.years_experience != null ? String(skill.years_experience) : '');
  };

  const handleEditSkill = async (skillId: string) => {
    setSaving(true);
    setMessage(null);
    try {
      const updated = await apiClient.patch<UserSkill>(API_ENDPOINTS.profile.mySkill(skillId), {
        proficiency_level: Number(editProficiency),
        years_experience: editYears === '' ? null : Number(editYears),
      });
      setSkills((prev) => prev.map((s) => (s.skill_id === skillId ? updated : s)));
      setEditingSkillId(null);
      setMessage({ kind: 'success', text: 'Skill updated.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to update skill.') });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSkill = async (skillId: string) => {
    setSaving(true);
    setMessage(null);
    try {
      await apiClient.delete(API_ENDPOINTS.profile.mySkill(skillId));
      setSkills((prev) => prev.filter((s) => s.skill_id !== skillId));
      setMessage({ kind: 'success', text: 'Skill removed.' });
    } catch (err) {
      setMessage({ kind: 'error', text: getApiErrorMessage(err, 'Failed to remove skill.') });
    } finally {
      setSaving(false);
    }
  };

  const availableToAdd = catalog.filter((s) => !skills.some((mine) => mine.skill_id === s.id));
  const student = profile ? isStudentRole(profile.role) : true;

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-secondary-900">Profile</h1>
          <p className="mt-1 text-secondary-600">Manage your details and professional skills.</p>
        </div>

        {message && (
          <div
            role="alert"
            className={`rounded-lg border px-4 py-3 text-sm ${
              message.kind === 'success'
                ? 'border-green-200 bg-green-50 text-green-800'
                : 'border-red-200 bg-red-50 text-red-700'
            }`}
          >
            {message.text}
          </div>
        )}

        {loading || !profile ? (
          <div className="card p-6 text-sm text-secondary-600">Loading profile…</div>
        ) : (
          <>
            <form onSubmit={handleSaveProfile} className="card p-6 space-y-4">
              <h2 className="text-lg font-semibold text-secondary-900">Account details</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="fullName" className="block text-sm font-medium text-secondary-700 mb-1">
                    Full name
                  </label>
                  <input
                    id="fullName"
                    className="input-field"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    disabled={saving}
                  />
                </div>
                <div>
                  <span className="block text-sm font-medium text-secondary-700 mb-1">Email</span>
                  <input className="input-field bg-secondary-50" value={profile.email} disabled readOnly />
                </div>
                <div>
                  <span className="block text-sm font-medium text-secondary-700 mb-1">Role</span>
                  <input className="input-field bg-secondary-50" value={profile.role} disabled readOnly />
                </div>
                <div>
                  <label htmlFor="identifier" className="block text-sm font-medium text-secondary-700 mb-1">
                    {student ? 'Student identifier' : 'Employee identifier'}
                  </label>
                  <input
                    id="identifier"
                    className="input-field"
                    placeholder={student ? 'e.g. CS2021001' : 'e.g. FAC001'}
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    disabled={saving}
                  />
                </div>
                <div>
                  <label htmlFor="department" className="block text-sm font-medium text-secondary-700 mb-1">
                    Department
                  </label>
                  <select
                    id="department"
                    className="input-field"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    disabled={saving}
                  >
                    {DEPARTMENTS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="availability" className="block text-sm font-medium text-secondary-700 mb-1">
                    Availability
                  </label>
                  <select
                    id="availability"
                    className="input-field"
                    value={availability}
                    onChange={(e) => setAvailability(e.target.value)}
                    disabled={saving}
                  >
                    {AVAILABILITY.map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                  </select>
                </div>
                {student ? (
                  <>
                    <div>
                      <label htmlFor="academicYear" className="block text-sm font-medium text-secondary-700 mb-1">
                        Academic year (1–5)
                      </label>
                      <input
                        id="academicYear"
                        type="number"
                        min={1}
                        max={5}
                        className="input-field"
                        value={academicYear}
                        onChange={(e) => setAcademicYear(e.target.value)}
                        disabled={saving}
                      />
                    </div>
                    <div>
                      <label htmlFor="semester" className="block text-sm font-medium text-secondary-700 mb-1">
                        Semester (1–8, optional)
                      </label>
                      <input
                        id="semester"
                        type="number"
                        min={1}
                        max={8}
                        className="input-field"
                        value={semester}
                        onChange={(e) => setSemester(e.target.value)}
                        disabled={saving}
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <label htmlFor="designation" className="block text-sm font-medium text-secondary-700 mb-1">
                        Designation
                      </label>
                      <input
                        id="designation"
                        className="input-field"
                        value={designation}
                        onChange={(e) => setDesignation(e.target.value)}
                        disabled={saving}
                      />
                    </div>
                    <div>
                      <label htmlFor="specialization" className="block text-sm font-medium text-secondary-700 mb-1">
                        Specialization
                      </label>
                      <input
                        id="specialization"
                        className="input-field"
                        value={specialization}
                        onChange={(e) => setSpecialization(e.target.value)}
                        disabled={saving}
                      />
                    </div>
                  </>
                )}
              </div>
              <div>
                <label htmlFor="bio" className="block text-sm font-medium text-secondary-700 mb-1">
                  Bio
                </label>
                <textarea
                  id="bio"
                  rows={3}
                  className="input-field"
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  disabled={saving}
                />
              </div>
              <button type="submit" className="btn-primary px-5 py-2" disabled={saving}>
                {saving ? 'Saving…' : 'Save profile'}
              </button>
            </form>

            <div className="card p-6 space-y-4">
              <h2 className="text-lg font-semibold text-secondary-900">Skills ({skills.length})</h2>

              {skills.length === 0 ? (
                <p className="text-sm text-secondary-600">No skills yet — add your first skill below.</p>
              ) : (
                <ul className="space-y-3">
                  {skills.map((s) => (
                    <li key={s.skill_id} className="rounded-lg border border-secondary-200 p-4">
                      {editingSkillId === s.skill_id ? (
                        <div className="flex flex-wrap items-end gap-3">
                          <div className="font-medium text-secondary-900 w-full">{s.skill?.name ?? s.skill_id}</div>
                          <div>
                            <label className="block text-xs font-medium text-secondary-600 mb-1">Proficiency (1–5)</label>
                            <input
                              type="number"
                              min={1}
                              max={5}
                              className="input-field w-24"
                              value={editProficiency}
                              onChange={(e) => setEditProficiency(e.target.value)}
                              disabled={saving}
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-secondary-600 mb-1">Years experience</label>
                            <input
                              type="number"
                              min={0}
                              className="input-field w-28"
                              value={editYears}
                              onChange={(e) => setEditYears(e.target.value)}
                              disabled={saving}
                              placeholder="—"
                            />
                          </div>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              className="btn-primary text-sm px-3 py-1.5"
                              onClick={() => handleEditSkill(s.skill_id)}
                              disabled={saving}
                            >
                              Save
                            </button>
                            <button
                              type="button"
                              className="btn-secondary text-sm px-3 py-1.5"
                              onClick={() => setEditingSkillId(null)}
                              disabled={saving}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-wrap items-center gap-3">
                          <div className="flex-1 min-w-[12rem]">
                            <div className="font-medium text-secondary-900">{s.skill?.name ?? s.skill_id}</div>
                            <div className="text-xs text-secondary-500">
                              {s.skill?.category ?? ''} · Proficiency {s.proficiency_level}/5
                              {s.years_experience != null ? ` · ${s.years_experience} yrs` : ''}
                              {s.is_verified ? ' · Verified' : ''}
                            </div>
                          </div>
                          <button
                            type="button"
                            className="btn-secondary text-sm px-3 py-1.5"
                            onClick={() => startEditSkill(s)}
                            disabled={saving}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="btn-secondary text-sm px-3 py-1.5 !text-red-700"
                            onClick={() => handleDeleteSkill(s.skill_id)}
                            disabled={saving}
                          >
                            Remove
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              <form onSubmit={handleAddSkill} className="rounded-lg bg-secondary-50 border border-secondary-200 p-4">
                <h3 className="text-sm font-semibold text-secondary-800 mb-3">Add a skill</h3>
                <div className="flex flex-wrap items-end gap-3">
                  <div className="flex-1 min-w-[12rem]">
                    <label htmlFor="newSkill" className="block text-xs font-medium text-secondary-600 mb-1">
                      Skill
                    </label>
                    <select
                      id="newSkill"
                      className="input-field"
                      value={newSkillId}
                      onChange={(e) => setNewSkillId(e.target.value)}
                      disabled={saving}
                    >
                      <option value="">Select a skill…</option>
                      {availableToAdd.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.category})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="newProf" className="block text-xs font-medium text-secondary-600 mb-1">
                      Proficiency (1–5)
                    </label>
                    <input
                      id="newProf"
                      type="number"
                      min={1}
                      max={5}
                      className="input-field w-24"
                      value={newProficiency}
                      onChange={(e) => setNewProficiency(e.target.value)}
                      disabled={saving}
                    />
                  </div>
                  <div>
                    <label htmlFor="newYears" className="block text-xs font-medium text-secondary-600 mb-1">
                      Years (optional)
                    </label>
                    <input
                      id="newYears"
                      type="number"
                      min={0}
                      className="input-field w-28"
                      value={newYears}
                      onChange={(e) => setNewYears(e.target.value)}
                      disabled={saving}
                      placeholder="—"
                    />
                  </div>
                  <button type="submit" className="btn-primary text-sm px-4 py-2" disabled={saving}>
                    Add skill
                  </button>
                </div>
              </form>
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}

export default function ProfilePage() {
  return (
    <RequireAuth>
      <ProfileContent />
    </RequireAuth>
  );
}
