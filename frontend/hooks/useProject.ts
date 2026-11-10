"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "../services/api";

export function useProjectId() {
  const params = useSearchParams();
  const [pid, setPid] = useState<string | null>(null);
  useEffect(() => {
    const p = params.get("project") || localStorage.getItem("currentProject");
    if (p) { setPid(p); localStorage.setItem("currentProject", p); }
  }, [params]);
  return pid;
}

export function useProject(pollMs = 0) {
  const pid = useProjectId();
  const [project, setProject] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!pid) return;
    let stop = false;
    const load = () => api.project(pid).then((p) => !stop && setProject(p)).catch((e) => !stop && setError(String(e.message || e)));
    load();
    const t = pollMs ? setInterval(load, pollMs) : null;
    return () => { stop = true; if (t) clearInterval(t); };
  }, [pid, pollMs]);
  return { pid, project, error };
}
