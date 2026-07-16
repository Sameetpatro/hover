package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/Sameetpatro/hover/backend/internal/architecture"
	"github.com/Sameetpatro/hover/backend/internal/llm"
	"github.com/Sameetpatro/hover/backend/internal/storage"
	"github.com/Sameetpatro/hover/backend/internal/store"
	"github.com/Sameetpatro/hover/backend/internal/worker"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
	"github.com/google/uuid"
)

type Handler struct {
	Store   *store.Store
	Queue   *worker.Queue
	LLM     *llm.Client
	Objects storage.ObjectStore
}

func NewRouter(h *Handler) http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins: []string{"http://localhost:5173", "http://127.0.0.1:5173", "*"},
		AllowedMethods: []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders: []string{"Accept", "Authorization", "Content-Type"},
	}))

	r.Route("/api", func(r chi.Router) {
		r.Get("/health/", h.Health)
		r.Get("/projects/", h.ListProjects)
		r.Post("/projects/", h.CreateProject)
		r.Get("/projects/{projectID}/", h.GetProject)
		r.Post("/projects/{projectID}/uploads/", h.CreateUpload)
		r.Post("/projects/{projectID}/uploads/complete/", h.CompleteUpload)
		r.Get("/projects/{projectID}/tree/", h.Tree)
		r.Get("/projects/{projectID}/graph/", h.Graph)
		r.Get("/projects/{projectID}/symbols/", h.Symbols)
		r.Get("/projects/{projectID}/architecture/", h.GetArchitecture)
		r.Post("/projects/{projectID}/architecture/generate/", h.GenerateArchitecture)
		r.Get("/jobs/{jobID}/", h.GetJob)
	})
	return r
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"detail": msg})
}

func (h *Handler) Health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, 200, map[string]string{"status": "ok", "service": "hover"})
}

func projectJSON(p *store.Project) map[string]any {
	return map[string]any{
		"id": p.ID, "name": p.Name, "status": p.Status,
		"created_at": p.CreatedAt.Format(time.RFC3339Nano),
		"updated_at": p.UpdatedAt.Format(time.RFC3339Nano),
	}
}

func jobJSON(j *store.AnalysisJob) map[string]any {
	return map[string]any{
		"id": j.ID, "project_id": j.ProjectID, "status": j.Status, "stage": j.Stage,
		"progress": j.Progress, "error": j.Error,
		"created_at": j.CreatedAt.Format(time.RFC3339Nano),
		"updated_at": j.UpdatedAt.Format(time.RFC3339Nano),
	}
}

func (h *Handler) ListProjects(w http.ResponseWriter, _ *http.Request) {
	list, err := h.Store.ListProjects()
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	out := make([]map[string]any, 0, len(list))
	for i := range list {
		out = append(out, projectJSON(&list[i]))
	}
	writeJSON(w, 200, out)
}

func (h *Handler) CreateProject(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Name string `json:"name"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	if strings.TrimSpace(body.Name) == "" {
		body.Name = "Untitled Project"
	}
	p, err := h.Store.CreateProject(body.Name)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 201, projectJSON(p))
}

func (h *Handler) GetProject(w http.ResponseWriter, r *http.Request) {
	p, err := h.Store.GetProject(chi.URLParam(r, "projectID"))
	if err != nil {
		writeErr(w, 404, "Not found")
		return
	}
	writeJSON(w, 200, projectJSON(p))
}

func (h *Handler) CreateUpload(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	if _, err := h.Store.GetProject(projectID); err != nil {
		writeErr(w, 404, "Not found")
		return
	}
	if err := r.ParseMultipartForm(200 << 20); err != nil {
		writeErr(w, 400, "expected multipart file")
		return
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		writeErr(w, 400, "file required")
		return
	}
	defer file.Close()

	filename := header.Filename
	if filename == "" {
		filename = "project.zip"
	}
	key := "projects/" + projectID + "/" + uuid.NewString() + "_" + filepath.Base(filename)
	payload, err := io.ReadAll(file)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	size := int64(len(payload))
	if err := h.Objects.Upload(r.Context(), key, bytes.NewReader(payload), size, "application/zip"); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	up, err := h.Store.CreateUpload(projectID, key, filename, size, "uploaded")
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	_ = h.Store.UpdateProjectStatus(projectID, "uploading")
	writeJSON(w, 201, map[string]any{"upload_id": up.ID, "s3_key": key, "direct": true})
}

func (h *Handler) CompleteUpload(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	if _, err := h.Store.GetProject(projectID); err != nil {
		writeErr(w, 404, "Not found")
		return
	}
	var body struct {
		UploadID string `json:"upload_id"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)

	var up *store.Upload
	var err error
	if body.UploadID != "" {
		up, err = h.Store.GetUpload(body.UploadID)
	} else {
		up, err = h.Store.LatestUpload(projectID)
	}
	if err != nil || up.ProjectID != projectID {
		writeErr(w, 400, "No upload found")
		return
	}
	up.Status = "uploaded"
	_ = h.Store.UpdateUpload(up)

	job, err := h.Store.CreateJob(projectID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	_ = h.Store.UpdateProjectStatus(projectID, "queued")
	if err := h.Queue.Enqueue(r.Context(), job.ID); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 202, jobJSON(job))
}

func (h *Handler) GetJob(w http.ResponseWriter, r *http.Request) {
	j, err := h.Store.GetJob(chi.URLParam(r, "jobID"))
	if err != nil {
		writeErr(w, 404, "Not found")
		return
	}
	writeJSON(w, 200, jobJSON(j))
}

func (h *Handler) Tree(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	files, err := h.Store.ListFiles(projectID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"project_id": projectID, "files": files, "count": len(files)})
}

func (h *Handler) Graph(w http.ResponseWriter, r *http.Request) {
	nodes, edges, err := h.Store.ListGraph(chi.URLParam(r, "projectID"))
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"nodes": nodes, "edges": edges})
}

func (h *Handler) Symbols(w http.ResponseWriter, r *http.Request) {
	syms, err := h.Store.ListSymbols(chi.URLParam(r, "projectID"), 2000)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, syms)
}

func (h *Handler) GetArchitecture(w http.ResponseWriter, r *http.Request) {
	snap, err := h.Store.LatestArchitecture(chi.URLParam(r, "projectID"))
	if err != nil {
		writeErr(w, 404, "Architecture not generated yet")
		return
	}
	writeJSON(w, 200, map[string]any{
		"id": snap.ID, "version": snap.Version, "summary": snap.Summary,
		"data": json.RawMessage(snap.Data), "created_at": snap.CreatedAt.Format(time.RFC3339Nano),
	})
}

func (h *Handler) GenerateArchitecture(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	data, err := architecture.Generate(r.Context(), h.Store, h.LLM, projectID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	snap, err := h.Store.SaveArchitecture(projectID, data.Summary, data)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 201, map[string]any{
		"id": snap.ID, "version": snap.Version, "summary": snap.Summary,
		"data": json.RawMessage(snap.Data), "created_at": snap.CreatedAt.Format(time.RFC3339Nano),
	})
}
