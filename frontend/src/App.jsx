import { useRef, useState } from 'react';
import CommandBar from './components/CommandBar';
import ActivityLog from './components/ActivityLog';
import ProfileSettings from './components/ProfileSettings';
import { sendCommand, openTaskSocket } from './api';

export default function App() {
  const [tab, setTab] = useState('command'); // 'command' | 'profile'
  const [entries, setEntries] = useState([]);
  const [isTaskActive, setIsTaskActive] = useState(false);
  const [connStatus, setConnStatus] = useState('idle'); // idle | connected | error
  const wsRef = useRef(null);

  function appendEntry(text, kind) {
    setEntries((prev) => [...prev, kind ? { text, kind } : { text }]);
  }

  async function handleSubmitCommand(command) {
    // Fresh log per run — one command, one clear trace of what happened.
    setEntries([]);
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
        </nav>
        <div className="conn-status">
          <span className={`conn-dot ${connStatus}`} />
          {connStatus === 'connected' ? 'live' : connStatus === 'error' ? 'disconnected' : 'idle'}
        </div>
      </header>

      <main className="app-main">
        {tab === 'command' ? (
          <>
            <CommandBar onSubmit={handleSubmitCommand} disabled={isTaskActive} />
            <ActivityLog entries={entries} isActive={isTaskActive} />
          </>
        ) : (
          <ProfileSettings />
        )}
      </main>
    </div>
  );
}
