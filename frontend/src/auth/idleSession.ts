/** Fermeture de session après ce délai sans action de l'utilisateur. */
export const IDLE_TIMEOUT_MS = 2 * 60 * 1000;

const ACTIVITY_KEY = "finflow_last_activity";
const IDLE_NOTICE_KEY = "finflow_idle_notice";
const WRITE_EVERY_MS = 5 * 1000;

export function touchSessionActivity(force = false) {
  const now = Date.now();
  const current = Number(localStorage.getItem(ACTIVITY_KEY) || 0);
  if (!force && Number.isFinite(current) && now - current < WRITE_EVERY_MS) return;
  localStorage.setItem(ACTIVITY_KEY, String(now));
}

export function sessionIsIdle(now = Date.now()): boolean {
  const raw = localStorage.getItem(ACTIVITY_KEY);
  if (!raw) return false;
  const then = Number(raw);
  if (!Number.isFinite(then)) return false;
  return now - then >= IDLE_TIMEOUT_MS;
}

export function clearSessionActivity() {
  localStorage.removeItem(ACTIVITY_KEY);
}

export function markIdleLogout() {
  localStorage.setItem(IDLE_NOTICE_KEY, "1");
}

export function peekIdleNotice(): boolean {
  return localStorage.getItem(IDLE_NOTICE_KEY) === "1";
}

export function clearIdleNotice() {
  localStorage.removeItem(IDLE_NOTICE_KEY);
}
