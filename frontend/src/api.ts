// Simple frontend API helper.
// Vite proxies /api → FastAPI on :8000.

export type Project = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type AnalysisJob = {
  id: string;
  project_id: string;
  status: string;
  stage: string;
  progress: number;
  error: string;
  created_at: string;
  updated_at: string;
};

export type ArchitectureLayer = {
  id: string;
  label: string;
  role: string;
};

export type ArchitectureComponent = {
  id: string;
  name: string;
  layer_id: string;
  kind: string;
  files: string[];
  description: string;
};

export type FlowStep = {
  from: string;
  to: string;
  via: string;
  data: string;
};

export type ArchitectureFlow = {
  id: string;
  label: string;
  steps: FlowStep[];
};

export type ArchitectureData = {
  project_name: string;
  summary: string;
  layers: ArchitectureLayer[];
  components: ArchitectureComponent[];
  flows: ArchitectureFlow[];
  entrypoints: string[];
  data_stores: string[];
};

export type ArchitectureSnapshot = {
  id: string;
  version: number;
  summary: string;
  data: ArchitectureData;
  created_at: string;
};

const BASE = "/api";

async function call<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => call<{ status: string }>("/health/"),

  listProjects: () => call<Project[]>("/projects/"),

  createProject: (name: string) =>
    call<Project>("/projects/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  getProject: (id: string) => call<Project>(`/projects/${id}/`),

  // Upload the ZIP file (multipart form)
  uploadFile: async (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("filename", file.name);
    return call<{ upload_id: string; s3_key: string; direct: boolean }>(
      `/projects/${projectId}/uploads/`,
      { method: "POST", body: form },
    );
  },

  // Tell the backend: "file is ready — start analysis"
  completeUpload: (projectId: string, uploadId: string) =>
    call<AnalysisJob>(`/projects/${projectId}/uploads/complete/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId }),
    }),

  getJob: (jobId: string) => call<AnalysisJob>(`/jobs/${jobId}/`),

  getTree: (projectId: string) =>
    call<{
      files: { path: string; language: string; role: string; loc: number }[];
      count: number;
    }>(`/projects/${projectId}/tree/`),

  getArchitecture: (projectId: string) =>
    call<ArchitectureSnapshot>(`/projects/${projectId}/architecture/`),

  regenerateArchitecture: (projectId: string) =>
    call<ArchitectureSnapshot>(`/projects/${projectId}/architecture/generate/`, {
      method: "POST",
    }),
};
