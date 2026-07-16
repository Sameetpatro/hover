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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health/"),
  listProjects: () => request<Project[]>("/projects/"),
  createProject: (name: string) =>
    request<Project>("/projects/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  getProject: (id: string) => request<Project>(`/projects/${id}/`),
  uploadFile: async (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("filename", file.name);
    return request<{ upload_id: string; s3_key: string; direct: boolean }>(
      `/projects/${projectId}/uploads/`,
      { method: "POST", body: form },
    );
  },
  completeUpload: (projectId: string, uploadId: string) =>
    request<AnalysisJob>(`/projects/${projectId}/uploads/complete/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId }),
    }),
  getJob: (jobId: string) => request<AnalysisJob>(`/jobs/${jobId}/`),
  getTree: (projectId: string) =>
    request<{ files: { path: string; language: string; role: string; loc: number }[]; count: number }>(
      `/projects/${projectId}/tree/`,
    ),
  getArchitecture: (projectId: string) =>
    request<ArchitectureSnapshot>(`/projects/${projectId}/architecture/`),
  regenerateArchitecture: (projectId: string) =>
    request<ArchitectureSnapshot>(`/projects/${projectId}/architecture/generate/`, {
      method: "POST",
    }),
};
