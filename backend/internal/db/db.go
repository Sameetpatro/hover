package db

import (
	"database/sql"
	"fmt"

	"github.com/Sameetpatro/hover/backend/internal/config"

	_ "github.com/jackc/pgx/v5/stdlib"
	_ "modernc.org/sqlite"
)

func Open(cfg *config.Config) (*sql.DB, error) {
	var (
		driver string
		dsn    string
	)
	if cfg.UseSQLite {
		driver = "sqlite"
		dsn = cfg.SQLitePath
	} else {
		driver = "pgx"
		dsn = cfg.PostgresDSN
	}
	db, err := sql.Open(driver, dsn)
	if err != nil {
		return nil, err
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ping db: %w", err)
	}
	if cfg.UseSQLite {
		_, _ = db.Exec(`PRAGMA foreign_keys = ON`)
	}
	if err := migrate(db, cfg.UseSQLite); err != nil {
		_ = db.Close()
		return nil, err
	}
	return db, nil
}

func migrate(db *sql.DB, sqlite bool) error {
	stmts := schemaSQLite
	if !sqlite {
		stmts = schemaPostgres
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			return fmt.Errorf("migrate: %w\nstmt: %s", err, s)
		}
	}
	return nil
}

var schemaSQLite = []string{
	`CREATE TABLE IF NOT EXISTS projects (
		id TEXT PRIMARY KEY,
		name TEXT NOT NULL,
		status TEXT NOT NULL,
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)`,
	`CREATE TABLE IF NOT EXISTS uploads (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		s3_key TEXT NOT NULL,
		original_filename TEXT NOT NULL,
		size_bytes INTEGER NOT NULL DEFAULT 0,
		checksum TEXT NOT NULL DEFAULT '',
		status TEXT NOT NULL,
		created_at TEXT NOT NULL
	)`,
	`CREATE TABLE IF NOT EXISTS project_files (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		path TEXT NOT NULL,
		language TEXT NOT NULL DEFAULT '',
		size_bytes INTEGER NOT NULL DEFAULT 0,
		loc INTEGER NOT NULL DEFAULT 0,
		role TEXT NOT NULL DEFAULT '',
		metadata_json TEXT NOT NULL DEFAULT '{}',
		UNIQUE(project_id, path)
	)`,
	`CREATE TABLE IF NOT EXISTS analysis_jobs (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		status TEXT NOT NULL,
		stage TEXT NOT NULL,
		progress REAL NOT NULL DEFAULT 0,
		error TEXT NOT NULL DEFAULT '',
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)`,
	`CREATE TABLE IF NOT EXISTS dependency_nodes (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		key TEXT NOT NULL,
		label TEXT NOT NULL,
		kind TEXT NOT NULL,
		metadata_json TEXT NOT NULL DEFAULT '{}',
		UNIQUE(project_id, key)
	)`,
	`CREATE TABLE IF NOT EXISTS dependency_edges (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		source_key TEXT NOT NULL,
		target_key TEXT NOT NULL,
		edge_type TEXT NOT NULL DEFAULT 'import',
		metadata_json TEXT NOT NULL DEFAULT '{}'
	)`,
	`CREATE TABLE IF NOT EXISTS symbols (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		file_path TEXT NOT NULL,
		name TEXT NOT NULL,
		kind TEXT NOT NULL,
		start_line INTEGER NOT NULL DEFAULT 0,
		end_line INTEGER NOT NULL DEFAULT 0,
		signature TEXT NOT NULL DEFAULT ''
	)`,
	`CREATE TABLE IF NOT EXISTS code_chunks (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		file_path TEXT NOT NULL,
		symbol_name TEXT NOT NULL DEFAULT '',
		language TEXT NOT NULL DEFAULT '',
		start_line INTEGER NOT NULL DEFAULT 0,
		end_line INTEGER NOT NULL DEFAULT 0,
		content TEXT NOT NULL,
		metadata_json TEXT NOT NULL DEFAULT '{}'
	)`,
	`CREATE TABLE IF NOT EXISTS chunk_embeddings (
		id TEXT PRIMARY KEY,
		chunk_id TEXT NOT NULL UNIQUE REFERENCES code_chunks(id) ON DELETE CASCADE,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		embedding_json TEXT NOT NULL DEFAULT '[]'
	)`,
	`CREATE TABLE IF NOT EXISTS architecture_snapshots (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		version INTEGER NOT NULL,
		summary TEXT NOT NULL DEFAULT '',
		data_json TEXT NOT NULL,
		created_at TEXT NOT NULL,
		UNIQUE(project_id, version)
	)`,
}

var schemaPostgres = []string{
	`CREATE TABLE IF NOT EXISTS projects (
		id TEXT PRIMARY KEY,
		name TEXT NOT NULL,
		status TEXT NOT NULL,
		created_at TIMESTAMPTZ NOT NULL,
		updated_at TIMESTAMPTZ NOT NULL
	)`,
	`CREATE TABLE IF NOT EXISTS uploads (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		s3_key TEXT NOT NULL,
		original_filename TEXT NOT NULL,
		size_bytes BIGINT NOT NULL DEFAULT 0,
		checksum TEXT NOT NULL DEFAULT '',
		status TEXT NOT NULL,
		created_at TIMESTAMPTZ NOT NULL
	)`,
	`CREATE TABLE IF NOT EXISTS project_files (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		path TEXT NOT NULL,
		language TEXT NOT NULL DEFAULT '',
		size_bytes BIGINT NOT NULL DEFAULT 0,
		loc INTEGER NOT NULL DEFAULT 0,
		role TEXT NOT NULL DEFAULT '',
		metadata_json TEXT NOT NULL DEFAULT '{}',
		UNIQUE(project_id, path)
	)`,
	`CREATE TABLE IF NOT EXISTS analysis_jobs (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		status TEXT NOT NULL,
		stage TEXT NOT NULL,
		progress DOUBLE PRECISION NOT NULL DEFAULT 0,
		error TEXT NOT NULL DEFAULT '',
		created_at TIMESTAMPTZ NOT NULL,
		updated_at TIMESTAMPTZ NOT NULL
	)`,
	`CREATE TABLE IF NOT EXISTS dependency_nodes (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		key TEXT NOT NULL,
		label TEXT NOT NULL,
		kind TEXT NOT NULL,
		metadata_json TEXT NOT NULL DEFAULT '{}',
		UNIQUE(project_id, key)
	)`,
	`CREATE TABLE IF NOT EXISTS dependency_edges (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		source_key TEXT NOT NULL,
		target_key TEXT NOT NULL,
		edge_type TEXT NOT NULL DEFAULT 'import',
		metadata_json TEXT NOT NULL DEFAULT '{}'
	)`,
	`CREATE TABLE IF NOT EXISTS symbols (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		file_path TEXT NOT NULL,
		name TEXT NOT NULL,
		kind TEXT NOT NULL,
		start_line INTEGER NOT NULL DEFAULT 0,
		end_line INTEGER NOT NULL DEFAULT 0,
		signature TEXT NOT NULL DEFAULT ''
	)`,
	`CREATE TABLE IF NOT EXISTS code_chunks (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		file_path TEXT NOT NULL,
		symbol_name TEXT NOT NULL DEFAULT '',
		language TEXT NOT NULL DEFAULT '',
		start_line INTEGER NOT NULL DEFAULT 0,
		end_line INTEGER NOT NULL DEFAULT 0,
		content TEXT NOT NULL,
		metadata_json TEXT NOT NULL DEFAULT '{}'
	)`,
	`CREATE TABLE IF NOT EXISTS chunk_embeddings (
		id TEXT PRIMARY KEY,
		chunk_id TEXT NOT NULL UNIQUE REFERENCES code_chunks(id) ON DELETE CASCADE,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		embedding_json TEXT NOT NULL DEFAULT '[]'
	)`,
	`CREATE TABLE IF NOT EXISTS architecture_snapshots (
		id TEXT PRIMARY KEY,
		project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
		version INTEGER NOT NULL,
		summary TEXT NOT NULL DEFAULT '',
		data_json TEXT NOT NULL,
		created_at TIMESTAMPTZ NOT NULL,
		UNIQUE(project_id, version)
	)`,
}
