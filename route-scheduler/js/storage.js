// localStorage wrapped so the app keeps working when storage is blocked or full.
import { validateState } from './model.js';

const KEY = 'route-scheduler.v1';

// Returns { state } for good saved data, { state: null } when nothing is saved,
// or { state: null, discarded: true } when saved data was unreadable and was removed.
export function loadState() {
  let raw;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    return { state: null };
  }
  if (!raw) return { state: null };
  let state = null;
  try {
    state = validateState(JSON.parse(raw));
  } catch {
    state = null;
  }
  if (!state) {
    clearState();
    return { state: null, discarded: true };
  }
  return { state };
}

export function saveState(state) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(state));
    return true;
  } catch {
    return false;
  }
}

export function clearState() {
  try { window.localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}
