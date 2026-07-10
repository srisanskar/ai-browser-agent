// Talks to the Week 5 FastAPI backend.
// Change this if your backend runs somewhere other than localhost:8000.
export const API_BASE = 'http://localhost:8000';
export const WS_BASE = 'ws://localhost:8000';

export async function sendCommand(command) {
  const res = await fetch(`${API_BASE}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  });
  if (!res.ok) {
    throw new Error(`POST /command failed: ${res.status}`);
  }
  return res.json(); // { task_id, status }
}

export async function getStatus(taskId) {
  const res = await fetch(`${API_BASE}/status/${taskId}`);
  if (!res.ok) {
    throw new Error(`GET /status failed: ${res.status}`);
  }
  return res.json();
}

export async function getProfile() {
  const res = await fetch(`${API_BASE}/user/profile`);
  if (!res.ok) {
    throw new Error(`GET /user/profile failed: ${res.status}`);
  }
  return res.json();
}

export async function saveProfile(profile) {
  const res = await fetch(`${API_BASE}/user/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  if (!res.ok) {
    throw new Error(`POST /user/profile failed: ${res.status}`);
  }
  return res.json();
}

export async function submitForm() {
  const res = await fetch(`${API_BASE}/form/submit`, { method: 'POST' });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `POST /form/submit failed: ${res.status}`);
  }
  return res.json(); // { result: "..." }
}

export async function getSummaries() {
  const res = await fetch(`${API_BASE}/summaries`);
  if (!res.ok) {
    throw new Error(`GET /summaries failed: ${res.status}`);
  }
  return res.json();
}

export function openTaskSocket(taskId) {
  return new WebSocket(`${WS_BASE}/ws/${taskId}`);
}
