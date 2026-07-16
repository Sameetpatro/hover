package worker

import (
	"context"
	"log"
	"sync"

	"github.com/Sameetpatro/hover/backend/internal/pipeline"
	"github.com/redis/go-redis/v9"
)

const queueKey = "hover:jobs"

type Queue struct {
	Eager  bool
	Runner *pipeline.Runner
	Redis  *redis.Client
	wg     sync.WaitGroup
}

func New(eager bool, runner *pipeline.Runner, redisURL string) *Queue {
	q := &Queue{Eager: eager, Runner: runner}
	if !eager && redisURL != "" {
		opt, err := redis.ParseURL(redisURL)
		if err == nil {
			q.Redis = redis.NewClient(opt)
		}
	}
	return q
}

func (q *Queue) Enqueue(ctx context.Context, jobID string) error {
	if q.Eager || q.Redis == nil {
		q.wg.Add(1)
		go func() {
			defer q.wg.Done()
			if err := q.Runner.Run(context.Background(), jobID); err != nil {
				log.Printf("job %s failed: %v", jobID, err)
			}
		}()
		return nil
	}
	return q.Redis.LPush(ctx, queueKey, jobID).Err()
}

func (q *Queue) StartWorker(ctx context.Context) {
	if q.Eager || q.Redis == nil {
		log.Println("worker: eager mode or no redis — skipping poll loop")
		return
	}
	log.Println("worker: listening on", queueKey)
	for {
		select {
		case <-ctx.Done():
			return
		default:
			res, err := q.Redis.BRPop(ctx, 0, queueKey).Result()
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				log.Printf("redis brpop: %v", err)
				continue
			}
			if len(res) < 2 {
				continue
			}
			jobID := res[1]
			if err := q.Runner.Run(ctx, jobID); err != nil {
				log.Printf("job %s failed: %v", jobID, err)
			}
		}
	}
}

func (q *Queue) Wait() { q.wg.Wait() }
