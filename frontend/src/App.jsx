import { useRef, useState } from 'react';
import CommandBar from './components/CommandBar';
import ActivityLog from './components/ActivityLog';
import ProfileSettings from './components/ProfileSettings';
import SummariesPanel from './components/SummariesPanel';
import { sendCommand, openTaskSocket, submitForm } from './api';

export default function App() {
  const [tab, setTab] = useState('command'); // 'command' | 'profile' | 'summaries'
  const [entries, setEntries] = useState([]);
  const [isTaskActive, setIsTaskActive] = useState(false);
  const [connStatus, setConnStatus] = useState('idle'); // idle | connected | error
  const [submitStatus, setSubmitStatus] = useState(null); // { ok: bool, message: string }
  const [submitting, setSubmitting] = useState(false);
  const wsRef = useRef(null);

  // Module 1's safety gate lives here: this button only shows up after the
  // agent has actually filled fields, and it calls a completely separate
  // endpoint (/form/submit) that the LLM itself can never reach.
  const hasFilledFields = entries.some((e) => e.text?.includes('Filled field'));

  function appendEntry(text, kind) {
    setEntries((prev) => [...prev, kind ? { text, kind } : { text }]);
  }

  async function handleApproveSubmit() {
    setSubmitting(true);
    setSubmitStatus(null);
    try {
      const { result } = await submitForm();
      setSubmitStatus({ ok: !result.startsWith('❌'), message: result });
    } catch (err) {
      setSubmitStatus({ ok: false, message: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmitCommand(command) {
    // Fresh log per run — one command, one clear trace of what happened.
    setEntries([]);
    setSubmitStatus(null);
    setIsTaskActive(true);
    setConnStatus('idle');

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    try {
      const { task_id } = await sendCommand(command);
      const ws = openTaskSocket(task_id);
      wsRef.current = ws;

      ws.onopen = () => setConnStatus('connected');
      ws.onerror = () => setConnStatus('error');
      ws.onclose = () => setConnStatus('idle');

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);

        if (msg.type === 'history') {
          const task = msg.task;
          const stepEntries = (task.steps || []).map((s, i) =>
            i === 0 ? { text: s.message, kind: 'command' } : { text: s.message }
          );
          setEntries(stepEntries);
          if (task.status === 'completed' || task.status === 'failed') {
            setIsTaskActive(false);
            if (task.status === 'failed' && task.error) {
              appendEntry(`Failed: ${task.error}`);
            }
          }
        } else if (msg.type === 'step') {
          appendEntry(msg.message);
        } else if (msg.type === 'status') {
          if (msg.status === 'completed' || msg.status === 'failed') {
            setIsTaskActive(false);
          }
          if (msg.status === 'failed' && msg.error) {
            appendEntry(`Failed: ${msg.error}`);
          }
        }
      };
    } catch (err) {
      appendEntry(`Could not reach the backend: ${err.message}`);
      setIsTaskActive(false);
      setConnStatus('error');
    }
  }

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-title">
          <span className="dot" />
          Agent Console
        </div>
        <nav className="app-nav">
          <button className={tab === 'command' ? 'active' : ''} onClick={() => setTab('command')}>
            Command
          </button>
          <button className={tab === 'profile' ? 'active' : ''} onClick={() => setTab('profile')}>
            Profile
          </button>
          <button className={tab === 'summaries' ? 'active' : ''} onClick={() => setTab('summaries')}>
            Summaries
          </button>
        </nav>
        <div className="conn-status">
          <span className={`conn-dot ${connStatus}`} />
          {connStatus === 'connected' ? 'live' : connStatus === 'error' ? 'disconnected' : 'idle'}
        </div>
      </header>

      <main className="app-main">
        {tab === 'command' && (
          <>
            <CommandBar onSubmit={handleSubmitCommand} disabled={isTaskActive} />
            <ActivityLog entries={entries} isActive={isTaskActive} />
            {hasFilledFields && !isTaskActive && (
              <div className="command-bar" style={{ justifyContent: 'space-between' }}>
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                  Fields were filled above — review them, then approve to actually submit the form.
                </span>
                <button onClick={handleApproveSubmit} disabled={submitting}>
                  {submitting ? 'Submitting…' : 'Approve & Submit Form'}
                </button>
              </div>
            )}
            {submitStatus && (
              <div className={`save-status ${submitStatus.ok ? 'ok' : 'err'}`}>{submitStatus.message}</div>
            )}
          </>
        )}
        {tab === 'profile' && <ProfileSettings />}
        {tab === 'summaries' && <SummariesPanel />}
      </main>
    </div>
  );
}
