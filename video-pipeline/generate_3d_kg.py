#!/usr/bin/env python3
"""
generate_3d_kg.py — True 3D Knowledge Graph Generator

Generates a self-contained HTML file using Three.js ES modules from CDN.
Renders a fully 3D force-directed knowledge graph with:
  - Force-directed layout in all 3 axes (x, y, z)
  - PerspectiveCamera with OrbitControls
  - Nodes as spheres/cubes, colored by category
  - Edges as lines or cylinders
  - CSS2DRenderer labels above nodes
  - Hover highlighting
  - Auto-rotation toggle
  - Adjustable layout parameters (spring, repulsion, gravity, damping)
  - Z-axis binding to extra dimensions (time, weight, or none)

Usage:
  python generate_3d_kg.py --input graph.json --output my-graph.html [--z-dimension weight|time|none]
  python generate_3d_kg.py                          # generates a demo graph
"""

import json, math, random, argparse, os, sys
from datetime import datetime, timezone

# ──────────────────────────────────────────────
# Template HTML
# ──────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>3D Knowledge Graph</title>
<style>
  body {{ margin: 0; overflow: hidden; font-family: 'Segoe UI', Arial, sans-serif; background: #0a0a1a; }}
  #info {{
    position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
    color: rgba(255,255,255,0.6); font-size: 13px;
    pointer-events: none; z-index: 10;
    background: rgba(10,10,30,0.7); padding: 6px 18px; border-radius: 20px;
    backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.08);
  }}
  #controls {{
    position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
    z-index: 10; display: flex; gap: 10px; align-items: center;
    background: rgba(10,10,30,0.75); padding: 10px 20px; border-radius: 12px;
    backdrop-filter: blur(6px); border: 1px solid rgba(255,255,255,0.08);
  }}
  #controls label {{ color: #aaa; font-size: 12px; cursor: pointer; user-select: none; }}
  #controls input[type="checkbox"] {{ cursor: pointer; }}
  #stats {{
    position: absolute; bottom: 80px; left: 50%; transform: translateX(-50%);
    color: rgba(255,255,255,0.35); font-size: 11px; z-index: 10;
    pointer-events: none; text-align: center;
  }}
  .legend {{
    position: absolute; top: 60px; right: 16px; z-index: 10;
    background: rgba(10,10,30,0.75); padding: 10px 14px; border-radius: 10px;
    backdrop-filter: blur(6px); border: 1px solid rgba(255,255,255,0.08);
    font-size: 12px; color: #ccc;
  }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
  .legend-color {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
  .label {{
    color: #fff; font-size: 14px; font-weight: 600;
    text-shadow: 0 0 8px rgba(0,0,0,1), 0 0 16px rgba(0,0,0,0.8);
    pointer-events: none; white-space: nowrap;
    padding: 4px 10px; border-radius: 6px;
    background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
    border: 1px solid rgba(255,255,255,0.15);
  }}
  .label-highlight {{ color: #ff0; background: rgba(0,0,0,0.8); font-size: 16px; }}
</style>
</head>
<body>
<div id="info">3D Knowledge Graph — drag to orbit · scroll to zoom · hover to highlight</div>
<div class="legend" id="legend"></div>
<div id="stats"></div>
<div id="controls">
  <label><input type="checkbox" id="chkRotate" checked> Auto-rotate</label>
  <label style="margin-left:10px;color:#888;font-size:11px;">
    Nodes: {node_count} &middot; Edges: {edge_count}
  </label>
</div>

<script type="importmap">
{{
  "imports": {{
    "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
  }}
}}
</script>

<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';
import {{ CSS2DRenderer, CSS2DObject }} from 'three/addons/renderers/CSS2DRenderer.js';

let CSS2D_AVAILABLE = true;
// Fallback when CDN doesn't serve CSS2DRenderer
if (typeof CSS2DRenderer === 'undefined') {{
    CSS2D_AVAILABLE = false;
    console.warn('CSS2DRenderer not available, using canvas text labels');
}}

// ── Graph Data ────────────────────────────────
const NODES = {nodes_json};
const EDGES = {edges_json};
const CATEGORIES = {categories_json};
const CAT_COLORS = {cat_colors_json};
const Z_DIMENSION = '{z_dimension}';

// ── Layout Params ─────────────────────────────
const SPRING_K        = {spring_k};
const REPULSION_K     = {repulsion_k};
const GRAVITY_K       = {gravity_k};
const DAMPING         = {damping};
const CENTER_GRAVITY  = {center_gravity};

// ── Scene Setup ───────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a1a);

const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.set(20, 15, 25);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = false;
document.body.appendChild(renderer.domElement);

const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(window.innerWidth, window.innerHeight);
labelRenderer.domElement.style.position = 'absolute';
labelRenderer.domElement.style.top = '0px';
labelRenderer.domElement.style.left = '0px';
labelRenderer.domElement.style.pointerEvents = 'none';
document.body.appendChild(labelRenderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.autoRotate = true;
controls.autoRotateSpeed = 1.8;
controls.minDistance = 5;
controls.maxDistance = 80;

// ── Lights ────────────────────────────────────
const ambient = new THREE.AmbientLight(0x404060, 0.6);
scene.add(ambient);

const dirLight = new THREE.DirectionalLight(0xffffff, 1.8);
dirLight.position.set(10, 20, 10);
scene.add(dirLight);

const fillLight = new THREE.DirectionalLight(0x8888ff, 0.5);
fillLight.position.set(-10, 0, -10);
scene.add(fillLight);

const backLight = new THREE.DirectionalLight(0x4488ff, 0.3);
backLight.position.set(-5, -5, -15);
scene.add(backLight);

// ── Stars background ──────────────────────────
const starsGeo = new THREE.BufferGeometry();
const starCount = 2000;
const starPos = new Float32Array(starCount * 3);
for (let i = 0; i < starCount * 3; i++) {{
    starPos[i] = (Math.random() - 0.5) * 400;
}}
starsGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
const starsMat = new THREE.PointsMaterial({{ color: 0xffffff, size: 0.25, transparent: true, opacity: 0.6 }});
const stars = new THREE.Points(starsGeo, starsMat);
scene.add(stars);

// ── Build Nodes ───────────────────────────────
const nodeObjects = new Map();
const nodeMeshes = new Map();
const nodeLabels = new Map();

NODES.forEach((n, idx) => {{
    const color = new THREE.Color(CAT_COLORS[n.category] || '#888888');
    const size = n.size || 0.6;

    let geom, mesh;
    if (n.shape === 'cube') {{
        geom = new THREE.BoxGeometry(size, size, size);
    }} else {{
        geom = new THREE.SphereGeometry(size * 0.5, 24, 24);
    }}

    const mat = new THREE.MeshStandardMaterial({{
        color: color,
        roughness: 0.3,
        metalness: 0.1,
        emissive: color.clone().multiplyScalar(0.08),
        emissiveIntensity: 0.3,
    }});
    mesh = new THREE.Mesh(geom, mat);
    mesh.position.set(n.x, n.y, n.z);
    mesh.userData.idx = idx;
    mesh.userData.nodeId = n.id;
    mesh.userData.origColor = color;
    mesh.userData.highlighted = false;
    scene.add(mesh);

    // Glow ring underneath
    const ringGeo = new THREE.RingGeometry(size * 0.35, size * 0.55, 32);
    const ringMat = new THREE.MeshBasicMaterial({{
        color: color,
        transparent: true,
        opacity: 0.15,
        side: THREE.DoubleSide,
        depthWrite: false,
    }});
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.position.set(n.x, n.y - size * 0.2, n.z);
    ring.lookAt(camera.position);
    mesh.add(ring);

    // Label — Canvas Sprite (works without CSS2DRenderer)
    const labelCanvas = document.createElement('canvas');
    labelCanvas.width = 512;
    labelCanvas.height = 128;
    const lctx = labelCanvas.getContext('2d');
    // Dark rounded background
    lctx.fillStyle = 'rgba(0,0,0,0.7)';
    lctx.shadowColor = 'rgba(0,0,0,0.9)';
    lctx.shadowBlur = 10;
    const r = 12;
    const w = 512, h = 128;
    lctx.beginPath();
    lctx.moveTo(r, 0); lctx.lineTo(w - r, 0); lctx.quadraticCurveTo(w, 0, w, r);
    lctx.lineTo(w, h - r); lctx.quadraticCurveTo(w, h, w - r, h);
    lctx.lineTo(r, h); lctx.quadraticCurveTo(0, h, 0, h - r);
    lctx.lineTo(0, r); lctx.quadraticCurveTo(0, 0, r, 0);
    lctx.closePath();
    lctx.fill();
    // White border
    lctx.strokeStyle = 'rgba(255,255,255,0.3)';
    lctx.lineWidth = 2;
    lctx.stroke();
    // Text
    lctx.shadowColor = 'rgba(0,0,0,0.9)';
    lctx.shadowBlur = 8;
    lctx.fillStyle = '#ffffff';
    lctx.font = 'bold 36px Arial, sans-serif';
    lctx.textAlign = 'center';
    lctx.textBaseline = 'middle';
    lctx.fillText(n.label || n.id, 256, 64);
    const labelTexture = new THREE.CanvasTexture(labelCanvas);
    labelTexture.needsUpdate = true;
    const labelMat = new THREE.SpriteMaterial({{
        map: labelTexture,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        sizeAttenuation: true,
    }});
    const labelSprite = new THREE.Sprite(labelMat);
    labelSprite.scale.set(size * 5, size * 1.2, 1);
    labelSprite.position.set(0, size * 1.2 + 1.2, 0);
    mesh.add(labelSprite);
    mesh.userData.origLabelScale = new THREE.Vector2(size * 5, size * 1.2);
    nodeLabels.set(n.id, labelSprite);

    // Glow sprite
    const spriteMap = (() => {{
        const canvas = document.createElement('canvas');
        canvas.width = 128;
        canvas.height = 128;
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
        gradient.addColorStop(0, `rgba(${{color.r*255|0}},${{color.g*255|0}},${{color.b*255|0}},0.3)`);
        gradient.addColorStop(0.4, `rgba(${{color.r*255|0}},${{color.g*255|0}},${{color.b*255|0}},0.08)`);
        gradient.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 128, 128);
        return new THREE.CanvasTexture(canvas);
    }})();
    const spriteMat = new THREE.SpriteMaterial({{ map: spriteMap, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }});
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(size * 4, size * 4, 1);
    sprite.position.set(0, 0, 0);
    mesh.add(sprite);

    nodeObjects.set(n.id, mesh);
    nodeMeshes.set(n.id, mesh);
    nodeLabels.set(n.id, label);
}});

// ── Build Edges ───────────────────────────────
const edgeGroup = new THREE.Group();
scene.add(edgeGroup);

EDGES.forEach(e => {{
    const src = nodeObjects.get(e.source);
    const tgt = nodeObjects.get(e.target);
    if (!src || !tgt) return;

    const p1 = src.position.clone();
    const p2 = tgt.position.clone();
    const mid = p1.clone().add(p2).multiplyScalar(0.5);
    const dir = p2.clone().sub(p1);
    const len = dir.length();
    if (len < 0.001) return;

    const color = new THREE.Color(e.color || '#446688');
    const weight = e.weight || 1;
    const radius = 0.015 + weight * 0.025;

    // Use cylinder for edges (thicker = higher weight)
    const cylGeo = new THREE.CylinderGeometry(radius, radius, len, 6, 1);
    const cylMat = new THREE.MeshStandardMaterial({{
        color: color,
        transparent: true,
        opacity: 0.5 + weight * 0.3,
        roughness: 0.5,
        metalness: 0.1,
    }});
    const cyl = new THREE.Mesh(cylGeo, cylMat);
    cyl.position.copy(mid);

    // Orient cylinder along dir
    const up = new THREE.Vector3(0, 1, 0);
    const quat = new THREE.Quaternion().setFromUnitVectors(up, dir.clone().normalize());
    cyl.quaternion.copy(quat);

    edgeGroup.add(cyl);

    // Glow line inside cylinder (thin line for visual direction)
    const lineMat = new THREE.LineBasicMaterial({{
        color: color,
        transparent: true,
        opacity: 0.15 + weight * 0.2,
    }});
    const lineGeo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
    const line = new THREE.Line(lineGeo, lineMat);
    edgeGroup.add(line);
}});

// ── Floor Grid ───────────────────────────────
const gridHelper = new THREE.GridHelper(40, 20, 0x334466, 0x223355);
gridHelper.position.y = -6;
scene.add(gridHelper);

// Subtle axis indicator
const axesHelper = new THREE.AxesHelper(3);
axesHelper.position.set(-12, -5.5, -12);
scene.add(axesHelper);

// ── Force Simulation ──────────────────────────
// We do a fixed number of iterations on load (no real-time tick)
function runForceLayout(iterations) {{
    const nodes = NODES;
    const edges = EDGES;

    for (let iter = 0; iter < iterations; iter++) {{
        // Forces
        const forces = nodes.map(() => new THREE.Vector3(0, 0, 0));

        // Spring force (edges pull nodes together)
        edges.forEach(e => {{
            const i = nodes.findIndex(n => n.id === e.source);
            const j = nodes.findIndex(n => n.id === e.target);
            if (i < 0 || j < 0) return;
            const dx = nodes[j].x - nodes[i].x;
            const dy = nodes[j].y - nodes[i].y;
            const dz = nodes[j].z - nodes[i].z;
            const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || 0.001;
            const force = SPRING_K * (dist - 3.0);
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            const fz = (dz / dist) * force;
            forces[i].x += fx; forces[i].y += fy; forces[i].z += fz;
            forces[j].x -= fx; forces[j].y -= fy; forces[j].z -= fz;
        }});

        // Repulsion (all node pairs)
        for (let i = 0; i < nodes.length; i++) {{
            for (let j = i+1; j < nodes.length; j++) {{
                const dx = nodes[j].x - nodes[i].x;
                const dy = nodes[j].y - nodes[i].y;
                const dz = nodes[j].z - nodes[i].z;
                const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || 0.001;
                const force = REPULSION_K / (dist * dist + 0.1);
                const fx = (dx / dist) * force;
                const fy = (dy / dist) * force;
                const fz = (dz / dist) * force;
                forces[i].x -= fx; forces[i].y -= fy; forces[i].z -= fz;
                forces[j].x += fx; forces[j].y += fy; forces[j].z += fz;
            }}
        }}

        // Center gravity
        nodes.forEach((n, i) => {{
            forces[i].x -= n.x * CENTER_GRAVITY;
            forces[i].y -= n.y * CENTER_GRAVITY;
            forces[i].z -= n.z * CENTER_GRAVITY;
        }});

        // Z-dimension specific gravity
        if (Z_DIMENSION === 'time') {{
            // Keep z values clustered near original timeline positions
            forces.forEach((f, i) => {{
                f.z -= (nodes[i].z - nodes[i]._z_orig) * 0.01;
            }});
        }}

        // Apply
        nodes.forEach((n, i) => {{
            n.vx = (n.vx || 0) + forces[i].x * DAMPING;
            n.vy = (n.vy || 0) + forces[i].y * DAMPING;
            n.vz = (n.vz || 0) + forces[i].z * DAMPING;
            n.vx *= (1 - DAMPING * 0.5);
            n.vy *= (1 - DAMPING * 0.5);
            n.vz *= (1 - DAMPING * 0.5);
            n.x += n.vx;
            n.y += n.vy;
            n.z += n.vz;
        }});
    }}

    // Update meshes
    nodes.forEach(n => {{
        const mesh = nodeObjects.get(n.id);
        if (mesh) {{
            mesh.position.set(n.x, n.y, n.z);
        }}
    }});
    rebuildEdges();
}}

function rebuildEdges() {{
    // Remove old edges
    while(edgeGroup.children.length > 0) {{
        const child = edgeGroup.children[0];
        child.geometry?.dispose();
        child.material?.dispose();
        edgeGroup.remove(child);
    }}

    EDGES.forEach(e => {{
        const src = nodeObjects.get(e.source);
        const tgt = nodeObjects.get(e.target);
        if (!src || !tgt) return;

        const p1 = src.position.clone();
        const p2 = tgt.position.clone();
        const mid = p1.clone().add(p2).multiplyScalar(0.5);
        const dir = p2.clone().sub(p1);
        const len = dir.length();
        if (len < 0.001) return;

        const color = new THREE.Color(e.color || '#446688');
        const weight = e.weight || 1;
        const radius = 0.015 + weight * 0.025;

        const cylGeo = new THREE.CylinderGeometry(radius, radius, len, 6, 1);
        const cylMat = new THREE.MeshStandardMaterial({{
            color: color,
            transparent: true,
            opacity: 0.5 + weight * 0.3,
            roughness: 0.5,
            metalness: 0.1,
        }});
        const cyl = new THREE.Mesh(cylGeo, cylMat);
        cyl.position.copy(mid);
        const up = new THREE.Vector3(0, 1, 0);
        const quat = new THREE.Quaternion().setFromUnitVectors(up, dir.clone().normalize());
        cyl.quaternion.copy(quat);
        edgeGroup.add(cyl);

        const lineMat = new THREE.LineBasicMaterial({{
            color: color,
            transparent: true,
            opacity: 0.15 + weight * 0.2,
        }});
        const lineGeo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
        const line = new THREE.Line(lineGeo, lineMat);
        edgeGroup.add(line);
    }});
}}

// Run force layout
runForceLayout(60);

// ── Legend ────────────────────────────────────
const legendEl = document.getElementById('legend');
let legendHTML = '';
for (const [cat, color] of Object.entries(CAT_COLORS)) {{
    legendHTML += `<div class="legend-item"><span class="legend-color" style="background:${{color}}"></span>${{cat}}</div>`;
}}
legendEl.innerHTML = legendHTML;

// ── Hover Highlighting ────────────────────────
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
let hoveredMesh = null;

const allMeshes = Array.from(nodeMeshes.values());

renderer.domElement.addEventListener('mousemove', (event) => {{
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(allMeshes);

    // Reset previous
    if (hoveredMesh) {{
        const mat = hoveredMesh.material;
        mat.emissive.copy(hoveredMesh.userData.origColor.clone().multiplyScalar(0.08));
        mat.emissiveIntensity = 0.3;
        mat.needsUpdate = true;
        // Reset label sprite
        const labelSprite = nodeLabels.get(hoveredMesh.userData.nodeId);
        if (labelSprite) {{
            labelSprite.scale.set(hoveredMesh.userData.origLabelScale.x,
                                  hoveredMesh.userData.origLabelScale.y, 1);
        }}
        hoveredMesh = null;
        document.body.style.cursor = 'default';
    }}

    if (intersects.length > 0) {{
        const obj = intersects[0].object;
        if (obj.userData.idx !== undefined) {{
            hoveredMesh = obj;
            const mat = obj.material;
            mat.emissive.copy(new THREE.Color(0xffff88));
            mat.emissiveIntensity = 0.8;
            mat.needsUpdate = true;
            const labelSprite = nodeLabels.get(obj.userData.nodeId);
            if (labelSprite) {{
                labelSprite.scale.set(
                    obj.userData.origLabelScale.x * 1.3,
                    obj.userData.origLabelScale.y * 1.3, 1);
            }}
            document.body.style.cursor = 'pointer';
        }}
    }}
}});

// ── Auto-rotate toggle ────────────────────────
document.getElementById('chkRotate').addEventListener('change', (e) => {{
    controls.autoRotate = e.target.checked;
}});

// ── Resize ────────────────────────────────────
window.addEventListener('resize', () => {{
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    labelRenderer.setSize(window.innerWidth, window.innerHeight);
}});

// ── Animation Loop ────────────────────────────
const statsEl = document.getElementById('stats');

function animate() {{
    requestAnimationFrame(animate);

    // Gentle star rotation
    stars.rotation.y += 0.0001;

    controls.update();

    // Update stats
    const pos = camera.position;
    statsEl.textContent = `Camera: (${{pos.x.toFixed(1)}}, ${{pos.y.toFixed(1)}}, ${{pos.z.toFixed(1)}})`;

    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);
}}

animate();
</script>
</body>
</html>"""

# ──────────────────────────────────────────────
# Functions
# ──────────────────────────────────────────────

def generate_demo_graph(z_dimension='time'):
    """Generate a demo knowledge graph with 4-6 categories and random nodes/edges."""
    random.seed(42)

    categories = {
        'AI/ML':     '#ff6b6b',
        'Systems':   '#4ecdc4',
        'Data':      '#45b7d1',
        'Security':  '#96ceb4',
        'Network':   '#ffeaa7',
        'Theory':    '#dfe6e9',
    }

    # Pick 4-6 categories
    cat_names = random.sample(list(categories.keys()), random.randint(4, 6))
    cat_colors = {k: categories[k] for k in cat_names}

    topic_prefixes = {
        'AI/ML':     ['Transformer', 'CNN', 'RNN', 'GAN', 'VAE', 'Attention', 'BERT', 'GPT', 'CLIP', 'Diffusion'],
        'Systems':   ['Linux', 'Kubernetes', 'Docker', 'Mesos', 'Hadoop', 'Spark', 'Flink', 'Kafka', 'Zookeeper', 'etcd'],
        'Data':      ['PostgreSQL', 'MongoDB', 'Redis', 'Cassandra', 'Elasticsearch', 'Neo4j', 'Snowflake', 'BigQuery', 'Druid', 'Pinot'],
        'Security':  ['OAuth', 'TLS', 'ZeroTrust', 'Firewall', 'IDS', 'WAF', 'SIEM', 'SOAR', 'DLP', 'IAM'],
        'Network':   ['TCP/IP', 'HTTP/3', 'gRPC', 'WebSocket', 'QUIC', 'MPLS', 'SDN', 'VPC', 'CDN', 'DNS'],
        'Theory':    ['Graph', 'Information', 'Complexity', 'Category', 'Game', 'Queueing', 'Coding', 'Optimization', 'Probability', 'Set'],
    }

    shapes = ['sphere', 'sphere', 'sphere', 'cube']

    # Generate nodes: 25-45 nodes
    num_nodes = random.randint(25, 45)
    nodes = []
    node_ids = []

    for i in range(num_nodes):
        cat = random.choice(cat_names)
        prefix = random.choice(topic_prefixes[cat])
        suffix = random.randint(1, 99)
        node_id = f"{prefix.lower()}-{suffix}"
        while node_id in node_ids:
            suffix = random.randint(1, 99)
            node_id = f"{prefix.lower()}-{suffix}"
        node_ids.append(node_id)

        # Random positions in 3D
        x = random.uniform(-8, 8)
        y = random.uniform(-6, 6)
        z_orig = random.uniform(-6, 6)

        if z_dimension == 'time':
            # Simulated timeline: map time value to z (-6 to 6)
            # Generate a fake "time" that spreads nodes across the z-axis
            z_val = (i / num_nodes) * 12 - 6 + random.uniform(-1.5, 1.5)
        elif z_dimension == 'weight':
            z_val = random.uniform(-6, 6)
        else:
            z_val = random.uniform(-6, 6)

        nodes.append({
            'id': node_id,
            'label': f"{prefix} {suffix}",
            'category': cat,
            'shape': random.choice(shapes),
            'size': random.uniform(0.4, 0.8),
            'x': x,
            'y': y,
            'z': z_val,
            '_z_orig': z_val,
            'vx': 0, 'vy': 0, 'vz': 0,
        })

    # Generate edges: num_nodes * ~1.4
    num_edges = int(num_nodes * random.uniform(1.2, 1.8))
    edges = []
    edge_pairs = set()

    for _ in range(num_edges):
        si = random.randint(0, num_nodes - 1)
        ti = random.randint(0, num_nodes - 1)
        if si == ti:
            continue
        key = (min(si, ti), max(si, ti))
        if key in edge_pairs:
            continue
        edge_pairs.add(key)

        weight = random.uniform(0.3, 1.0)
        # Edge color = blend of source and target category colors
        c1 = cat_colors[nodes[si]['category']]
        c2 = cat_colors[nodes[ti]['category']]
        edges.append({
            'source': nodes[si]['id'],
            'target': nodes[ti]['id'],
            'weight': round(weight, 2),
            'color': blend_colors(c1, c2),
            'label': f"{weight:.1f}",
        })

    return nodes, edges, cat_colors


def blend_colors(c1, c2):
    """Blend two hex colors."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = (r1 + r2) // 2
    g = (g1 + g2) // 2
    b = (b1 + b2) // 2
    return f'#{r:02x}{g:02x}{b:02x}'


def render_html(nodes, edges, cat_colors, z_dimension='none',
                spring_k=0.08, repulsion_k=20.0, gravity_k=0.02,
                damping=0.02, center_gravity=0.01):
    """Render the final HTML with embedded data."""

    # Clean nodes for JSON (remove temp fields)
    clean_nodes = []
    for n in nodes:
        clean = {
            'id': n['id'],
            'label': n.get('label', n['id']),
            'category': n['category'],
            'shape': n.get('shape', 'sphere'),
            'size': n.get('size', 0.6),
            'x': round(n.get('x', 0), 4),
            'y': round(n.get('y', 0), 4),
            'z': round(n.get('z', 0), 4),
        }
        clean_nodes.append(clean)

    clean_edges = []
    for e in edges:
        clean_edges.append({
            'source': e['source'],
            'target': e['target'],
            'weight': e.get('weight', 1),
            'color': e.get('color', '#446688'),
            'label': e.get('label', ''),
        })

    nodes_json = json.dumps(clean_nodes, indent=2)
    edges_json = json.dumps(clean_edges, indent=2)
    categories_json = json.dumps(sorted(cat_colors.keys()))
    cat_colors_json = json.dumps(cat_colors)

    html = HTML_TEMPLATE.format(
        nodes_json=nodes_json,
        edges_json=edges_json,
        categories_json=categories_json,
        cat_colors_json=cat_colors_json,
        z_dimension=z_dimension,
        spring_k=spring_k,
        repulsion_k=repulsion_k,
        gravity_k=gravity_k,
        damping=damping,
        center_gravity=center_gravity,
        node_count=len(clean_nodes),
        edge_count=len(clean_edges),
    )

    return html


def main():
    parser = argparse.ArgumentParser(
        description='Generate a true 3D Knowledge Graph HTML page using Three.js')
    parser.add_argument('--input', '-i', type=str, default=None,
                        help='Input JSON file with nodes and edges')
    parser.add_argument('--output', '-o', type=str, default='knowledge-graph-3d.html',
                        help='Output HTML file path')
    parser.add_argument('--z-dimension', type=str, default='time',
                        choices=['weight', 'time', 'none'],
                        help='Z-axis binding: weight, time, or none')
    parser.add_argument('--spring', type=float, default=0.08,
                        help='Spring constant (default: 0.08)')
    parser.add_argument('--repulsion', type=float, default=20.0,
                        help='Repulsion constant (default: 20.0)')
    parser.add_argument('--gravity', type=float, default=0.02,
                        help='Gravity constant toward center (default: 0.02)')
    parser.add_argument('--damping', type=float, default=0.02,
                        help='Velocity damping factor (default: 0.02)')
    parser.add_argument('--center-gravity', type=float, default=0.01,
                        help='Center gravity strength (default: 0.01)')
    args = parser.parse_args()

    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
        nodes = data.get('nodes', data)
        edges = data.get('edges', [])
        cat_colors = data.get('categories', {})
        if not cat_colors:
            # Auto-assign colors from node categories
            cats = set(n.get('category', 'default') for n in nodes)
            pal = ['#ff6b6b','#4ecdc4','#45b7d1','#96ceb4','#ffeaa7','#dfe6e9','#a29bfe','#fd79a8','#e17055','#00cec9']
            cat_colors = {c: pal[i % len(pal)] for i, c in enumerate(sorted(cats))}
    else:
        print("No input file specified. Generating demo knowledge graph...")
        nodes, edges, cat_colors = generate_demo_graph(args.z_dimension)

    html = render_html(
        nodes, edges, cat_colors,
        z_dimension=args.z_dimension,
        spring_k=args.spring,
        repulsion_k=args.repulsion,
        gravity_k=args.gravity,
        damping=args.damping,
        center_gravity=args.center_gravity,
    )

    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    abs_path = os.path.abspath(args.output)
    sys.stdout.reconfigure(errors="replace")
    print(f"\n✅ 3D Knowledge Graph generated: {abs_path}")
    print(f"   Nodes: {len(nodes)}, Edges: {len(edges)}")
    print(f"   Z-dimension: {args.z_dimension}")
    print(f"   Open in your browser to explore!")


if __name__ == '__main__':
    main()
