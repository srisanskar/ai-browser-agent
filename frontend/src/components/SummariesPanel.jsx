import { useEffect, useState } from 'react';
import { getSummaries } from '../api';

export default function SummariesPanel() {
  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getSummaries()
      .then((data) => { if (!cancelled) setSummaries(data); })
      .catch(() => { if (!cancelled) setError('Could not load summaries — is the backend running?'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return <div className="profile-panel"><p className="subtitle">Loading summaries…</p></div>;
  }

  return (
    <div className="profile-panel">
      <h2>Saved Summaries</h2>
      <p className="subtitle">
        Every page you've asked the agent to summarize — saved automatically.
      </p>
      {error && <p className="save-status err">{error}</p>}
      {!error && summaries.length === 0 && (
        <p className="subtitle">No summaries yet — try "summarize this" or "summarize https://..." from the Command tab.</p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {summaries.map((s) => {
          let parsed;
          try { parsed = JSON.parse(s.summary_text); } catch { parsed = null; }
          return (
            <div key={s.id} style={{
              background: 'var(--panel-raised)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: 14,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 13 }}>{s.title || s.source_url || 'Untitled'}</strong>
                <span style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                  {new Date(s.created_at).toLocaleString()}
                </span>
              </div>
              {s.source_url && (
                <a href={s.source_url} target="_blank" rel="noreferrer"
                   style={{ fontSize: 12, color: 'var(--accent)', wordBreak: 'break-all' }}>
                  {s.source_url}
                </a>
              )}
              <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 8 }}>
                {parsed?.tldr || 'No TL;DR available.'}
              </p>
              {parsed?.tags?.length > 0 && (
                <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {parsed.tags.map((t, i) => (
                    <span key={i} style={{
                      fontSize: 11, color: 'var(--success)', border: '1px solid var(--success-soft)',
                      borderRadius: 4, padding: '2px 8px', fontFamily: 'var(--font-mono)',
                    }}>{t}</span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
