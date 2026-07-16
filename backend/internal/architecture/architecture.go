package architecture

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"github.com/Sameetpatro/hover/backend/internal/llm"
	"github.com/Sameetpatro/hover/backend/internal/store"
	"github.com/google/uuid"
)

type Data struct {
	ProjectName string      `json:"project_name"`
	Summary     string      `json:"summary"`
	Layers      []Layer     `json:"layers"`
	Components  []Component `json:"components"`
	Flows       []Flow      `json:"flows"`
	Entrypoints []string    `json:"entrypoints"`
	DataStores  []string    `json:"data_stores"`
}

type Layer struct {
	ID    string `json:"id"`
	Label string `json:"label"`
	Role  string `json:"role"`
}

type Component struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	LayerID     string   `json:"layer_id"`
	Kind        string   `json:"kind"`
	Files       []string `json:"files"`
	Description string   `json:"description"`
}

type Flow struct {
	ID    string     `json:"id"`
	Label string     `json:"label"`
	Steps []FlowStep `json:"steps"`
}

type FlowStep struct {
	From string `json:"from"`
	To   string `json:"to"`
	Via  string `json:"via"`
	Data string `json:"data"`
}

func roleToLayer(role string) string {
	switch role {
	case "ui", "entry":
		return "client"
	case "api":
		return "api"
	case "db":
		return "data"
	default:
		return "services"
	}
}

func roleToKind(role string) string {
	switch role {
	case "ui":
		return "ui"
	case "entry":
		return "entry"
	case "api":
		return "controller"
	case "worker":
		return "worker"
	case "db":
		return "model"
	case "config":
		return "config"
	default:
		return "service"
	}
}

func Heuristic(project *store.Project, files []store.ProjectFile, symbols []map[string]any, edges []map[string]any) Data {
	layers := []Layer{
		{ID: "client", Label: "Client", Role: "entry"},
		{ID: "api", Label: "API", Role: "gateway"},
		{ID: "services", Label: "Services", Role: "logic"},
		{ID: "data", Label: "Data", Role: "store"},
	}

	buckets := map[string][]store.ProjectFile{}
	for _, f := range files {
		switch f.Language {
		case "unknown", "markdown", "json", "yaml", "toml", "css", "scss":
			continue
		}
		parts := strings.Split(filepath.ToSlash(f.Path), "/")
		top := "root"
		if len(parts) > 0 {
			top = parts[0]
		}
		key := roleToLayer(f.Role) + "::" + top + "::" + f.Role
		buckets[key] = append(buckets[key], f)
	}

	var components []Component
	fileToComp := map[string]string{}
	for key, group := range buckets {
		parts := strings.Split(key, "::")
		layerID, top, role := parts[0], parts[1], parts[2]
		id := "c_" + uuid.NewString()[:10]
		name := top
		switch role {
		case "api":
			name = top + " API"
		case "ui":
			name = top + " UI"
		case "db":
			name = top + " Models"
		case "worker":
			name = top + " Workers"
		}
		filesList := make([]string, 0, len(group))
		for _, g := range group {
			filesList = append(filesList, g.Path)
			fileToComp[g.Path] = id
		}
		components = append(components, Component{
			ID: id, Name: name, LayerID: layerID, Kind: roleToKind(role),
			Files: filesList, Description: fmt.Sprintf("%d files · role=%s", len(group), role),
		})
	}

	var ui, api, svc, data, worker []Component
	for _, c := range components {
		switch c.Kind {
		case "ui":
			ui = append(ui, c)
		case "controller":
			api = append(api, c)
		case "service":
			svc = append(svc, c)
		case "model":
			data = append(data, c)
		case "worker":
			worker = append(worker, c)
		}
	}

	var flows []Flow
	if len(ui) > 0 && len(api) > 0 {
		steps := []FlowStep{{From: ui[0].ID, To: api[0].ID, Via: "HTTP", Data: "Request"}}
		if len(svc) > 0 {
			steps = append(steps, FlowStep{From: api[0].ID, To: svc[0].ID, Via: "call", Data: "Domain call"})
			if len(data) > 0 {
				steps = append(steps, FlowStep{From: svc[0].ID, To: data[0].ID, Via: "db", Data: "Persist"})
			}
		} else if len(data) > 0 {
			steps = append(steps, FlowStep{From: api[0].ID, To: data[0].ID, Via: "db", Data: "Query"})
		}
		flows = append(flows, Flow{ID: "flow_" + uuid.NewString()[:8], Label: "Client request path", Steps: steps})
	}
	if len(api) > 0 && len(worker) > 0 {
		steps := []FlowStep{{From: api[0].ID, To: worker[0].ID, Via: "queue", Data: "Job"}}
		if len(data) > 0 {
			steps = append(steps, FlowStep{From: worker[0].ID, To: data[0].ID, Via: "db", Data: "Write"})
		}
		flows = append(flows, Flow{ID: "flow_" + uuid.NewString()[:8], Label: "Async job path", Steps: steps})
	}
	if len(edges) > 0 && len(components) >= 2 {
		type pair struct{ a, b string }
		counts := map[pair]int{}
		for _, e := range edges {
			src, _ := e["source"].(string)
			tgt, _ := e["target"].(string)
			a, ok1 := fileToComp[src]
			b, ok2 := fileToComp[tgt]
			if ok1 && ok2 && a != b {
				counts[pair{a, b}]++
			}
		}
		var best pair
		bestN := 0
		for p, n := range counts {
			if n > bestN {
				best, bestN = p, n
			}
		}
		if bestN > 0 {
			flows = append(flows, Flow{
				ID: "flow_" + uuid.NewString()[:8], Label: "Module dependency flow",
				Steps: []FlowStep{{From: best.a, To: best.b, Via: "import", Data: "Module"}},
			})
		}
	}
	if len(flows) == 0 && len(components) >= 2 {
		flows = append(flows, Flow{
			ID: "flow_" + uuid.NewString()[:8], Label: "Primary path",
			Steps: []FlowStep{{From: components[0].ID, To: components[1].ID, Via: "call", Data: "Data"}},
		})
	}

	langCount := map[string]int{}
	for _, f := range files {
		if f.Language != "" && f.Language != "unknown" {
			langCount[f.Language]++
		}
	}
	type kv struct {
		k string
		v int
	}
	var langs []kv
	for k, v := range langCount {
		langs = append(langs, kv{k, v})
	}
	sort.Slice(langs, func(i, j int) bool { return langs[i].v > langs[j].v })
	var top []string
	for i := 0; i < len(langs) && i < 3; i++ {
		top = append(top, langs[i].k)
	}
	topLangs := strings.Join(top, ", ")
	if topLangs == "" {
		topLangs = "mixed"
	}

	var entrypoints []string
	for _, f := range files {
		base := filepath.Base(f.Path)
		if f.Role == "entry" || base == "main.py" || base == "app.py" || base == "index.ts" || base == "manage.py" || base == "main.go" {
			entrypoints = append(entrypoints, f.Path)
		}
	}
	for _, s := range symbols {
		if s["kind"] == "endpoint" {
			entrypoints = append(entrypoints, fmt.Sprintf("%v:%v", s["file"], s["name"]))
		}
		if len(entrypoints) > 12 {
			break
		}
	}

	var stores []string
	for _, c := range data {
		stores = append(stores, c.ID)
	}

	return Data{
		ProjectName: project.Name,
		Summary:     fmt.Sprintf("%s: %d files across %s. Mapped into layered architecture from static analysis.", project.Name, len(files), topLangs),
		Layers:      layers,
		Components:  components,
		Flows:       flows,
		Entrypoints: entrypoints,
		DataStores:  stores,
	}
}

func Retrieve(ctx context.Context, st *store.Store, llmClient *llm.Client, projectID, query string, limit int) ([]store.Chunk, error) {
	vecs, err := llmClient.Embed(ctx, []string{query})
	if err != nil || len(vecs) == 0 {
		return nil, err
	}
	q := vecs[0]
	chunks, err := st.ListChunksWithEmbeddings(projectID)
	if err != nil {
		return nil, err
	}
	type scored struct {
		c store.Chunk
		s float64
	}
	var list []scored
	for _, c := range chunks {
		list = append(list, scored{c: c, s: llm.Cosine(q, c.Embedding)})
	}
	sort.Slice(list, func(i, j int) bool { return list[i].s > list[j].s })
	if limit > len(list) {
		limit = len(list)
	}
	out := make([]store.Chunk, 0, limit)
	for i := 0; i < limit; i++ {
		out = append(out, list[i].c)
	}
	return out, nil
}

var jsonBlock = regexp.MustCompile(`(?s)\{.*\}`)

func extractJSON(text string) (map[string]any, error) {
	text = strings.TrimSpace(text)
	text = strings.TrimPrefix(text, "```json")
	text = strings.TrimPrefix(text, "```")
	text = strings.TrimSuffix(text, "```")
	text = strings.TrimSpace(text)
	var m map[string]any
	if err := json.Unmarshal([]byte(text), &m); err == nil {
		return m, nil
	}
	loc := jsonBlock.FindString(text)
	if loc == "" {
		return nil, fmt.Errorf("no json")
	}
	if err := json.Unmarshal([]byte(loc), &m); err != nil {
		return nil, err
	}
	return m, nil
}

func Generate(ctx context.Context, st *store.Store, llmClient *llm.Client, projectID string) (*Data, error) {
	project, err := st.GetProject(projectID)
	if err != nil {
		return nil, err
	}
	files, err := st.ListFiles(projectID)
	if err != nil {
		return nil, err
	}
	symbols, _ := st.ListSymbols(projectID, 500)
	_, edges, _ := st.ListGraph(projectID)
	base := Heuristic(project, files, symbols, edges)

	retrieved, _ := Retrieve(ctx, st, llmClient, projectID, "system architecture data flow API client database workers services layers", 12)
	if llmClient.Configured() && len(retrieved) > 0 {
		var b strings.Builder
		for i, r := range retrieved {
			if i >= 10 {
				break
			}
			content := r.Content
			if len(content) > 1200 {
				content = content[:1200]
			}
			fmt.Fprintf(&b, "FILE: %s (%s)\n%s\n\n", r.FilePath, r.SymbolName, content)
		}
		baseJSON, _ := json.Marshal(base)
		if len(baseJSON) > 8000 {
			baseJSON = baseJSON[:8000]
		}
		prompt := fmt.Sprintf(`You are an expert software architect. Refine the architecture JSON for visualization. Keep component ids stable when possible.
Return ONLY valid JSON with keys: project_name, summary, layers, components, flows, entrypoints, data_stores.

PROJECT: %s

HEURISTIC DRAFT:
%s

RETRIEVED CODE:
%s`, project.Name, string(baseJSON), b.String())
		raw, err := llmClient.ChatJSON(ctx, "You output only valid JSON.", prompt)
		if err == nil && raw != "" {
			if m, err := extractJSON(raw); err == nil {
				refinedBytes, _ := json.Marshal(m)
				var refined Data
				if json.Unmarshal(refinedBytes, &refined) == nil && len(refined.Components) > 0 && len(refined.Layers) > 0 {
					if refined.ProjectName == "" {
						refined.ProjectName = project.Name
					}
					if len(refined.Flows) == 0 {
						refined.Flows = base.Flows
					}
					return &refined, nil
				}
			}
		}
	}
	return &base, nil
}
