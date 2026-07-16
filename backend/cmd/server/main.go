package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/Sameetpatro/hover/backend/internal/api"
	"github.com/Sameetpatro/hover/backend/internal/config"
	"github.com/Sameetpatro/hover/backend/internal/db"
	"github.com/Sameetpatro/hover/backend/internal/llm"
	"github.com/Sameetpatro/hover/backend/internal/pipeline"
	"github.com/Sameetpatro/hover/backend/internal/storage"
	"github.com/Sameetpatro/hover/backend/internal/store"
	"github.com/Sameetpatro/hover/backend/internal/worker"
)

func main() {
	mode := flag.String("mode", "server", "server | worker | all")
	flag.Parse()

	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}

	sqlDB, err := db.Open(cfg)
	if err != nil {
		log.Fatal(err)
	}
	defer sqlDB.Close()

	st := store.New(sqlDB, !cfg.UseSQLite)
	objs, err := storage.New(cfg)
	if err != nil {
		log.Fatal(err)
	}
	llmClient := llm.New(cfg)
	runner := &pipeline.Runner{Cfg: cfg, Store: st, Objects: objs, LLM: llmClient}
	q := worker.New(cfg.EagerWorker, runner, cfg.RedisURL)

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	switch *mode {
	case "worker":
		q.StartWorker(ctx)
		return
	case "all":
		go q.StartWorker(ctx)
	}

	h := &api.Handler{Store: st, Queue: q, LLM: llmClient, Objects: objs}
	srv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           api.NewRouter(h),
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Printf("hover go api listening on %s (sqlite=%v eager=%v)", cfg.Addr, cfg.UseSQLite, cfg.EagerWorker)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()

	<-ctx.Done()
	shutdownCtx, c := context.WithTimeout(context.Background(), 10*time.Second)
	defer c()
	_ = srv.Shutdown(shutdownCtx)
	q.Wait()
}
