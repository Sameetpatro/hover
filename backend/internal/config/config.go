package config

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
)

type Config struct {
	Addr              string
	UseSQLite         bool
	SQLitePath        string
	PostgresDSN       string
	UseLocalStorage   bool
	EagerWorker       bool
	RedisURL          string
	MediaRoot         string
	ExtractRoot       string
	AWSAccessKey      string
	AWSSecretKey      string
	AWSBucket         string
	AWSEndpoint       string
	AWSRegion         string
	OpenRouterKey     string
	OpenRouterBaseURL string
	ChatModel         string
	EmbeddingModel    string
	EmbeddingDim      int
	HTTPReferer       string
	AppTitle          string
	MaxZipBytes       int64
	MaxExtractedFiles int
}

func Load() (*Config, error) {
	root := findProjectRoot()
	_ = godotenv.Load(filepath.Join(root, ".env"))
	_ = godotenv.Load(filepath.Join(root, ".env.local"))

	cfg := &Config{
		Addr:              getenv("HOVER_ADDR", ":8000"),
		UseSQLite:         getenvBool("USE_SQLITE", true),
		SQLitePath:        getenv("SQLITE_PATH", filepath.Join(root, "backend", "hover.db")),
		UseLocalStorage:   getenvBool("USE_LOCAL_STORAGE", true),
		EagerWorker:       getenvBool("WORKER_EAGER", getenvBool("CELERY_TASK_ALWAYS_EAGER", true)),
		RedisURL:          getenv("REDIS_URL", getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")),
		MediaRoot:         getenv("MEDIA_ROOT", filepath.Join(root, "backend", "media")),
		ExtractRoot:       getenv("EXTRACT_ROOT", filepath.Join(root, "backend", "extracted")),
		AWSAccessKey:      getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
		AWSSecretKey:      getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
		AWSBucket:         getenv("AWS_STORAGE_BUCKET_NAME", "hover"),
		AWSEndpoint:       getenv("AWS_S3_ENDPOINT_URL", "http://localhost:9000"),
		AWSRegion:         getenv("AWS_S3_REGION_NAME", "us-east-1"),
		OpenRouterKey:     firstNonEmpty(os.Getenv("OPENROUTER_API_KEY"), os.Getenv("OPENAI_API_KEY")),
		OpenRouterBaseURL: getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
		ChatModel:         getenv("OPENROUTER_CHAT_MODEL", "openai/gpt-4o-mini"),
		EmbeddingModel:    getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small"),
		EmbeddingDim:      getenvInt("EMBEDDING_DIM", 1536),
		HTTPReferer:       getenv("OPENROUTER_HTTP_REFERER", "http://localhost:5173"),
		AppTitle:          getenv("OPENROUTER_APP_TITLE", "Hover"),
		MaxZipBytes:       int64(getenvInt("MAX_ZIP_BYTES", 200*1024*1024)),
		MaxExtractedFiles: getenvInt("MAX_EXTRACTED_FILES", 5000),
	}

	cfg.PostgresDSN = getenv("DATABASE_URL", buildPostgresDSN())
	_ = os.MkdirAll(cfg.MediaRoot, 0o755)
	_ = os.MkdirAll(cfg.ExtractRoot, 0o755)
	_ = os.MkdirAll(filepath.Dir(cfg.SQLitePath), 0o755)
	return cfg, nil
}

func buildPostgresDSN() string {
	host := getenv("POSTGRES_HOST", "localhost")
	port := getenv("POSTGRES_PORT", "5432")
	user := getenv("POSTGRES_USER", "hover")
	pass := getenv("POSTGRES_PASSWORD", "hover")
	name := getenv("POSTGRES_DB", "hover")
	return "postgres://" + user + ":" + pass + "@" + host + ":" + port + "/" + name + "?sslmode=disable"
}

func findProjectRoot() string {
	wd, err := os.Getwd()
	if err != nil {
		return "."
	}
	dir := wd
	for i := 0; i < 6; i++ {
		if _, err := os.Stat(filepath.Join(dir, ".env")); err == nil {
			return dir
		}
		if _, err := os.Stat(filepath.Join(dir, "docker-compose.yml")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return wd
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func getenvBool(k string, def bool) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(k)))
	if v == "" {
		return def
	}
	return v == "1" || v == "true" || v == "yes"
}

func getenvInt(k string, def int) int {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}
