package pipeline

import (
	"archive/zip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/Sameetpatro/hover/backend/internal/analysis"
	"github.com/Sameetpatro/hover/backend/internal/architecture"
	"github.com/Sameetpatro/hover/backend/internal/config"
	"github.com/Sameetpatro/hover/backend/internal/llm"
	"github.com/Sameetpatro/hover/backend/internal/storage"
	"github.com/Sameetpatro/hover/backend/internal/store"
)

type Runner struct {
	Cfg     *config.Config
	Store   *store.Store
	Objects storage.ObjectStore
	LLM     *llm.Client
}

var skipDirs = map[string]struct{}{
	"node_modules": {}, ".git": {}, "dist": {}, "build": {}, "__pycache__": {}, ".venv": {}, "venv": {},
}

func (r *Runner) Run(ctx context.Context, jobID string) (err error) {
	job, err := r.Store.GetJob(jobID)
	if err != nil {
		return err
	}
	projectID := job.ProjectID
	_ = r.Store.UpdateJob(jobID, "running", "extracting", 0.05, "")
	_ = r.Store.UpdateProjectStatus(projectID, "processing")

	defer func() {
		if err != nil {
			_ = r.Store.UpdateJob(jobID, "failed", "failed", 1, err.Error())
			_ = r.Store.UpdateProjectStatus(projectID, "failed")
		}
	}()

	upload, err := r.Store.LatestUpload(projectID)
	if err != nil {
		return err
	}

	workDir := filepath.Join(r.Cfg.ExtractRoot, projectID)
	_ = os.RemoveAll(workDir)
	_ = os.MkdirAll(workDir, 0o755)
	zipPath := filepath.Join(workDir, "source.zip")
	extractDir := filepath.Join(workDir, "src")
	_ = os.MkdirAll(extractDir, 0o755)

	if err = r.Objects.Download(ctx, upload.S3Key, zipPath); err != nil {
		return err
	}
	sum, _ := storage.SHA256File(zipPath)
	fi, _ := os.Stat(zipPath)
	upload.Checksum = sum
	if fi != nil {
		upload.SizeBytes = fi.Size()
	}
	upload.Status = "complete"
	_ = r.Store.UpdateUpload(upload)

	_ = r.Store.UpdateJob(jobID, "running", "extracting", 0.15, "")
	extracted, err := extractZip(zipPath, extractDir, r.Cfg.MaxZipBytes, r.Cfg.MaxExtractedFiles)
	if err != nil {
		return err
	}

	root := extractDir
	entries, _ := os.ReadDir(extractDir)
	var dirs []os.DirEntry
	for _, e := range entries {
		if e.Name() == "__MACOSX" {
			continue
		}
		dirs = append(dirs, e)
	}
	if len(dirs) == 1 && dirs[0].IsDir() {
		root = filepath.Join(extractDir, dirs[0].Name())
	}

	type fileRec struct {
		Path string
		Abs  string
		Size int64
		LOC  int
	}
	var records []fileRec
	for _, item := range extracted {
		abs := filepath.Join(extractDir, filepath.FromSlash(item.path))
		rel, err := filepath.Rel(root, abs)
		if err != nil {
			rel = item.path
		}
		rel = filepath.ToSlash(rel)
		records = append(records, fileRec{Path: rel, Abs: filepath.Join(root, filepath.FromSlash(rel)), Size: item.size, LOC: item.loc})
	}

	_ = r.Store.UpdateJob(jobID, "running", "detecting", 0.3, "")
	var analyzed []analysis.AnalyzedFile
	var files []store.ProjectFile
	for _, fr := range records {
		if _, err := os.Stat(fr.Abs); err != nil {
			continue
		}
		a := analysis.AnalyzeFile(fr.Path, fr.Abs)
		analyzed = append(analyzed, a)
		meta, _ := json.Marshal(map[string]any{"imports": a.Imports})
		if len(a.Imports) > 50 {
			meta, _ = json.Marshal(map[string]any{"imports": a.Imports[:50]})
		}
		files = append(files, store.ProjectFile{
			Path: a.Path, Language: a.Language, SizeBytes: fr.Size, LOC: a.LOC, Role: a.Role, Metadata: meta,
		})
	}
	if err = r.Store.ReplaceFiles(projectID, files); err != nil {
		return err
	}

	_ = r.Store.UpdateJob(jobID, "running", "analyzing", 0.45, "")
	nodes, edges := analysis.BuildGraph(analyzed)
	if err = r.Store.ReplaceGraph(projectID, nodes, edges); err != nil {
		return err
	}
	var symbols []map[string]any
	for _, a := range analyzed {
		for _, s := range a.Symbols {
			symbols = append(symbols, map[string]any{
				"file": a.Path, "name": s.Name, "kind": s.Kind,
				"start_line": s.StartLine, "end_line": s.EndLine, "signature": s.Signature,
			})
		}
	}
	if err = r.Store.ReplaceSymbols(projectID, symbols); err != nil {
		return err
	}

	_ = r.Store.UpdateJob(jobID, "running", "chunking", 0.6, "")
	var chunkDefs []map[string]any
	var chunkMeta []struct {
		file string
		ch   map[string]any
	}
	for _, a := range analyzed {
		abs := filepath.Join(root, filepath.FromSlash(a.Path))
		for _, ch := range analysis.ChunkFile(a, abs, 1800) {
			chunkMeta = append(chunkMeta, struct {
				file string
				ch   map[string]any
			}{a.Path, ch})
			chunkDefs = append(chunkDefs, ch)
		}
	}

	_ = r.Store.UpdateJob(jobID, "running", "embedding", 0.75, "")
	texts := make([]string, len(chunkMeta))
	for i, cm := range chunkMeta {
		content, _ := cm.ch["content"].(string)
		sym, _ := cm.ch["symbol_name"].(string)
		texts[i] = fmt.Sprintf("File: %s\nSymbol: %s\n%s", cm.file, sym, content)
	}
	vecs, err := r.LLM.Embed(ctx, texts)
	if err != nil {
		return err
	}
	chunks := make([]store.Chunk, 0, len(chunkMeta))
	for i, cm := range chunkMeta {
		meta, _ := json.Marshal(cm.ch["metadata"])
		start, _ := cm.ch["start_line"].(int)
		end, _ := cm.ch["end_line"].(int)
		// JSON numbers may be float64 if from map - handle via fmt
		if start == 0 {
			start = toInt(cm.ch["start_line"])
		}
		if end == 0 {
			end = toInt(cm.ch["end_line"])
		}
		content, _ := cm.ch["content"].(string)
		sym, _ := cm.ch["symbol_name"].(string)
		lang, _ := cm.ch["language"].(string)
		emb := []float64{}
		if i < len(vecs) {
			emb = vecs[i]
		}
		chunks = append(chunks, store.Chunk{
			ProjectID: projectID, FilePath: cm.file, SymbolName: sym, Language: lang,
			StartLine: start, EndLine: end, Content: content, Metadata: string(meta), Embedding: emb,
		})
	}
	if err = r.Store.ReplaceChunks(projectID, chunks); err != nil {
		return err
	}

	_ = r.Store.UpdateJob(jobID, "running", "indexed", 0.85, "")
	_ = r.Store.UpdateJob(jobID, "running", "generating", 0.9, "")
	arch, err := architecture.Generate(ctx, r.Store, r.LLM, projectID)
	if err != nil {
		return err
	}
	if _, err = r.Store.SaveArchitecture(projectID, arch.Summary, arch); err != nil {
		return err
	}

	_ = r.Store.UpdateJob(jobID, "succeeded", "ready", 1.0, "")
	_ = r.Store.UpdateProjectStatus(projectID, "ready")
	return nil
}

func toInt(v any) int {
	switch t := v.(type) {
	case int:
		return t
	case float64:
		return int(t)
	default:
		return 0
	}
}

type zipItem struct {
	path string
	size int64
	loc  int
}

func extractZip(zipPath, dest string, maxBytes int64, maxFiles int) ([]zipItem, error) {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return nil, err
	}
	defer r.Close()

	var out []zipItem
	var total int64
	for _, f := range r.File {
		name := filepath.ToSlash(f.Name)
		if f.FileInfo().IsDir() || shouldSkip(name) {
			continue
		}
		if strings.HasPrefix(name, "/") || strings.Contains(name, "..") {
			continue
		}
		total += int64(f.UncompressedSize64)
		if total > maxBytes {
			return nil, fmt.Errorf("extracted archive exceeds size limit")
		}
		if len(out) >= maxFiles {
			return nil, fmt.Errorf("extracted archive exceeds file count limit")
		}
		target, err := storage.SafeJoin(dest, name)
		if err != nil {
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return nil, err
		}
		rc, err := f.Open()
		if err != nil {
			return nil, err
		}
		w, err := os.Create(target)
		if err != nil {
			rc.Close()
			return nil, err
		}
		_, err = io.Copy(w, rc)
		w.Close()
		rc.Close()
		if err != nil {
			return nil, err
		}
		b, _ := os.ReadFile(target)
		loc := strings.Count(string(b), "\n")
		if len(b) > 0 {
			loc++
		}
		out = append(out, zipItem{path: name, size: int64(f.UncompressedSize64), loc: loc})
	}
	return out, nil
}

func shouldSkip(path string) bool {
	if strings.HasPrefix(path, "__MACOSX/") {
		return true
	}
	parts := strings.Split(path, "/")
	for _, p := range parts {
		if _, ok := skipDirs[p]; ok {
			return true
		}
		if strings.HasPrefix(p, ".") {
			return true
		}
	}
	base := filepath.Base(path)
	return base == ".DS_Store" || base == "Thumbs.db"
}
