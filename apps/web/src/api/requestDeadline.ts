import { ApiError } from "./documents";
/** Bounds the complete fetch/body operation; outer cancellation remains distinct. */
export async function requestDeadline<T>(
  signal: AbortSignal,
  operation: (signal: AbortSignal) => Promise<T>,
  milliseconds = 10000,
): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  if (signal.aborted) controller.abort();
  else signal.addEventListener("abort", cancel, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, milliseconds);
  try {
    const result = await operation(controller.signal);
    if (controller.signal.aborted)
      throw new DOMException("Aborted", "AbortError");
    return result;
  } catch (error) {
    if (timedOut && !signal.aborted) throw new ApiError(408);
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", cancel);
  }
}
