import { useState, useCallback, useRef } from "react";
import { api } from "../api/client";
import type { ManualIngestJobRecord } from "../api/types";

export function usePollingJob() {
  const [job, setJob] = useState<ManualIngestJobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const start = useCallback(
    (jobId: string) => {
      stop();
      const poll = async () => {
        try {
          const j = await api.getManualJob(jobId);
          setJob(j);
          if (j.status === "succeeded" || j.status === "failed") {
            stop();
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : "Poll error");
          stop();
        }
      };
      poll();
      timerRef.current = setInterval(poll, 2000);
    },
    [stop],
  );

  return { job, error, start, stop };
}
