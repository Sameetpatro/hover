package store

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

type Project struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type Upload struct {
	ID               string    `json:"id"`
	ProjectID        string    `json:"project_id"`
	S3Key            string    `json:"s3_key"`
	OriginalFilename string    `json:"original_filename"`
	SizeBytes        int64     `json:"size_bytes"`
	Checksum         string    `json:"checksum"`
	Status           string    `json:"status"`
	CreatedAt        time.Time `json:"created_at"`
}

type AnalysisJob struct {
	ID        string    `json:"id"`
	ProjectID string    `json:"project_id"`
	Status    string    `json:"status"`
	Stage     string    `json:"stage"`
	Progress  float64   `json:"progress"`
	Error     string    `json:"error"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type ProjectFile struct {
	ID        string          `json:"id"`
	ProjectID string          `json:"-"`
	Path      string          `json:"path"`
	Language  string          `json:"language"`
	SizeBytes int64           `json:"size_bytes"`
	LOC       int             `json:"loc"`
	Role      string          `json:"role"`
	Metadata  json.RawMessage `json:"metadata"`
}

type ArchitectureSnapshot struct {
	ID        string          `json:"id"`
	ProjectID string          `json:"-"`
	Version   int             `json:"version"`
	Summary   string          `json:"summary"`
	Data      json.RawMessage `json:"data"`
	CreatedAt time.Time       `json:"created_at"`
}

type Store struct {
	DB       *sql.DB
	Postgres bool
}

func New(db *sql.DB, postgres bool) *Store { return &Store{DB: db, Postgres: postgres} }

func (s *Store) q(query string) string { return rebind(s.Postgres, query) }

func now() time.Time { return time.Now().UTC() }

func formatTime(t time.Time) string { return t.UTC().Format(time.RFC3339Nano) }

func parseTime(s string) time.Time {
	t, err := time.Parse(time.RFC3339Nano, s)
	if err != nil {
		t, _ = time.Parse(time.RFC3339, s)
	}
	return t
}

func (s *Store) CreateProject(name string) (*Project, error) {
	p := &Project{
		ID:        uuid.NewString(),
		Name:      name,
		Status:    "created",
		CreatedAt: now(),
		UpdatedAt: now(),
	}
	_, err := s.DB.Exec(s.q(`INSERT INTO projects (id, name, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)`),
		p.ID, p.Name, p.Status, formatTime(p.CreatedAt), formatTime(p.UpdatedAt),
	)
	return p, err
}

func (s *Store) ListProjects() ([]Project, error) {
	rows, err := s.DB.Query(s.q(`SELECT id, name, status, created_at, updated_at FROM projects ORDER BY created_at DESC`))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Project
	for rows.Next() {
		var p Project
		var c, u string
		if err := rows.Scan(&p.ID, &p.Name, &p.Status, &c, &u); err != nil {
			return nil, err
		}
		p.CreatedAt, p.UpdatedAt = parseTime(c), parseTime(u)
		out = append(out, p)
	}
	if out == nil {
		out = []Project{}
	}
	return out, rows.Err()
}

func (s *Store) GetProject(id string) (*Project, error) {
	var p Project
	var c, u string
	err := s.DB.QueryRow(s.q(`SELECT id, name, status, created_at, updated_at FROM projects WHERE id = ?`), id,
	).Scan(&p.ID, &p.Name, &p.Status, &c, &u)
	if err != nil {
		return nil, err
	}
	p.CreatedAt, p.UpdatedAt = parseTime(c), parseTime(u)
	return &p, nil
}

func (s *Store) UpdateProjectStatus(id, status string) error {
	_, err := s.DB.Exec(s.q(`UPDATE projects SET status = ?, updated_at = ? WHERE id = ?`),
		status, formatTime(now()), id,
	)
	return err
}

func (s *Store) CreateUpload(projectID, key, filename string, size int64, status string) (*Upload, error) {
	u := &Upload{
		ID:               uuid.NewString(),
		ProjectID:        projectID,
		S3Key:            key,
		OriginalFilename: filename,
		SizeBytes:        size,
		Status:           status,
		CreatedAt:        now(),
	}
	_, err := s.DB.Exec(s.q(`INSERT INTO uploads (id, project_id, s3_key, original_filename, size_bytes, checksum, status, created_at)
		 VALUES (?, ?, ?, ?, ?, '', ?, ?)`),
		u.ID, u.ProjectID, u.S3Key, u.OriginalFilename, u.SizeBytes, u.Status, formatTime(u.CreatedAt),
	)
	return u, err
}

func (s *Store) GetUpload(id string) (*Upload, error) {
	var u Upload
	var c string
	err := s.DB.QueryRow(s.q(`SELECT id, project_id, s3_key, original_filename, size_bytes, checksum, status, created_at FROM uploads WHERE id = ?`), id,
	).Scan(&u.ID, &u.ProjectID, &u.S3Key, &u.OriginalFilename, &u.SizeBytes, &u.Checksum, &u.Status, &c)
	if err != nil {
		return nil, err
	}
	u.CreatedAt = parseTime(c)
	return &u, nil
}

func (s *Store) LatestUpload(projectID string) (*Upload, error) {
	var u Upload
	var c string
	err := s.DB.QueryRow(s.q(`SELECT id, project_id, s3_key, original_filename, size_bytes, checksum, status, created_at
		 FROM uploads WHERE project_id = ? ORDER BY created_at DESC LIMIT 1`), projectID,
	).Scan(&u.ID, &u.ProjectID, &u.S3Key, &u.OriginalFilename, &u.SizeBytes, &u.Checksum, &u.Status, &c)
	if err != nil {
		return nil, err
	}
	u.CreatedAt = parseTime(c)
	return &u, nil
}

func (s *Store) UpdateUpload(u *Upload) error {
	_, err := s.DB.Exec(s.q(`UPDATE uploads SET size_bytes = ?, checksum = ?, status = ? WHERE id = ?`),
		u.SizeBytes, u.Checksum, u.Status, u.ID,
	)
	return err
}

func (s *Store) CreateJob(projectID string) (*AnalysisJob, error) {
	j := &AnalysisJob{
		ID:        uuid.NewString(),
		ProjectID: projectID,
		Status:    "queued",
		Stage:     "queued",
		Progress:  0,
		CreatedAt: now(),
		UpdatedAt: now(),
	}
	_, err := s.DB.Exec(s.q(`INSERT INTO analysis_jobs (id, project_id, status, stage, progress, error, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, '', ?, ?)`),
		j.ID, j.ProjectID, j.Status, j.Stage, j.Progress, formatTime(j.CreatedAt), formatTime(j.UpdatedAt),
	)
	return j, err
}

func (s *Store) GetJob(id string) (*AnalysisJob, error) {
	var j AnalysisJob
	var c, u string
	err := s.DB.QueryRow(s.q(`SELECT id, project_id, status, stage, progress, error, created_at, updated_at FROM analysis_jobs WHERE id = ?`), id,
	).Scan(&j.ID, &j.ProjectID, &j.Status, &j.Stage, &j.Progress, &j.Error, &c, &u)
	if err != nil {
		return nil, err
	}
	j.CreatedAt, j.UpdatedAt = parseTime(c), parseTime(u)
	return &j, nil
}

func (s *Store) UpdateJob(id, status, stage string, progress float64, errMsg string) error {
	_, err := s.DB.Exec(s.q(`UPDATE analysis_jobs SET status = ?, stage = ?, progress = ?, error = ?, updated_at = ? WHERE id = ?`),
		status, stage, progress, errMsg, formatTime(now()), id,
	)
	return err
}

func (s *Store) ReplaceFiles(projectID string, files []ProjectFile) error {
	tx, err := s.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(s.q(`DELETE FROM project_files WHERE project_id = ?`), projectID); err != nil {
		return err
	}
	for _, f := range files {
		if f.ID == "" {
			f.ID = uuid.NewString()
		}
		meta := f.Metadata
		if len(meta) == 0 {
			meta = json.RawMessage(`{}`)
		}
		if _, err := tx.Exec(s.q(`INSERT INTO project_files (id, project_id, path, language, size_bytes, loc, role, metadata_json)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?)`),
			f.ID, projectID, f.Path, f.Language, f.SizeBytes, f.LOC, f.Role, string(meta),
		); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (s *Store) ListFiles(projectID string) ([]ProjectFile, error) {
	rows, err := s.DB.Query(s.q(`SELECT id, path, language, size_bytes, loc, role, metadata_json FROM project_files WHERE project_id = ? ORDER BY path`),
		projectID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ProjectFile
	for rows.Next() {
		var f ProjectFile
		var meta string
		if err := rows.Scan(&f.ID, &f.Path, &f.Language, &f.SizeBytes, &f.LOC, &f.Role, &meta); err != nil {
			return nil, err
		}
		f.ProjectID = projectID
		f.Metadata = json.RawMessage(meta)
		out = append(out, f)
	}
	if out == nil {
		out = []ProjectFile{}
	}
	return out, rows.Err()
}

func (s *Store) ReplaceGraph(projectID string, nodes []map[string]any, edges []map[string]any) error {
	tx, err := s.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(s.q(`DELETE FROM dependency_edges WHERE project_id = ?`), projectID); err != nil {
		return err
	}
	if _, err := tx.Exec(s.q(`DELETE FROM dependency_nodes WHERE project_id = ?`), projectID); err != nil {
		return err
	}
	for _, n := range nodes {
		meta, _ := json.Marshal(n["metadata"])
		if meta == nil {
			meta = []byte(`{}`)
		}
		if _, err := tx.Exec(s.q(`INSERT INTO dependency_nodes (id, project_id, key, label, kind, metadata_json) VALUES (?, ?, ?, ?, ?, ?)`),
			uuid.NewString(), projectID, n["key"], n["label"], n["kind"], string(meta),
		); err != nil {
			return err
		}
	}
	for _, e := range edges {
		meta, _ := json.Marshal(e["metadata"])
		if meta == nil {
			meta = []byte(`{}`)
		}
		if _, err := tx.Exec(s.q(`INSERT INTO dependency_edges (id, project_id, source_key, target_key, edge_type, metadata_json) VALUES (?, ?, ?, ?, ?, ?)`),
			uuid.NewString(), projectID, e["source"], e["target"], e["edge_type"], string(meta),
		); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (s *Store) ListGraph(projectID string) (nodes []map[string]any, edges []map[string]any, err error) {
	nrows, err := s.DB.Query(s.q(`SELECT id, key, label, kind, metadata_json FROM dependency_nodes WHERE project_id = ?`), projectID)
	if err != nil {
		return nil, nil, err
	}
	defer nrows.Close()
	for nrows.Next() {
		var id, key, label, kind, meta string
		if err := nrows.Scan(&id, &key, &label, &kind, &meta); err != nil {
			return nil, nil, err
		}
		var md any
		_ = json.Unmarshal([]byte(meta), &md)
		nodes = append(nodes, map[string]any{"id": id, "key": key, "label": label, "kind": kind, "metadata": md})
	}
	erows, err := s.DB.Query(s.q(`SELECT id, source_key, target_key, edge_type, metadata_json FROM dependency_edges WHERE project_id = ?`), projectID)
	if err != nil {
		return nil, nil, err
	}
	defer erows.Close()
	for erows.Next() {
		var id, src, tgt, et, meta string
		if err := erows.Scan(&id, &src, &tgt, &et, &meta); err != nil {
			return nil, nil, err
		}
		var md any
		_ = json.Unmarshal([]byte(meta), &md)
		edges = append(edges, map[string]any{"id": id, "source": src, "target": tgt, "edge_type": et, "metadata": md})
	}
	if nodes == nil {
		nodes = []map[string]any{}
	}
	if edges == nil {
		edges = []map[string]any{}
	}
	return nodes, edges, nil
}

func (s *Store) ReplaceSymbols(projectID string, symbols []map[string]any) error {
	tx, err := s.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(s.q(`DELETE FROM symbols WHERE project_id = ?`), projectID); err != nil {
		return err
	}
	for _, sym := range symbols {
		if _, err := tx.Exec(s.q(`INSERT INTO symbols (id, project_id, file_path, name, kind, start_line, end_line, signature) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`),
			uuid.NewString(), projectID, sym["file"], sym["name"], sym["kind"], sym["start_line"], sym["end_line"], sym["signature"],
		); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (s *Store) ListSymbols(projectID string, limit int) ([]map[string]any, error) {
	if limit <= 0 {
		limit = 2000
	}
	rows, err := s.DB.Query(s.q(`SELECT id, name, kind, file_path, start_line, end_line, signature FROM symbols WHERE project_id = ? LIMIT ?`),
		projectID, limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []map[string]any
	for rows.Next() {
		var id, name, kind, file, sig string
		var start, end int
		if err := rows.Scan(&id, &name, &kind, &file, &start, &end, &sig); err != nil {
			return nil, err
		}
		out = append(out, map[string]any{
			"id": id, "name": name, "kind": kind, "file": file, "start_line": start, "end_line": end, "signature": sig,
		})
	}
	if out == nil {
		out = []map[string]any{}
	}
	return out, rows.Err()
}

type Chunk struct {
	ID         string
	ProjectID  string
	FilePath   string
	SymbolName string
	Language   string
	StartLine  int
	EndLine    int
	Content    string
	Metadata   string
	Embedding  []float64
}

func (s *Store) ReplaceChunks(projectID string, chunks []Chunk) error {
	tx, err := s.DB.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(s.q(`DELETE FROM chunk_embeddings WHERE project_id = ?`), projectID); err != nil {
		return err
	}
	if _, err := tx.Exec(s.q(`DELETE FROM code_chunks WHERE project_id = ?`), projectID); err != nil {
		return err
	}
	for _, c := range chunks {
		cid := uuid.NewString()
		if c.Metadata == "" {
			c.Metadata = "{}"
		}
		if _, err := tx.Exec(s.q(`INSERT INTO code_chunks (id, project_id, file_path, symbol_name, language, start_line, end_line, content, metadata_json)
			 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`),
			cid, projectID, c.FilePath, c.SymbolName, c.Language, c.StartLine, c.EndLine, c.Content, c.Metadata,
		); err != nil {
			return err
		}
		emb, _ := json.Marshal(c.Embedding)
		if _, err := tx.Exec(s.q(`INSERT INTO chunk_embeddings (id, chunk_id, project_id, embedding_json) VALUES (?, ?, ?, ?)`),
			uuid.NewString(), cid, projectID, string(emb),
		); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (s *Store) ListChunksWithEmbeddings(projectID string) ([]Chunk, error) {
	rows, err := s.DB.Query(s.q(`
		SELECT c.id, c.file_path, c.symbol_name, c.language, c.start_line, c.end_line, c.content, e.embedding_json
		FROM code_chunks c
		JOIN chunk_embeddings e ON e.chunk_id = c.id
		WHERE c.project_id = ?`), projectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Chunk
	for rows.Next() {
		var c Chunk
		var emb string
		if err := rows.Scan(&c.ID, &c.FilePath, &c.SymbolName, &c.Language, &c.StartLine, &c.EndLine, &c.Content, &emb); err != nil {
			return nil, err
		}
		c.ProjectID = projectID
		_ = json.Unmarshal([]byte(emb), &c.Embedding)
		out = append(out, c)
	}
	return out, rows.Err()
}

func (s *Store) SaveArchitecture(projectID, summary string, data any) (*ArchitectureSnapshot, error) {
	var version int
	_ = s.DB.QueryRow(s.q(`SELECT COALESCE(MAX(version), 0) FROM architecture_snapshots WHERE project_id = ?`), projectID).Scan(&version)
	version++
	raw, err := json.Marshal(data)
	if err != nil {
		return nil, err
	}
	snap := &ArchitectureSnapshot{
		ID:        uuid.NewString(),
		ProjectID: projectID,
		Version:   version,
		Summary:   summary,
		Data:      raw,
		CreatedAt: now(),
	}
	_, err = s.DB.Exec(s.q(`INSERT INTO architecture_snapshots (id, project_id, version, summary, data_json, created_at) VALUES (?, ?, ?, ?, ?, ?)`),
		snap.ID, projectID, snap.Version, snap.Summary, string(raw), formatTime(snap.CreatedAt),
	)
	return snap, err
}

func (s *Store) LatestArchitecture(projectID string) (*ArchitectureSnapshot, error) {
	var snap ArchitectureSnapshot
	var data, created string
	err := s.DB.QueryRow(s.q(`SELECT id, version, summary, data_json, created_at FROM architecture_snapshots WHERE project_id = ? ORDER BY version DESC LIMIT 1`),
		projectID,
	).Scan(&snap.ID, &snap.Version, &snap.Summary, &data, &created)
	if err != nil {
		return nil, err
	}
	snap.ProjectID = projectID
	snap.Data = json.RawMessage(data)
	snap.CreatedAt = parseTime(created)
	return &snap, nil
}

func (s *Store) GetNodesAndEdgesRaw(projectID string) (nodes []map[string]any, edges []map[string]any, err error) {
	return s.ListGraph(projectID)
}

func ErrNotFound(err error) bool {
	return err == sql.ErrNoRows
}

func Wrap(err error, msg string) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("%s: %w", msg, err)
}
