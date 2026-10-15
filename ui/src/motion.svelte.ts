/** Whether decorative motion should stop: the visitor paused it, or their OS asks for less. */
const KEY = "agent-harness-demo:motion-paused";

function stored(): boolean {
  try {
    return localStorage.getItem(KEY) === "true";
  } catch {
    return false;
  }
}

const reduced = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;

export const motion = $state({ paused: stored(), reduced: reduced?.matches ?? false });

reduced?.addEventListener("change", (event) => (motion.reduced = event.matches));

export function toggleMotion() {
  motion.paused = !motion.paused;
  try {
    localStorage.setItem(KEY, String(motion.paused));
  } catch {
    // Private windows can refuse storage; the toggle still works for this page.
  }
}
