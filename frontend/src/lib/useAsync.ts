import { useCallback, useEffect, useRef, useState } from "react";
import { isAbort } from "../api/client";

export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: unknown };

/**
 * Runs `task` whenever `deps` change, cancelling the previous run. Passing `enabled: false`
 * leaves the state idle, for requests that need a profile the student has not entered yet.
 */
export function useAsync<T>(
  task: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  enabled = true,
): AsyncState<T> & { retry: () => void } {
  const [state, setState] = useState<AsyncState<T>>(enabled ? { status: "loading" } : { status: "idle" });
  const [attempt, setAttempt] = useState(0);
  const taskRef = useRef(task);
  taskRef.current = task;

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading" });
    taskRef
      .current(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: "success", data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && !isAbort(error)) setState({ status: "error", error });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { ...state, retry };
}
