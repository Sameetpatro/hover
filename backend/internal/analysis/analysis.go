package analysis

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var extLang = map[string]string{
	".py": "python", ".js": "javascript", ".jsx": "javascript",
	".ts": "typescript", ".tsx": "typescript", ".java": "java",
	".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
	".cs": "csharp", ".cpp": "cpp", ".cc": "cpp", ".c": "c",
	".sql": "sql", ".html": "html", ".css": "css", ".json": "json",
	".yml": "yaml", ".yaml": "yaml", ".md": "markdown", ".sh": "shell",
}

type Symbol struct {
	Name      string `json:"name"`
	Kind      string `json:"kind"`
	StartLine int    `json:"start_line"`
	EndLine   int    `json:"end_line"`
	Signature string `json:"signature"`
}

type AnalyzedFile struct {
	Path     string
	Language string
	Role     string
	LOC      int
	Imports  []string
	Symbols  []Symbol
}

var (
	pyImportRe = regexp.MustCompile(`(?m)^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))`)
	jsImportRe = regexp.MustCompile(`(?:import\s+(?:[^'"]+\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))`)
	pyDefRe    = regexp.MustCompile(`(?m)^\s*(?:async\s+)?def\s+(\w+)\s*\((.*?)\)\s*:`)
	pyClassRe  = regexp.MustCompile(`(?m)^\s*class\s+(\w+)\s*(?:\(|:)`)
	jsFuncRe   = regexp.MustCompile(`(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|(?:export\s+)?class\s+(\w+)`)
	djangoURL  = regexp.MustCompile(`path\(\s*['"]([^'"]+)['"]`)
	flaskRoute = regexp.MustCompile(`@(?:\w+\.)?route\(\s*['"]([^'"]+)['"]`)
)

func DetectLanguage(path, content string) string {
	base := strings.ToLower(filepath.Base(path))
	if base == "dockerfile" || strings.HasPrefix(base, "dockerfile") {
		return "dockerfile"
	}
	ext := strings.ToLower(filepath.Ext(path))
	if lang, ok := extLang[ext]; ok {
		return lang
	}
	if strings.HasPrefix(strings.TrimSpace(content), "#!") {
		line := strings.SplitN(content, "\n", 2)[0]
		low := strings.ToLower(line)
		if strings.Contains(low, "python") {
			return "python"
		}
		if strings.Contains(low, "node") || strings.Contains(low, "bash") {
			return "shell"
		}
	}
	return "unknown"
}

func InferRole(path, language string) string {
	lower := strings.ToLower(strings.ReplaceAll(path, "\\", "/"))
	name := filepath.Base(lower)
	switch {
	case strings.Contains(lower, "migration"), strings.Contains(lower, "models.py"),
		strings.Contains(lower, "/db/"), strings.Contains(lower, "repository"), strings.Contains(lower, "prisma"):
		return "db"
	case strings.Contains(lower, "controller"), strings.Contains(lower, "views.py"),
		strings.Contains(lower, "urls.py"), strings.Contains(lower, "routes"),
		strings.Contains(lower, "api/"), strings.Contains(lower, "handlers"):
		return "api"
	case strings.Contains(lower, "component"), strings.Contains(lower, "pages/"),
		strings.Contains(lower, "frontend"), strings.Contains(lower, "ui/"),
		strings.HasSuffix(lower, ".tsx"), strings.HasSuffix(lower, ".jsx"):
		return "ui"
	case strings.Contains(lower, "worker"), strings.Contains(lower, "celery"),
		strings.Contains(lower, "task"), strings.Contains(lower, "queue"), strings.Contains(lower, "consumer"):
		return "worker"
	case strings.Contains(lower, "config"), strings.Contains(lower, "settings"),
		strings.Contains(lower, "docker"), strings.Contains(lower, "package.json"),
		strings.Contains(lower, "requirements"):
		return "config"
	case language == "html", language == "css", language == "scss":
		return "ui"
	case name == "main.py", name == "app.py", name == "index.ts", name == "index.js",
		name == "manage.py", name == "server.js", name == "main.go":
		return "entry"
	default:
		return "logic"
	}
}

func lineAt(content string, idx int) int {
	return strings.Count(content[:idx], "\n") + 1
}

func AnalyzeFile(path, abs string) AnalyzedFile {
	b, _ := os.ReadFile(abs)
	content := string(b)
	lang := DetectLanguage(path, content)
	af := AnalyzedFile{
		Path:     path,
		Language: lang,
		Role:     InferRole(path, lang),
		LOC:      strings.Count(content, "\n"),
	}
	if content != "" {
		af.LOC++
	}
	switch lang {
	case "python":
		for _, m := range pyImportRe.FindAllStringSubmatch(content, -1) {
			imp := m[1]
			if imp == "" {
				imp = m[2]
			}
			if imp != "" {
				af.Imports = append(af.Imports, imp)
			}
		}
		for _, m := range pyClassRe.FindAllStringSubmatchIndex(content, -1) {
			name := content[m[2]:m[3]]
			line := lineAt(content, m[0])
			af.Symbols = append(af.Symbols, Symbol{Name: name, Kind: "class", StartLine: line, EndLine: line, Signature: "class " + name})
		}
		for _, m := range pyDefRe.FindAllStringSubmatchIndex(content, -1) {
			name := content[m[2]:m[3]]
			args := content[m[4]:m[5]]
			line := lineAt(content, m[0])
			kind := "function"
			af.Symbols = append(af.Symbols, Symbol{Name: name, Kind: kind, StartLine: line, EndLine: line, Signature: "def " + name + "(" + args + ")"})
		}
		for _, m := range djangoURL.FindAllStringSubmatchIndex(content, -1) {
			name := content[m[2]:m[3]]
			line := lineAt(content, m[0])
			af.Symbols = append(af.Symbols, Symbol{Name: name, Kind: "endpoint", StartLine: line, EndLine: line, Signature: "path('" + name + "')"})
		}
		for _, m := range flaskRoute.FindAllStringSubmatchIndex(content, -1) {
			name := content[m[2]:m[3]]
			line := lineAt(content, m[0])
			af.Symbols = append(af.Symbols, Symbol{Name: name, Kind: "endpoint", StartLine: line, EndLine: line, Signature: "route('" + name + "')"})
		}
	case "javascript", "typescript":
		for _, m := range jsImportRe.FindAllStringSubmatch(content, -1) {
			imp := m[1]
			if imp == "" {
				imp = m[2]
			}
			if imp != "" {
				af.Imports = append(af.Imports, imp)
			}
		}
		for _, m := range jsFuncRe.FindAllStringSubmatchIndex(content, -1) {
			var name string
			for i := 1; i <= 3; i++ {
				if m[2*i] >= 0 {
					name = content[m[2*i]:m[2*i+1]]
					break
				}
			}
			if name == "" {
				continue
			}
			line := lineAt(content, m[0])
			kind := "function"
			if m[6] >= 0 {
				kind = "class"
			}
			af.Symbols = append(af.Symbols, Symbol{Name: name, Kind: kind, StartLine: line, EndLine: line, Signature: name})
		}
	}
	return af
}

func resolveImport(importName, fromPath string, all map[string]struct{}) string {
	if importName == "" {
		return ""
	}
	if strings.HasPrefix(importName, ".") {
		base := filepath.Dir(fromPath)
		rel := importName
		for strings.HasPrefix(rel, "..") {
			base = filepath.Dir(base)
			if strings.HasPrefix(rel, "../") {
				rel = rel[3:]
			} else {
				rel = rel[2:]
			}
		}
		rel = strings.TrimPrefix(rel, "./")
		cands := []string{
			filepath.ToSlash(filepath.Join(base, rel+".py")),
			filepath.ToSlash(filepath.Join(base, rel, "__init__.py")),
			filepath.ToSlash(filepath.Join(base, rel+".ts")),
			filepath.ToSlash(filepath.Join(base, rel+".tsx")),
			filepath.ToSlash(filepath.Join(base, rel+".js")),
			filepath.ToSlash(filepath.Join(base, rel, "index.ts")),
			filepath.ToSlash(filepath.Join(base, rel, "index.js")),
		}
		for _, c := range cands {
			if _, ok := all[c]; ok {
				return c
			}
		}
		return ""
	}
	dotted := strings.ReplaceAll(importName, ".", "/")
	cands := []string{dotted + ".py", dotted + "/__init__.py", dotted + ".ts", dotted + ".js", "src/" + dotted + ".ts"}
	for _, c := range cands {
		if _, ok := all[c]; ok {
			return c
		}
	}
	for p := range all {
		if strings.HasSuffix(p, "/"+dotted+".py") || strings.HasSuffix(p, "/"+dotted+".ts") {
			return p
		}
	}
	return ""
}

func BuildGraph(analyzed []AnalyzedFile) (nodes []map[string]any, edges []map[string]any) {
	all := map[string]struct{}{}
	for _, a := range analyzed {
		all[a.Path] = struct{}{}
	}
	for _, a := range analyzed {
		nodes = append(nodes, map[string]any{
			"key": a.Path, "label": filepath.Base(a.Path), "kind": a.Role,
			"metadata": map[string]any{"language": a.Language, "role": a.Role, "loc": a.LOC},
		})
	}
	seen := map[string]struct{}{}
	for _, a := range analyzed {
		for _, imp := range a.Imports {
			target := resolveImport(imp, a.Path, all)
			if target == "" || target == a.Path {
				continue
			}
			k := a.Path + "->" + target
			if _, ok := seen[k]; ok {
				continue
			}
			seen[k] = struct{}{}
			edges = append(edges, map[string]any{
				"source": a.Path, "target": target, "edge_type": "import",
				"metadata": map[string]any{"import": imp},
			})
		}
	}
	return nodes, edges
}

func ChunkFile(a AnalyzedFile, abs string, maxChars int) []map[string]any {
	b, err := os.ReadFile(abs)
	if err != nil {
		return nil
	}
	lines := strings.Split(string(b), "\n")
	var chunks []map[string]any
	for _, sym := range a.Symbols {
		start := sym.StartLine - 1
		if start < 0 {
			start = 0
		}
		end := start + 40
		if end > len(lines) {
			end = len(lines)
		}
		body := strings.Join(lines[start:end], "\n")
		if len(body) > maxChars {
			body = body[:maxChars]
		}
		if strings.TrimSpace(body) == "" {
			continue
		}
		chunks = append(chunks, map[string]any{
			"symbol_name": sym.Name, "language": a.Language,
			"start_line": start + 1, "end_line": end, "content": body,
			"metadata": map[string]any{"kind": sym.Kind, "role": a.Role},
		})
	}
	end := 80
	if end > len(lines) {
		end = len(lines)
	}
	overview := strings.Join(lines[:end], "\n")
	if len(overview) > maxChars {
		overview = overview[:maxChars]
	}
	if strings.TrimSpace(overview) != "" {
		chunks = append(chunks, map[string]any{
			"symbol_name": filepath.Base(a.Path), "language": a.Language,
			"start_line": 1, "end_line": end, "content": overview,
			"metadata": map[string]any{"kind": "file", "role": a.Role},
		})
	}
	return chunks
}
