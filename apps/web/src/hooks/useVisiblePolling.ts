import { useEffect, useRef } from "react";

/** Serial polling; hidden/unmounted scopes cancel in-flight requests and timers. */
export function useVisiblePolling(
  enabled: boolean,
  task: (signal: AbortSignal) => Promise<void>,
  interval: number,
  immediate = false,
) {
  const latest = useRef(task);
  latest.current = task;
  useEffect(() => {
    if (!enabled) return;
    let disposed = false,
      timer: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | undefined,
      failures = 0;
    const stop = () => {
      clearTimeout(timer);
      request?.abort();
    };
    const schedule = (delay: number) => {
      if (!disposed && !document.hidden) timer = setTimeout(run, delay);
    };
    const run = async () => {
      if (disposed || document.hidden) return;
      const c = new AbortController();
      request = c;
      try {
        await latest.current(c.signal);
        failures = 0;
      } catch {
        if (!c.signal.aborted) failures = Math.min(failures + 1, 5);
      } finally {
        if (!c.signal.aborted)
          schedule(Math.min(interval * 2 ** failures, 30000));
      }
    };
    const visibility = () => {
      stop();
      if (!document.hidden) schedule(0);
    };
    document.addEventListener("visibilitychange", visibility);
    schedule(immediate ? 0 : interval);
    return () => {
      disposed = true;
      stop();
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [enabled, interval, immediate]);
}
