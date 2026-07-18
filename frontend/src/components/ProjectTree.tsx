import { useMemo, useState } from "react";
import type { ProjectFileRow } from "../api";

type TreeNode = {
  name: string;
  path: string;
  children: Map<string, TreeNode>;
  file?: ProjectFileRow;
};

function buildTree(files: ProjectFileRow[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: new Map() };
  for (const f of files) {
    const parts = f.path.split("/").filter(Boolean);
    let cur = root;
    let acc = "";
    parts.forEach((part, i) => {
      acc = acc ? `${acc}/${part}` : part;
      if (!cur.children.has(part)) {
        cur.children.set(part, { name: part, path: acc, children: new Map() });
      }
      cur = cur.children.get(part)!;
      if (i === parts.length - 1) cur.file = f;
    });
  }
  return root;
}

function Branch({
  node,
  depth,
}: {
  node: TreeNode;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 2);
  const kids = [...node.children.values()].sort((a, b) => {
    const aDir = a.children.size > 0 && !a.file;
    const bDir = b.children.size > 0 && !b.file;
    if (aDir !== bDir) return aDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const isDir = kids.length > 0;

  if (!node.name && depth === 0) {
    return (
      <ul className="tree-list">
        {kids.map((k) => (
          <Branch key={k.path} node={k} depth={0} />
        ))}
      </ul>
    );
  }

  return (
    <li className="tree-item">
      <button
        type="button"
        className={`tree-row ${node.file ? "file" : "dir"}`}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
        onClick={() => isDir && setOpen((v) => !v)}
      >
        <span className="tree-icon">{isDir ? (open ? "▾" : "▸") : "·"}</span>
        <span className="tree-name">{node.name}</span>
        {node.file && (
          <span className="tree-meta">
            {node.file.language || "?"} · {node.file.role || "file"} · {node.file.loc} loc
          </span>
        )}
      </button>
      {isDir && open && (
        <ul className="tree-list">
          {kids.map((k) => (
            <Branch key={k.path} node={k} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ProjectTree({ files }: { files: ProjectFileRow[] }) {
  const tree = useMemo(() => buildTree(files), [files]);
  if (!files.length) {
    return <p className="panel-empty">No files indexed yet.</p>;
  }
  return (
    <div className="tree-wrap">
      <p className="panel-hint">{files.length} files in this project</p>
      <Branch node={tree} depth={0} />
    </div>
  );
}
