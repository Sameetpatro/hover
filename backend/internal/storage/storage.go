package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"github.com/Sameetpatro/hover/backend/internal/config"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type ObjectStore interface {
	Upload(ctx context.Context, key string, r io.Reader, size int64, contentType string) error
	Download(ctx context.Context, key, dest string) error
}

type LocalStore struct {
	Root string
}

func (l *LocalStore) path(key string) string {
	return filepath.Join(l.Root, "uploads", filepath.FromSlash(key))
}

func (l *LocalStore) Upload(_ context.Context, key string, r io.Reader, _ int64, _ string) error {
	dest := l.path(key)
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(f, r)
	return err
}

func (l *LocalStore) Download(_ context.Context, key, dest string) error {
	src := l.path(key)
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}

type S3Store struct {
	client *minio.Client
	bucket string
}

func New(cfg *config.Config) (ObjectStore, error) {
	if cfg.UseLocalStorage {
		return &LocalStore{Root: cfg.MediaRoot}, nil
	}
	endpoint := cfg.AWSEndpoint
	u, err := url.Parse(endpoint)
	if err != nil {
		return nil, err
	}
	secure := u.Scheme == "https"
	host := u.Host
	client, err := minio.New(host, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AWSAccessKey, cfg.AWSSecretKey, ""),
		Secure: secure,
		Region: cfg.AWSRegion,
	})
	if err != nil {
		return nil, err
	}
	ctx := context.Background()
	exists, err := client.BucketExists(ctx, cfg.AWSBucket)
	if err != nil {
		return nil, err
	}
	if !exists {
		if err := client.MakeBucket(ctx, cfg.AWSBucket, minio.MakeBucketOptions{Region: cfg.AWSRegion}); err != nil {
			return nil, err
		}
	}
	return &S3Store{client: client, bucket: cfg.AWSBucket}, nil
}

func (s *S3Store) Upload(ctx context.Context, key string, r io.Reader, size int64, contentType string) error {
	if contentType == "" {
		contentType = "application/zip"
	}
	_, err := s.client.PutObject(ctx, s.bucket, key, r, size, minio.PutObjectOptions{ContentType: contentType})
	return err
}

func (s *S3Store) Download(ctx context.Context, key, dest string) error {
	obj, err := s.client.GetObject(ctx, s.bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return err
	}
	defer obj.Close()
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, obj)
	return err
}

func SHA256File(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func SafeJoin(root, name string) (string, error) {
	clean := filepath.Clean("/" + strings.ReplaceAll(name, "\\", "/"))
	clean = strings.TrimPrefix(clean, "/")
	full := filepath.Join(root, clean)
	rel, err := filepath.Rel(root, full)
	if err != nil || strings.HasPrefix(rel, "..") {
		return "", fmt.Errorf("unsafe path: %s", name)
	}
	return full, nil
}
