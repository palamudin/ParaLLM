import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const MATERIAL_COLORS = {
  "module-call": 0xffdf80,
  contains: 0x78aef7,
  defines: 0x4fa69f,
  calls: 0x66d9cf,
  ambiguous: 0xffc66d
};

export class RepoSpatialRenderer {
  constructor(container, callbacks = {}) {
    this.container = container;
    this.callbacks = callbacks;
    this.projection = "isometric";
    this.selectedId = "";
    this.hoveredId = "";
    this.dataKey = "";
    this.objectById = new Map();
    this.pickables = [];
    this.materials = new Map();
    this.geometries = new Map();
    this.pointerDown = null;
    this.orthoHeight = 80;
    this.theme = "";

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x030b12);
    this.scene.fog = new THREE.FogExp2(0x030b12, 0.0032);

    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance"
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.35;
    this.renderer.domElement.className = "repo-3d-canvas";
    this.renderer.domElement.setAttribute("aria-label", "Interactive repository architecture map");
    this.container.replaceChildren(this.renderer.domElement);

    this.tooltip = document.createElement("div");
    this.tooltip.className = "repo-3d-tooltip";
    this.tooltip.hidden = true;
    this.container.appendChild(this.tooltip);

    this.world = new THREE.Group();
    this.nodeGroup = new THREE.Group();
    this.edgeGroup = new THREE.Group();
    this.labelGroup = new THREE.Group();
    this.helperGroup = new THREE.Group();
    this.world.add(this.edgeGroup, this.nodeGroup, this.labelGroup, this.helperGroup);
    this.scene.add(this.world);

    this.scene.add(new THREE.AmbientLight(0x8fc8ff, 1.15));
    this.scene.add(new THREE.HemisphereLight(0xc6e5ff, 0x0b1c2b, 2.2));
    const keyLight = new THREE.DirectionalLight(0xd9f3ff, 2.4);
    keyLight.position.set(40, 70, 30);
    this.scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0x4f8dff, 1.1);
    rimLight.position.set(-55, 18, -40);
    this.scene.add(rimLight);

    this.perspectiveCamera = new THREE.PerspectiveCamera(48, 1, 0.1, 3000);
    this.orthographicCamera = new THREE.OrthographicCamera(-40, 40, 40, -40, 0.1, 3000);
    this.camera = this.orthographicCamera;
    this.controls = null;
    this.activateCamera("isometric");

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.installEvents();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.container);
    this.applyTheme();
    this.resize();
  }

  setData({ nodes = [], edges = [], projection = "isometric", detailMode = "overview", selectedId = "", hoveredId = "", showLabels = true }) {
    const nextProjection = projection === "spatial" ? "spatial" : "isometric";
    const nextDetailMode = detailMode || "overview";
    const nextKey = [
      nextProjection,
      nextDetailMode,
      showLabels ? "labels" : "plain",
      nodes.map(node => node.id).join("|"),
      edges.map(edge => edge.id || `${edge.sourceId}:${edge.targetId}`).join("|")
    ].join("::");
    const projectionChanged = this.projection !== nextProjection;
    this.projection = nextProjection;
    this.detailMode = nextDetailMode;
    this.selectedId = selectedId || "";
    this.hoveredId = hoveredId || "";
    if (projectionChanged) this.activateCamera(nextProjection);
    if (nextKey !== this.dataKey) {
      this.dataKey = nextKey;
      this.rebuild(nodes, edges, showLabels);
    }
    this.updateHelpers();
    this.render();
  }

  rebuild(nodes, edges, showLabels) {
    this.clearWorld();
    const displayNodes = this.projection === "isometric" && this.detailMode !== "functions"
      ? nodes.filter(node => node.nodeKind !== "function")
      : nodes;
    const visibleIds = new Set(displayNodes.map(node => node.id));
    for (const node of displayNodes) {
      const mesh = this.createNodeMesh(node);
      if (!mesh) continue;
      this.nodeGroup.add(mesh);
      this.objectById.set(node.id, mesh);
      this.pickables.push(mesh);
    }
    this.createEdges(edges.filter(edge => visibleIds.has(edge.sourceId) && visibleIds.has(edge.targetId)));
    if (showLabels) {
      const structuralCount = displayNodes.filter(node => node.nodeKind !== "function").length;
      for (const node of displayNodes) {
        if (node.nodeKind === "function") continue;
        if (node.nodeKind === "file" && structuralCount > 90 && node.id !== this.selectedId) continue;
        const mesh = this.objectById.get(node.id);
        if (!mesh) continue;
        const sprite = createLabelSprite(node, node.nodeKind === "module");
        const lift = this.projection === "isometric"
          ? Math.max(1.2, mesh.scale.y + 0.9)
          : Math.max(1.1, mesh.scale.y + 0.65);
        sprite.position.copy(mesh.position).add(new THREE.Vector3(0, lift, 0));
        this.labelGroup.add(sprite);
      }
    }
    this.addReferencePlane();
  }

  createNodeMesh(node) {
    const layout = node.layout?.[this.projection];
    if (!layout) return null;
    const geometry = this.geometryFor(node);
    const material = this.materialFor(node);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.nodeId = node.id;
    mesh.userData.nodeKind = node.nodeKind;
    mesh.userData.label = node.nodeKind === "function"
      ? `${node.name} | ${node.file}:${node.line || 0}`
      : node.nodeKind === "file"
        ? `${node.file} | ${node.functionCount || 0} functions`
        : `${node.module} | layer ${node.layer || 0}`;

    if (this.projection === "isometric") {
      const scale = isometricScale(node);
      mesh.scale.set(scale.x, scale.y, scale.z);
      mesh.position.set(layout.x, layout.y + scale.y / 2, layout.z);
    } else {
      const scale = spatialScale(node);
      mesh.scale.setScalar(scale);
      mesh.position.set(layout.x, layout.y, layout.z);
    }
    return mesh;
  }

  geometryFor(node) {
    const key = this.projection === "isometric"
      ? node.nodeKind === "function" ? "iso-function" : "iso-box"
      : node.nodeKind === "module" ? "space-module" : node.nodeKind === "file" ? "space-file" : "space-function";
    if (this.geometries.has(key)) return this.geometries.get(key);
    let geometry;
    if (key === "iso-box") geometry = new THREE.BoxGeometry(1, 1, 1);
    else if (key === "iso-function") geometry = new THREE.SphereGeometry(1, 12, 8);
    else if (key === "space-module") geometry = new THREE.IcosahedronGeometry(1, 2);
    else if (key === "space-file") geometry = new THREE.BoxGeometry(1, 1, 1);
    else geometry = new THREE.SphereGeometry(1, 9, 6);
    this.geometries.set(key, geometry);
    return geometry;
  }

  materialFor(node) {
    const color = new THREE.Color(node.color || "#66d9cf");
    if (node.nodeKind === "file") color.multiplyScalar(0.78);
    if (node.nodeKind === "function") color.multiplyScalar(1.08);
    const key = `${node.nodeKind}:${color.getHexString()}:${this.projection}`;
    if (this.materials.has(key)) return this.materials.get(key);
    const material = new THREE.MeshStandardMaterial({
      color,
      emissive: color.clone().multiplyScalar(node.nodeKind === "module" ? 0.42 : 0.28),
      emissiveIntensity: node.nodeKind === "module" ? 1.15 : node.nodeKind === "file" ? 0.78 : 1.1,
      roughness: this.projection === "isometric" ? 0.62 : 0.5,
      metalness: node.nodeKind === "module" ? 0.28 : 0.12,
      transparent: true,
      opacity: node.nodeKind === "function" ? 0.9 : 0.96
    });
    this.materials.set(key, material);
    return material;
  }

  createEdges(edges) {
    const groups = new Map();
    const edgeLimit = this.projection === "spatial" ? 7000 : 2800;
    const candidates = [];
    for (const edge of edges) {
      if (candidates.length >= edgeLimit) break;
      if (this.projection === "isometric" && !["module-call", "contains"].includes(edge.relation)) continue;
      const source = this.objectById.get(edge.sourceId);
      const target = this.objectById.get(edge.targetId);
      if (!source || !target) continue;
      const relation = edge.relation === "ambiguous" || edge.ambiguous ? "ambiguous" : edge.relation || "calls";
      candidates.push({ edge, source, target, relation });
    }
    const pairGroups = groupEdgeCandidates(candidates, item => `${item.edge.sourceId}\u0000${item.edge.targetId}`);
    const sourceGroups = groupEdgeCandidates(candidates, item => item.edge.sourceId);
    const pairLanes = assignCandidateLanes(pairGroups);
    const sourceLanes = assignCandidateLanes(sourceGroups);
    for (const item of candidates) {
      const { edge, source, target, relation } = item;
      if (!groups.has(relation)) groups.set(relation, []);
      const start = source.position.clone();
      const end = target.position.clone();
      const midpoint = start.clone().lerp(end, 0.5);
      const direction = end.clone().sub(start).normalize();
      const reference = Math.abs(direction.y) < 0.88 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0);
      const perpendicular = direction.clone().cross(reference).normalize();
      const lane = (pairLanes.get(item) || 0) * 1.25 + (sourceLanes.get(item) || 0) * 0.32;
      if (Number.isFinite(lane) && Math.abs(lane) > 0.001) midpoint.addScaledVector(perpendicular, lane);
      groups.get(relation).push(
        start.x, start.y, start.z,
        midpoint.x, midpoint.y, midpoint.z,
        midpoint.x, midpoint.y, midpoint.z,
        end.x, end.y, end.z
      );
    }
    for (const [relation, positions] of groups) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      const opacity = relation === "module-call" ? 0.9 : relation === "contains" ? 0.48 : relation === "defines" ? 0.2 : 0.38;
      const material = new THREE.LineBasicMaterial({
        color: MATERIAL_COLORS[relation] || MATERIAL_COLORS.calls,
        transparent: true,
        opacity,
        depthWrite: false
      });
      const lines = new THREE.LineSegments(geometry, material);
      lines.renderOrder = relation === "module-call" ? 3 : 1;
      this.edgeGroup.add(lines);
    }
  }

  addReferencePlane() {
    if (this.projection !== "isometric") return;
    const grid = new THREE.GridHelper(260, 52, 0x315b78, 0x153247);
    grid.material.transparent = true;
    grid.material.opacity = 0.4;
    grid.position.y = -0.06;
    this.edgeGroup.add(grid);
  }

  activateCamera(projection) {
    const previousTarget = this.controls?.target?.clone() || new THREE.Vector3();
    this.controls?.dispose();
    if (projection === "spatial") {
      this.camera = this.perspectiveCamera;
      this.camera.position.set(90, 58, 112);
    } else {
      this.camera = this.orthographicCamera;
      this.camera.position.set(78, 64, 78);
    }
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.autoRotate = false;
    this.controls.screenSpacePanning = true;
    this.controls.zoomToCursor = true;
    this.controls.minDistance = 3;
    this.controls.maxDistance = 1200;
    this.controls.target.copy(previousTarget);
    this.controls.addEventListener("change", () => {
      this.callbacks.onZoom?.(this.zoomLevel());
      this.render();
    });
    this.controls.update();
    this.resize();
  }

  updateHelpers() {
    this.clearGroup(this.helperGroup, true);
    const selected = this.objectById.get(this.selectedId);
    const hovered = this.objectById.get(this.hoveredId);
    if (selected) {
      const helper = new THREE.BoxHelper(selected, 0xffffff);
      helper.material.transparent = true;
      helper.material.opacity = 0.95;
      this.helperGroup.add(helper);
    }
    if (hovered && hovered !== selected) {
      const helper = new THREE.BoxHelper(hovered, 0x8ab4ff);
      helper.material.transparent = true;
      helper.material.opacity = 0.72;
      this.helperGroup.add(helper);
    }
  }

  focus(id) {
    const object = this.objectById.get(id);
    if (!object) return;
    const offset = this.camera.position.clone().sub(this.controls.target);
    const distance = Math.max(10, offset.length() * 0.58);
    this.controls.target.copy(object.position);
    this.camera.position.copy(object.position).add(offset.normalize().multiplyScalar(distance));
    this.controls.update();
    this.render();
  }

  fit() {
    if (!this.nodeGroup.children.length) return;
    const box = new THREE.Box3().setFromObject(this.nodeGroup);
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const center = sphere.center;
    const radius = Math.max(5, sphere.radius);
    this.controls.target.copy(center);
    if (this.projection === "isometric") {
      const rect = this.container.getBoundingClientRect();
      const aspect = Math.max(0.2, rect.width / Math.max(1, rect.height));
      this.camera.position.copy(center).add(new THREE.Vector3(1, 0.82, 1).normalize().multiplyScalar(radius * 3.2));
      this.camera.lookAt(center);
      this.camera.updateMatrixWorld(true);
      const corners = [];
      for (const x of [box.min.x, box.max.x]) {
        for (const y of [box.min.y, box.max.y]) {
          for (const z of [box.min.z, box.max.z]) {
            corners.push(new THREE.Vector3(x, y, z).applyMatrix4(this.camera.matrixWorldInverse));
          }
        }
      }
      const projectedWidth = Math.max(...corners.map(point => point.x)) - Math.min(...corners.map(point => point.x));
      const projectedHeight = Math.max(...corners.map(point => point.y)) - Math.min(...corners.map(point => point.y));
      this.orthoHeight = Math.max(18, projectedHeight + 10, (projectedWidth + 18) / aspect) * 1.08;
    } else {
      const distance = radius / Math.sin(THREE.MathUtils.degToRad(this.perspectiveCamera.fov / 2)) * 0.6;
      this.camera.position.copy(center).add(new THREE.Vector3(1, 0.82, 1.2).normalize().multiplyScalar(distance));
    }
    this.resize();
    this.controls.update();
    this.callbacks.onZoom?.(1);
    this.render();
  }

  resize() {
    const rect = this.container.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    this.renderer.setSize(width, height, false);
    const aspect = width / height;
    this.perspectiveCamera.aspect = aspect;
    this.perspectiveCamera.updateProjectionMatrix();
    this.orthographicCamera.left = -this.orthoHeight * aspect / 2;
    this.orthographicCamera.right = this.orthoHeight * aspect / 2;
    this.orthographicCamera.top = this.orthoHeight / 2;
    this.orthographicCamera.bottom = -this.orthoHeight / 2;
    this.orthographicCamera.updateProjectionMatrix();
    this.render();
  }

  render() {
    this.applyTheme();
    this.renderer.render(this.scene, this.camera);
  }

  applyTheme() {
    const theme = document.documentElement.getAttribute("data-bs-theme") === "light" ? "light" : "dark";
    if (this.theme === theme) return;
    this.theme = theme;
    const background = theme === "light" ? 0xe8f0f7 : 0x030b12;
    this.scene.background.setHex(background);
    this.scene.fog.color.setHex(background);
    this.scene.fog.density = theme === "light" ? 0.00018 : 0.00032;
    this.renderLabelsForTheme();
  }

  renderLabelsForTheme() {
    for (const sprite of this.labelGroup.children) {
      const node = sprite.userData.node;
      if (!node) continue;
      const previous = sprite.material?.map;
      const replacement = createLabelTexture(node, Boolean(sprite.userData.strong), this.theme);
      sprite.material.map = replacement;
      sprite.material.needsUpdate = true;
      previous?.dispose?.();
    }
  }

  installEvents() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", event => {
      this.pointerDown = { x: event.clientX, y: event.clientY };
    });
    canvas.addEventListener("pointerup", event => {
      if (!this.pointerDown) return;
      const distance = Math.hypot(event.clientX - this.pointerDown.x, event.clientY - this.pointerDown.y);
      this.pointerDown = null;
      if (distance > 5) return;
      const object = this.pick(event);
      if (object) this.callbacks.onSelect?.(object.userData.nodeId);
    });
    canvas.addEventListener("pointermove", event => {
      const object = this.pick(event);
      const id = object?.userData?.nodeId || "";
      if (id !== this.hoveredId) {
        this.hoveredId = id;
        this.callbacks.onHover?.(id);
        this.updateHelpers();
        this.render();
      }
      if (object) {
        this.tooltip.hidden = false;
        this.tooltip.textContent = object.userData.label || id;
        this.tooltip.style.transform = `translate(${event.offsetX + 14}px, ${event.offsetY + 14}px)`;
        canvas.style.cursor = "pointer";
      } else {
        this.tooltip.hidden = true;
        canvas.style.cursor = "grab";
      }
    });
    canvas.addEventListener("pointerleave", () => {
      this.hoveredId = "";
      this.callbacks.onHover?.("");
      this.tooltip.hidden = true;
      canvas.style.cursor = "grab";
      this.updateHelpers();
      this.render();
    });
  }

  pick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    return this.raycaster.intersectObjects(this.pickables, false)[0]?.object || null;
  }

  zoomLevel() {
    if (this.projection === "isometric") return this.orthographicCamera.zoom;
    const distance = this.camera.position.distanceTo(this.controls.target);
    return Math.max(0.1, Math.min(4, 80 / Math.max(1, distance)));
  }

  clearWorld() {
    this.clearGroup(this.nodeGroup, false);
    this.clearGroup(this.edgeGroup, true);
    this.clearGroup(this.labelGroup, true);
    this.clearGroup(this.helperGroup, true);
    for (const material of this.materials.values()) material.dispose();
    for (const geometry of this.geometries.values()) geometry.dispose();
    this.materials.clear();
    this.geometries.clear();
    this.objectById.clear();
    this.pickables = [];
  }

  clearGroup(group, dispose) {
    while (group.children.length) {
      const child = group.children.pop();
      if (dispose) {
        child.geometry?.dispose?.();
        if (Array.isArray(child.material)) {
          child.material.forEach(material => {
            material.map?.dispose?.();
            material.dispose?.();
          });
        } else {
          child.material?.map?.dispose?.();
          child.material?.dispose?.();
        }
      }
    }
  }
}

function groupEdgeCandidates(candidates, keyFor) {
  const groups = new Map();
  for (const candidate of candidates) {
    const key = keyFor(candidate);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(candidate);
  }
  return groups;
}

function assignCandidateLanes(groups) {
  const lanes = new Map();
  for (const group of groups.values()) {
    group.sort((a, b) => String(a.edge.targetId).localeCompare(String(b.edge.targetId))
      || String(a.edge.relation).localeCompare(String(b.edge.relation))
      || String(a.edge.id).localeCompare(String(b.edge.id)));
    group.forEach((candidate, index) => {
      lanes.set(candidate, index - (group.length - 1) / 2);
    });
  }
  return lanes;
}

function isometricScale(node) {
  if (node.nodeKind === "module") {
    return {
      x: 5.2 + Math.min(6, Math.sqrt(Number(node.fileCount || 0) + 1) * 1.1),
      y: 1.2 + Math.min(3.2, Math.log1p(Number(node.functionCount || 0)) * 0.48),
      z: 4.2 + Math.min(5, Math.sqrt(Number(node.fileCount || 0) + 1) * 0.9)
    };
  }
  if (node.nodeKind === "file") {
    return {
      x: 2.5,
      y: 0.55 + Math.min(1.8, Math.log1p(Number(node.functionCount || 0)) * 0.3),
      z: 1.45
    };
  }
  const radius = 0.18 + Math.min(0.36, Math.sqrt(Number(node.degree || 0) + 1) * 0.045);
  return { x: radius, y: radius, z: radius };
}

function spatialScale(node) {
  if (node.nodeKind === "module") return 1.8 + Math.min(2.2, Math.log1p(Number(node.functionCount || 0)) * 0.34);
  if (node.nodeKind === "file") return 0.62 + Math.min(0.9, Math.log1p(Number(node.functionCount || 0)) * 0.15);
  return 0.16 + Math.min(0.34, Math.sqrt(Number(node.degree || 0) + 1) * 0.04);
}

function createLabelSprite(node, strong) {
  const texture = createLabelTexture(node, strong, document.documentElement.getAttribute("data-bs-theme") === "light" ? "light" : "dark");
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(strong ? 14.4 : 10.4, strong ? 2.02 : 1.48, 1);
  sprite.renderOrder = 8;
  sprite.userData.node = node;
  sprite.userData.strong = strong;
  return sprite;
}

function createLabelTexture(node, strong, theme) {
  const text = node.nodeKind === "module" ? String(node.module || node.name).toUpperCase() : basename(node.file || node.name);
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 72;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  const light = theme === "light";
  context.fillStyle = light
    ? strong ? "rgba(235, 244, 250, 0.96)" : "rgba(244, 248, 251, 0.9)"
    : strong ? "rgba(3, 12, 20, 0.92)" : "rgba(3, 12, 20, 0.76)";
  context.fillRect(1, 1, canvas.width - 2, canvas.height - 2);
  context.strokeStyle = strong ? "rgba(138, 180, 255, 0.82)" : "rgba(102, 217, 207, 0.42)";
  context.lineWidth = 2;
  context.strokeRect(1, 1, canvas.width - 2, canvas.height - 2);
  context.fillStyle = light ? strong ? "#10283a" : "#244256" : strong ? "#f2f7ff" : "#d9e8f2";
  context.font = `${strong ? 700 : 600} ${strong ? 25 : 22}px ui-monospace, SFMono-Regular, Consolas, monospace`;
  context.textBaseline = "middle";
  context.fillText(trimText(context, text, 476), 18, 37);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  return texture;
}

function trimText(context, value, maxWidth) {
  const text = String(value || "");
  if (context.measureText(text).width <= maxWidth) return text;
  let result = text;
  while (result.length > 4 && context.measureText(`${result}...`).width > maxWidth) result = result.slice(0, -1);
  return `${result}...`;
}

function basename(path) {
  const parts = String(path || "").split("/");
  return parts[parts.length - 1] || String(path || "");
}
