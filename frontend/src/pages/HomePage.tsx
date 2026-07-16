import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type AnalysisJob, type Project } from "../api";
import "../App.css";

const STAGES = [
  "queued",
  "extracting",
  "detecting",
  "analyzing",
  "chunking",
  "embedding",
  "indexed",
  "generating",
  "ready",
];

function StageStrip({ stage }: { stage: string }) {
  const idx = STAGES.indexOf(stage);
  return (
    <div className="stage-strip">
      {STAGES.map((s, i) => (
        <div
          key={s}
          className={`stage-chip ${i <= idx ? "active" : ""} ${s === stage ? "current" : ""}`}
        >
          {s}
        </div>
      ))}
    </div>
  );
}

export function HomePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);

  const refreshProjects = useCallback(async () => {
    try {
      const list = await api.listProjects();
      setProjects(list);
    } catch {
      /* backend may be down */
    }
  }, []);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  useEffect(() => {
    if (!job || job.status === "succeeded" || job.status === "failed") return;
    const id = window.setInterval(async () => {
      try {
        const next = await api.getJob(job.id);
        setJob(next);
        if (next.status === "succeeded" && project) {
          navigate(`/projects/${project.id}/visualize`);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Job poll failed");
      }
    }, 1200);
    return () => window.clearInterval(id);
  }, [job, navigate, project]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };

  const start = async () => {
    if (!file) {
      setError("Drop a project ZIP first");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const p = await api.createProject(name.trim() || file.name.replace(/\.zip$/i, ""));
      setProject(p);
      const up = await api.uploadFile(p.id, file);
      const j = await api.completeUpload(p.id, up.upload_id);
      setJob(j);
      await refreshProjects();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const progressPct = useMemo(
    () => Math.round((job?.progress ?? 0) * 100),
    [job],
  );

  return (
    <div className="page">
      <div className="atmosphere" />
      <header className="top">
        <div className="brand">HOVER</div>
        <p className="tagline">See your system move.</p>
      </header>

      <main className="hero-upload">
        <div
          className={`dropzone ${dragOver ? "over" : ""} ${file ? "has-file" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <input
            type="file"
            accept=".zip,application/zip"
            id="zip"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <label htmlFor="zip">
            {file ? (
              <>
                <span className="file-name">{file.name}</span>
                <span className="hint">{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
              </>
            ) : (
              <>
                <span className="drop-title">Drop project ZIP</span>
                <span className="hint">or click to browse</span>
              </>
            )}
          </label>
        </div>

        <div className="controls">
          <input
            className="name-input"
            placeholder="Project name (optional)"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="cta" disabled={busy || !file} onClick={start}>
            {busy ? "Uploading…" : "Analyze & Visualize"}
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {job && (
          <section className="job-panel">
            <div className="job-meta">
              <span>Stage: {job.stage}</span>
              <span>{progressPct}%</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${progressPct}%` }} />
            </div>
            <StageStrip stage={job.stage} />
            {job.error && <p className="error">{job.error}</p>}
            {job.status === "succeeded" && project && (
              <Link className="cta ghost" to={`/projects/${project.id}/visualize`}>
                Open visualization
              </Link>
            )}
          </section>
        )}

        {projects.length > 0 && (
          <section className="recent">
            <h2>Recent</h2>
            <ul>
              {projects.slice(0, 8).map((p) => (
                <li key={p.id}>
                  <Link to={`/projects/${p.id}/visualize`}>
                    <strong>{p.name}</strong>
                    <span>{p.status}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
