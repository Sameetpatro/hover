package llm

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"math"

	"github.com/Sameetpatro/hover/backend/internal/config"
	openai "github.com/sashabaranov/go-openai"
)

type Client struct {
	cfg    *config.Config
	client *openai.Client
}

func New(cfg *config.Config) *Client {
	c := &Client{cfg: cfg}
	if cfg.OpenRouterKey == "" {
		return c
	}
	ocfg := openai.DefaultConfig(cfg.OpenRouterKey)
	ocfg.BaseURL = cfg.OpenRouterBaseURL
	ocfg.OrgID = ""
	client := openai.NewClientWithConfig(ocfg)
	c.client = client
	return c
}

func (c *Client) Configured() bool { return c.client != nil }

func (c *Client) Embed(ctx context.Context, texts []string) ([][]float64, error) {
	dim := c.cfg.EmbeddingDim
	if len(texts) == 0 {
		return nil, nil
	}
	if !c.Configured() {
		out := make([][]float64, len(texts))
		for i, t := range texts {
			out[i] = hashEmbed(t, dim)
		}
		return out, nil
	}
	var all [][]float64
	for i := 0; i < len(texts); i += 64 {
		end := i + 64
		if end > len(texts) {
			end = len(texts)
		}
		batch := texts[i:end]
		resp, err := c.client.CreateEmbeddings(ctx, openai.EmbeddingRequest{
			Input: batch,
			Model: openai.EmbeddingModel(c.cfg.EmbeddingModel),
		})
		if err != nil {
			return nil, err
		}
		// order by index
		tmp := make([][]float64, len(batch))
		for _, d := range resp.Data {
			tmp[d.Index] = float32To64(d.Embedding)
		}
		all = append(all, tmp...)
	}
	return all, nil
}

func (c *Client) ChatJSON(ctx context.Context, system, user string) (string, error) {
	if !c.Configured() {
		return "", nil
	}
	req := openai.ChatCompletionRequest{
		Model: c.cfg.ChatModel,
		Messages: []openai.ChatCompletionMessage{
			{Role: openai.ChatMessageRoleSystem, Content: system},
			{Role: openai.ChatMessageRoleUser, Content: user},
		},
		Temperature: 0.2,
	}
	// OpenRouter optional headers via custom transport would be nicer;
	// go-openai doesn't expose default headers easily — key+base URL is enough.
	resp, err := c.client.CreateChatCompletion(ctx, req)
	if err != nil {
		return "", err
	}
	if len(resp.Choices) == 0 {
		return "", nil
	}
	return resp.Choices[0].Message.Content, nil
}

func float32To64(in []float32) []float64 {
	out := make([]float64, len(in))
	for i, v := range in {
		out[i] = float64(v)
	}
	return out
}

func hashEmbed(text string, dim int) []float64 {
	vec := make([]float64, dim)
	tokens := stringsFields(text)
	if len(tokens) == 0 {
		tokens = []string{"empty"}
	}
	for _, tok := range tokens {
		sum := sha256.Sum256([]byte(tok))
		for i := 0; i+4 <= len(sum) && i < dim; i += 4 {
			idx := binary.BigEndian.Uint32(sum[i:i+4]) % uint32(dim)
			vec[idx] += 1
		}
	}
	var norm float64
	for _, v := range vec {
		norm += v * v
	}
	norm = math.Sqrt(norm)
	if norm == 0 {
		norm = 1
	}
	for i := range vec {
		vec[i] /= norm
	}
	return vec
}

func stringsFields(s string) []string {
	var out []string
	start := -1
	for i, r := range s {
		isSpace := r == ' ' || r == '\n' || r == '\t' || r == '\r'
		if !isSpace && start < 0 {
			start = i
		}
		if isSpace && start >= 0 {
			out = append(out, toLowerASCII(s[start:i]))
			start = -1
		}
	}
	if start >= 0 {
		out = append(out, toLowerASCII(s[start:]))
	}
	return out
}

func toLowerASCII(s string) string {
	b := make([]byte, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'A' && c <= 'Z' {
			c += 32
		}
		b[i] = c
	}
	return string(b)
}

func Cosine(a, b []float64) float64 {
	if len(a) == 0 || len(a) != len(b) {
		return 0
	}
	var dot, na, nb float64
	for i := range a {
		dot += a[i] * b[i]
		na += a[i] * a[i]
		nb += b[i] * b[i]
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return dot / (math.Sqrt(na) * math.Sqrt(nb))
}
