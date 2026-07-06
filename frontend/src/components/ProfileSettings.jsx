import { useEffect, useState } from 'react';
import { getProfile, saveProfile } from '../api';

const EMPTY_PROFILE = { name: '', email: '', phone: '', address: '', resume_text: '' };

export default function ProfileSettings() {
  const [profile, setProfile] = useState(EMPTY_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null); // { ok: bool, message: string }

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((data) => {
        if (cancelled) return;
        setProfile({ ...EMPTY_PROFILE, ...data });
      })
      .catch(() => {
        if (!cancelled) setStatus({ ok: false, message: 'Could not load profile — is the backend running?' });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  function update(field, value) {
    setProfile((p) => ({ ...p, [field]: value }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      await saveProfile(profile);
      setStatus({ ok: true, message: 'Saved.' });
    } catch (err) {
      setStatus({ ok: false, message: 'Save failed — check the backend terminal.' });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="profile-panel">
        <p className="subtitle">Loading profile…</p>
      </div>
    );
  }

  return (
    <div className="profile-panel">
      <h2>Profile</h2>
      <p className="subtitle">This is the memory the agent reads from — name, contact details, and resume text.</p>
      <form onSubmit={handleSave}>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="name">Name</label>
            <input id="name" value={profile.name || ''} onChange={(e) => update('name', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" value={profile.email || ''} onChange={(e) => update('email', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="phone">Phone</label>
            <input id="phone" value={profile.phone || ''} onChange={(e) => update('phone', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="address">Address</label>
            <input id="address" value={profile.address || ''} onChange={(e) => update('address', e.target.value)} />
          </div>
          <div className="field full">
            <label htmlFor="resume_text">Resume text</label>
            <textarea id="resume_text" value={profile.resume_text || ''} onChange={(e) => update('resume_text', e.target.value)} />
          </div>
        </div>
        <div className="profile-actions">
          <button className="btn-primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          {status && (
            <span className={`save-status ${status.ok ? 'ok' : 'err'}`}>{status.message}</span>
          )}
        </div>
      </form>
    </div>
  );
}
