import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Pause, Play } from "lucide-react";

const FILL: Record<string, number> = { URGENT: 0xb54747, REVIEW: 0xe39a5b, MONITOR: 0xf3d68b, OK: 0xbdefe0, NONE: 0xdfe5ee };

/** Optional 3D body twin (three.js). Drag to rotate, click a region to select it. 2D view remains the accessible default. */
export default function Body3D({ selected, onSelect, statusOf }: {
  selected: string; onSelect: (id: string) => void; statusOf: (id: string) => string;
}) {
  const mount = useRef<HTMLDivElement>(null);
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [spinning, setSpinning] = useState(!reduced);
  const spinRef = useRef(spinning);
  spinRef.current = spinning;
  const meshes = useRef<THREE.Mesh[]>([]);

  useEffect(() => {
    const el = mount.current!;
    const w = el.clientWidth, h = 440;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, h);
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 100);
    camera.position.set(0, 0.2, 7.5);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x334466, 1.4));
    const dir = new THREE.DirectionalLight(0xffffff, 1.2);
    dir.position.set(3, 5, 4);
    scene.add(dir);
    const body = new THREE.Group();
    scene.add(body);
    const shell = new THREE.MeshStandardMaterial({ color: 0xf4efe6, transparent: true, opacity: 0.35, roughness: 0.8 });

    const add = (geo: THREE.BufferGeometry, pos: [number, number, number], region: string | null, rot: [number, number, number] = [0, 0, 0]) => {
      const mat = region ? new THREE.MeshStandardMaterial({ color: FILL.NONE, roughness: 0.5 }) : shell;
      const m = new THREE.Mesh(geo, mat);
      m.position.set(...pos); m.rotation.set(...rot);
      m.userData.region = region;
      body.add(m);
      if (region) meshes.current.push(m);
      return m;
    };
    // silhouette
    add(new THREE.SphereGeometry(0.55, 32, 24), [0, 2.05, 0], null);
    add(new THREE.CapsuleGeometry(0.75, 1.4, 8, 24), [0, 0.45, 0], null);
    // regions
    add(new THREE.SphereGeometry(0.38, 28, 20), [0, 2.2, 0], "brain");
    add(new THREE.SphereGeometry(0.07, 12, 10), [-0.18, 2.0, 0.5], "eyes");
    add(new THREE.SphereGeometry(0.07, 12, 10), [0.18, 2.0, 0.5], "eyes");
    add(new THREE.CapsuleGeometry(0.2, 0.45, 6, 16), [-0.32, 0.95, 0.15], "lungs");
    add(new THREE.CapsuleGeometry(0.2, 0.45, 6, 16), [0.32, 0.95, 0.15], "lungs");
    add(new THREE.SphereGeometry(0.2, 24, 18), [0.05, 0.85, 0.45], "heart");
    add(new THREE.SphereGeometry(0.36, 24, 18), [0, 0.0, 0.25], "digestive");
    for (const x of [-0.32, 0.32]) add(new THREE.CapsuleGeometry(0.17, 1.6, 6, 16), [x, -1.45, 0], "msk");
    for (const x of [-1.0, 1.0]) add(new THREE.CapsuleGeometry(0.13, 1.25, 6, 16), [x, 0.55, 0], "msk", [0, 0, x > 0 ? 0.18 : -0.18]);

    // interaction: drag to rotate, click to select
    let dragging = false, moved = 0, lastX = 0;
    const ray = new THREE.Raycaster();
    const ptr = new THREE.Vector2();
    const down = (e: PointerEvent) => { dragging = true; moved = 0; lastX = e.clientX; };
    const move = (e: PointerEvent) => { if (!dragging) return; body.rotation.y += (e.clientX - lastX) * 0.01; moved += Math.abs(e.clientX - lastX); lastX = e.clientX; };
    const up = (e: PointerEvent) => {
      dragging = false;
      if (moved > 4) return;
      const r = renderer.domElement.getBoundingClientRect();
      ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ptr, camera);
      const hit = ray.intersectObjects(meshes.current)[0];
      if (hit) onSelectRef.current(hit.object.userData.region);
    };
    renderer.domElement.addEventListener("pointerdown", down);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    let frame = 0;
    const loop = () => {
      if (spinRef.current && !dragging) body.rotation.y += 0.004;
      renderer.render(scene, camera);
      frame = requestAnimationFrame(loop);
    };
    loop();
    return () => {
      cancelAnimationFrame(frame);
      renderer.domElement.removeEventListener("pointerdown", down);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      renderer.dispose();
      meshes.current = [];
      el.removeChild(renderer.domElement);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // colour by status and highlight the selection
  useEffect(() => {
    for (const m of meshes.current) {
      const mat = m.material as THREE.MeshStandardMaterial;
      const region = m.userData.region as string;
      mat.color.setHex(FILL[statusOf(region)] ?? FILL.NONE);
      const on = region === selected;
      mat.emissive.setHex(on ? 0x20b8ad : 0x000000);
      mat.emissiveIntensity = on ? 0.6 : 0;
      mat.transparent = true;
      mat.opacity = on ? 1 : 0.7;
      m.scale.setScalar(on ? 1.12 : 1);
    }
  });

  return (
    <div>
      <div ref={mount} className="h-[440px] w-full cursor-grab rounded-2xl bg-gradient-to-b from-ivory to-mint-soft"
        role="img" aria-label="3D body model. Use the list of body systems for keyboard access." />
      <div className="mt-2 flex justify-center">
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => setSpinning(!spinning)} aria-pressed={!spinning}>
          {spinning ? <><Pause size={12} aria-hidden /> Pause rotation</> : <><Play size={12} aria-hidden /> Rotate</>}
        </button>
      </div>
    </div>
  );
}
