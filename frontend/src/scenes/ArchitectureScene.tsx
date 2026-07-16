import { useMemo, useRef, useState, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import {
  Billboard,
  Float,
  Line,
  OrbitControls,
  PerspectiveCamera,
  Text,
  Stars,
} from "@react-three/drei";
import * as THREE from "three";
import gsap from "gsap";
import type { ArchitectureData } from "../api";
import {
  colorForKind,
  mapArchitecture,
  type LayoutEdge,
  type LayoutNode,
} from "../lib/architectureMapper";

function geometryForKind(kind: string) {
  switch (kind) {
    case "ui":
    case "entry":
      return <boxGeometry args={[1.2, 0.7, 0.35]} />;
    case "controller":
      return <octahedronGeometry args={[0.7, 0]} />;
    case "worker":
      return <dodecahedronGeometry args={[0.65, 0]} />;
    case "model":
      return <cylinderGeometry args={[0.55, 0.55, 0.7, 16]} />;
    default:
      return <icosahedronGeometry args={[0.65, 0]} />;
  }
}

function NodeMesh({
  node,
  highlighted,
  assemble,
}: {
  node: LayoutNode;
  highlighted: boolean;
  assemble: number;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const color = colorForKind(node.kind);
  const scatter = useMemo(() => {
    const r = 18 + Math.random() * 10;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    return new THREE.Vector3(
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.sin(phi) * Math.sin(theta),
      r * Math.cos(phi),
    );
  }, []);

  useFrame(() => {
    if (!ref.current) return;
    const target = new THREE.Vector3(...node.position);
    const pos = scatter.clone().lerp(target, assemble);
    ref.current.position.copy(pos);
    ref.current.rotation.y += highlighted ? 0.04 : 0.008;
    const s = highlighted ? 1.25 : 1;
    ref.current.scale.lerp(new THREE.Vector3(s, s, s), 0.1);
  });

  return (
    <Float speed={1.2} rotationIntensity={0.2} floatIntensity={0.35}>
      <mesh ref={ref}>
        {geometryForKind(node.kind)}
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={highlighted ? 1.4 : 0.45}
          metalness={0.55}
          roughness={0.25}
        />
      </mesh>
      <Billboard position={[node.position[0], node.position[1] + 1.1, node.position[2]]}>
        <Text fontSize={0.28} color="#f8fafc" anchorX="center" anchorY="middle" maxWidth={3}>
          {node.name}
        </Text>
      </Billboard>
    </Float>
  );
}

function Packet({
  from,
  to,
  active,
  delay,
}: {
  from: THREE.Vector3;
  to: THREE.Vector3;
  active: boolean;
  delay: number;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const t = useRef(0);

  useFrame((_, delta) => {
    if (!ref.current || !active) return;
    t.current = (t.current + delta * 0.55) % 1;
    const p = from.clone().lerp(to, t.current);
    // slight arc
    p.y += Math.sin(t.current * Math.PI) * 1.2;
    ref.current.position.copy(p);
  });

  useEffect(() => {
    t.current = delay;
  }, [delay, active]);

  if (!active) return null;
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshStandardMaterial color="#fef08a" emissive="#facc15" emissiveIntensity={2} />
    </mesh>
  );
}

function FlowBeams({
  nodes,
  edges,
  activeFlowId,
  assemble,
}: {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
  activeFlowId: string | null;
  assemble: number;
}) {
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  if (assemble < 0.95) return null;

  return (
    <>
      {edges.map((e) => {
        const a = byId.get(e.from);
        const b = byId.get(e.to);
        if (!a || !b) return null;
        const active = !activeFlowId || activeFlowId === e.flowId;
        const from = new THREE.Vector3(...a.position);
        const to = new THREE.Vector3(...b.position);
        const mid = from.clone().lerp(to, 0.5);
        mid.y += 1.1;
        return (
          <group key={e.id}>
            <Line
              points={[from, mid, to]}
              color={active ? "#fde68a" : "#334155"}
              lineWidth={active ? 2.5 : 1}
              transparent
              opacity={active ? 0.95 : 0.25}
            />
            <Packet from={from} to={to} active={active} delay={Math.random()} />
            <Packet from={from} to={to} active={active} delay={Math.random() * 0.5} />
          </group>
        );
      })}
    </>
  );
}

function LayerPlanes({ layers }: { layers: ArchitectureData["layers"] }) {
  const zMap: Record<string, number> = {
    client: 6,
    api: 2,
    services: -2,
    data: -6,
  };
  return (
    <>
      {layers.map((l) => (
        <group key={l.id} position={[0, -1.6, zMap[l.id] ?? 0]}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[16, 3.2]} />
            <meshStandardMaterial
              color="#0f172a"
              transparent
              opacity={0.45}
              side={THREE.DoubleSide}
            />
          </mesh>
          <Text
            position={[-7.2, 0.2, 0]}
            fontSize={0.35}
            color="#94a3b8"
            anchorX="left"
          >
            {l.label.toUpperCase()}
          </Text>
        </group>
      ))}
    </>
  );
}

function SceneContent({
  data,
  activeFlowId,
}: {
  data: ArchitectureData;
  activeFlowId: string | null;
}) {
  const { nodes, edges } = useMemo(() => mapArchitecture(data), [data]);
  const [assemble, setAssemble] = useState(0);
  const highlighted = useMemo(() => {
    if (!activeFlowId) return new Set(nodes.map((n) => n.id));
    const ids = new Set<string>();
    for (const e of edges) {
      if (e.flowId === activeFlowId) {
        ids.add(e.from);
        ids.add(e.to);
      }
    }
    return ids;
  }, [activeFlowId, edges, nodes]);

  useEffect(() => {
    const state = { t: 0 };
    const tween = gsap.to(state, {
      t: 1,
      duration: 2.8,
      ease: "power3.inOut",
      onUpdate: () => setAssemble(state.t),
    });
    return () => {
      tween.kill();
    };
  }, [data]);

  return (
    <>
      <color attach="background" args={["#020617"]} />
      <fog attach="fog" args={["#020617", 18, 42]} />
      <ambientLight intensity={0.45} />
      <directionalLight position={[8, 12, 6]} intensity={1.3} color="#e2e8f0" />
      <pointLight position={[-6, 4, -4]} intensity={1.2} color="#22d3ee" />
      <pointLight position={[6, 2, 8]} intensity={0.9} color="#f59e0b" />
      <Stars radius={80} depth={40} count={2500} factor={3} saturation={0} fade speed={0.6} />
      <LayerPlanes layers={data.layers} />
      {nodes.map((n) => (
        <NodeMesh
          key={n.id}
          node={n}
          highlighted={highlighted.has(n.id)}
          assemble={assemble}
        />
      ))}
      <FlowBeams
        nodes={nodes}
        edges={edges}
        activeFlowId={activeFlowId}
        assemble={assemble}
      />
      <OrbitControls
        enablePan
        maxDistance={28}
        minDistance={6}
        autoRotate={assemble >= 1}
        autoRotateSpeed={0.4}
      />
    </>
  );
}

export function ArchitectureScene({
  data,
  activeFlowId,
}: {
  data: ArchitectureData;
  activeFlowId: string | null;
}) {
  return (
    <Canvas dpr={[1, 2]}>
      <PerspectiveCamera makeDefault position={[10, 7, 14]} fov={45} />
      <SceneContent data={data} activeFlowId={activeFlowId} />
    </Canvas>
  );
}
