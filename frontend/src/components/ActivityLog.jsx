import { useEffect, useRef } from 'react';

// Turns a raw step/history message into { type, text } for rendering.
// type drives the marker + color: command | reasoning | success | error | result
function classifyStep(message) {
  if (message.startsWith('Failed:')) {
    return { type: 'error', marker: '✗' };
  }
  if (message.startsWith('Agent decided to call tool')) {
    return { type: 'reasoning', marker: '▸' };
  }
  if (message.startsWith('Agent:')) {
    return { type: 'result', marker: '◆' };
  }
  if (message.includes('❌') || message.toLowerCase().includes('error')) {
    return { type: 'error', marker: '✗' };
  }
  if (message.includes('✅') || message.includes('returned:')) {
    return { type: 'success', marker: '✓' };
  }
  return { type: 'reasoning', marker: '▸' };
}

export default function ActivityLog({ entries, isActive }) {
  const bodyRef = useRef(null);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <div className="activity-log">
      <div className="activity-log-header">
        <span>Live Activity</span>
        <span>{entries.length} event{entries.length === 1 ? '' : 's'}</span>
      </div>
      <div className="activity-log-body" ref={bodyRef}>
        {entries.length === 0 && (
          <div className="log-empty">
            Waiting for a command — type one above and hit Run.
          </div>
        )}
        {entries.map((entry, i) => {
          const isCommand = entry.kind === 'command';
          const { type, marker } = isCommand
            ? { type: 'command', marker: '●' }
            : classifyStep(entry.text);
          return (
            <div className={`log-line ${type}`} key={i}>
              <span className="marker">{marker}</span>
              <span className="text">{entry.text}</span>
            </div>
          );
        })}
        {isActive && <span className="log-cursor" />}
      </div>
    </div>
  );
}
