import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Select, Typography, Button, Tooltip, Space, Spin, message,
  Tag, Divider, Modal, Form, Input, Empty, Card, Badge, Alert,
} from "antd";
import {
  EyeOutlined,
  SaveOutlined, CloseOutlined, PlusOutlined,
  TableOutlined, SettingOutlined,
  AimOutlined, EnvironmentOutlined,
} from "@ant-design/icons";
import maplibregl from "maplibre-gl";
import {
  TerraDraw,
  TerraDrawPointMode,
  TerraDrawLineStringMode,
  TerraDrawPolygonMode,
  TerraDrawSelectMode,
} from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import "maplibre-gl/dist/maplibre-gl.css";
import client from "../api/client";
import { mapsApi } from "../api/maps";
import { layers as layersApi } from "../api/layers";
import type {
  GeoDatabase, GeoMap, Layer,
  MapTreeNode, MapLayerNode,
  IdentifyTreeNode, IdentifyLayerNode, IdentifyGroupNode,
} from "../types";
import { MapGroupTree } from "../components/maps/MapGroupTree";
import { SchemaEditor } from "../components/layers/SchemaEditor";
import { AttributeTable } from "../components/layers/AttributeTable";

// ── Types ──────────────────────────────────────────────────────────────────────

interface ApiFeature {
  id: number;
  layer_id: string;
  geom: GeoJSON.Geometry;
  properties: Record<string, unknown>;
  version: number;
}

interface LayerRender {
  layerId: string;
  name: string;
  color: string;
  features: ApiFeature[];
}

type DrawMode = "select" | "point" | "linestring" | "polygon";
type Mode = "view" | "edit" | "identify";

// ── Constants ──────────────────────────────────────────────────────────────────

const COLORS = [
  "#1677ff", "#52c41a", "#fa8c16", "#eb2f96",
  "#722ed1", "#13c2c2", "#f5222d", "#a0d911",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function omitInternal(props: Record<string, unknown>): Record<string, unknown> {
  const { _api_id, _api_version, mode, ...rest } = props;
  void _api_id; void _api_version; void mode;
  return rest;
}

function geomToMode(type: GeoJSON.Geometry["type"]): "point" | "linestring" | "polygon" | null {
  if (type === "Point") return "point";
  if (type === "LineString") return "linestring";
  if (type === "Polygon") return "polygon";
  return null;
}

function toDrawFeatures(features: ApiFeature[]): import("terra-draw").GeoJSONStoreFeatures[] {
  const out: import("terra-draw").GeoJSONStoreFeatures[] = [];
  for (const f of features) {
    const m = geomToMode(f.geom.type);
    if (!m) continue;
    out.push({
      type: "Feature",
      geometry: f.geom as import("terra-draw").GeoJSONStoreGeometries,
      properties: { _api_id: f.id, _api_version: f.version, mode: m, ...f.properties },
    });
  }
  return out;
}

function flattenTreeLayers(tree: MapTreeNode[]): MapLayerNode[] {
  const out: MapLayerNode[] = [];
  function recurse(nodes: MapTreeNode[]) {
    for (const n of nodes) {
      if (n.type === "layer") out.push(n);
      else recurse(n.children);
    }
  }
  recurse(tree);
  return out;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function MapPage() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);

  // Database / map selection
  const [databases, setDatabases] = useState<GeoDatabase[]>([]);
  const [selectedDb, setSelectedDb] = useState<string>("");
  const [maps, setMaps] = useState<GeoMap[]>([]);
  const [selectedMap, setSelectedMap] = useState<string>("");
  const [mapMeta, setMapMeta] = useState<GeoMap | null>(null);
  const [mapTree, setMapTree] = useState<MapTreeNode[]>([]);
  const [loadingMap, setLoadingMap] = useState(false);
  const [autoFitDoneFor, setAutoFitDoneFor] = useState<string>("");

  // Layer rendering on map
  const [layerRenders, setLayerRenders] = useState<Record<string, LayerRender>>({});
  const layerRendersRef = useRef<Record<string, LayerRender>>({});
  layerRendersRef.current = layerRenders;

  // Edit mode
  const [editingLayerId, setEditingLayerId] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>("select");
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);
  const originalFeaturesRef = useRef<ApiFeature[]>([]);

  // Identify mode
  const [mode, setMode] = useState<Mode>("view");
  const [identifyResults, setIdentifyResults] = useState<IdentifyTreeNode[] | null>(null);
  const [identifyBusy, setIdentifyBusy] = useState(false);

  // Map runtime
  const [mapReady, setMapReady] = useState(false);

  // Modals / overlays
  const [newLayerOpen, setNewLayerOpen] = useState(false);
  const [creatingLayer, setCreatingLayer] = useState(false);
  const [newLayerForm] = Form.useForm<{ name: string }>();
  const [schemaLayerId, setSchemaLayerId] = useState<string | null>(null);
  const [openTableIds, setOpenTableIds] = useState<string[]>([]);
  const [activeTableId, setActiveTableId] = useState<string | null>(null);
  const [tableRefreshKey, setTableRefreshKey] = useState(0);
  const [tablePanelHeight, setTablePanelHeight] = useState(280);
  const tableDragging = useRef(false);
  const tableDragStartY = useRef(0);
  const tableDragStartH = useRef(0);

  // ── Load databases ──────────────────────────────────────────────────────────
  useEffect(() => {
    client.get<GeoDatabase[]>("/databases").then((r) => setDatabases(r.data));
  }, []);

  // ── Load maps for selected DB ──────────────────────────────────────────────
  useEffect(() => {
    if (!selectedDb) { setMaps([]); setSelectedMap(""); return; }
    mapsApi.list(selectedDb).then((rows) => {
      setMaps(rows);
      // Auto-select first map for convenience
      if (rows.length > 0 && !rows.find((m) => m.id === selectedMap)) {
        setSelectedMap(rows[0].id);
      } else if (rows.length === 0) {
        setSelectedMap("");
      }
    }).catch(() => setMaps([]));
  }, [selectedDb]);

  // ── Load map tree when selectedMap changes ──────────────────────────────────
  const loadMapData = useCallback(async () => {
    if (!selectedMap) { setMapMeta(null); setMapTree([]); return; }
    setLoadingMap(true);
    try {
      const res = await mapsApi.open(selectedMap);
      if (res.status === 200) {
        setMapMeta(res.data.map);
        setMapTree(res.data.tree);
      }
    } catch {
      message.error("Failed to load map");
    } finally {
      setLoadingMap(false);
    }
  }, [selectedMap]);

  useEffect(() => { loadMapData(); }, [loadMapData]);

  // ── Auto-fitBounds when extent is set (once per map) ───────────────────────
  useEffect(() => {
    if (!mapReady || !mapMeta || !mapMeta.extent) return;
    if (autoFitDoneFor === mapMeta.id) return;
    try {
      mapRef.current?.fitBounds(
        [[mapMeta.extent[0], mapMeta.extent[1]], [mapMeta.extent[2], mapMeta.extent[3]]],
        { padding: 60, maxZoom: 14, animate: false }
      );
      setAutoFitDoneFor(mapMeta.id);
    } catch {
      // ignore degenerate envelopes
    }
  }, [mapMeta, mapReady, autoFitDoneFor]);

  // ── Reconcile layer renders with the map tree's visible layers ─────────────
  const flatLayers = useMemo(() => flattenTreeLayers(mapTree), [mapTree]);

  useEffect(() => {
    // For visible layers not yet loaded, fetch them. For invisible loaded
    // layers, drop them so we redraw the map without their features.
    const visibleIds = new Set(flatLayers.filter((l) => l.is_visible).map((l) => l.layer_id));
    const current = layerRendersRef.current;

    // Drop invisible
    const next: Record<string, LayerRender> = {};
    for (const [lid, render] of Object.entries(current)) {
      if (visibleIds.has(lid)) next[lid] = render;
    }
    let changed = Object.keys(next).length !== Object.keys(current).length;

    // Fetch missing (visible but not yet loaded)
    const toFetch = flatLayers.filter((l) => l.is_visible && !current[l.layer_id]);
    if (toFetch.length === 0) {
      if (changed) setLayerRenders(next);
      return;
    }

    let cancelled = false;
    Promise.all(
      toFetch.map((l, i) =>
        client.get<ApiFeature[]>(`/layers/${l.layer_id}/features?limit=5000`)
          .then((r) => ({ layer: l, features: r.data, idx: i }))
          .catch(() => ({ layer: l, features: [], idx: i }))
      )
    ).then((results) => {
      if (cancelled) return;
      const final = { ...next };
      results.forEach(({ layer, features }, i) => {
        final[layer.layer_id] = {
          layerId: layer.layer_id,
          name: layer.name,
          color: COLORS[(Object.keys(final).length + i) % COLORS.length],
          features,
        };
      });
      setLayerRenders(final);
    });
    return () => { cancelled = true; };
  }, [flatLayers]);

  // ── Init map ────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [35.2, 31.8],
      zoom: 7,
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("style.load", () => {
      try {
        const draw = new TerraDraw({
          adapter: new TerraDrawMapLibreGLAdapter({ map }),
          modes: [
            new TerraDrawSelectMode({
              flags: {
                point: { feature: { draggable: true } },
                linestring: {
                  feature: {
                    draggable: true,
                    coordinates: { midpoints: true, draggable: true, deletable: true },
                  },
                },
                polygon: {
                  feature: {
                    draggable: true,
                    coordinates: { midpoints: true, draggable: true, deletable: true },
                  },
                },
              },
            }),
            new TerraDrawPointMode(),
            new TerraDrawLineStringMode(),
            new TerraDrawPolygonMode({
              styles: {
                fillColor: "#fa541c",
                fillOpacity: 0.2,
                outlineColor: "#fa541c",
                outlineWidth: 2,
              },
            }),
          ],
        });

        draw.start();
        draw.on("change", () => {
          // hasChanges is only meaningful in edit mode
          if (editingLayerIdRef.current) setHasChanges(true);
        });

        // Identify-mode: when polygon drawing finishes, run identify
        draw.on("finish", async (id) => {
          if (modeRef.current !== "identify") return;
          const snapshot = draw.getSnapshot();
          const feat = snapshot.find((f) => f.id === id);
          if (!feat || feat.geometry.type !== "Polygon") return;
          await runIdentify(feat.geometry as GeoJSON.Polygon);
          // clear the drawn polygon
          const ids = draw.getSnapshot().map((f) => f.id as string);
          if (ids.length) draw.removeFeatures(ids);
        });

        drawRef.current = draw;
        setMapReady(true);
      } catch (err) {
        console.error("Failed to initialize TerraDraw:", err);
        message.error("Drawing tools failed to initialize — see console");
      }
    });

    mapRef.current = map;

    return () => {
      drawRef.current?.stop();
      map.remove();
      mapRef.current = null;
      drawRef.current = null;
      setMapReady(false);
    };
  }, []);

  // refs to give terra-draw callbacks fresh state without re-init
  const editingLayerIdRef = useRef<string | null>(null);
  const modeRef = useRef<Mode>("view");
  useEffect(() => { editingLayerIdRef.current = editingLayerId; }, [editingLayerId]);
  useEffect(() => { modeRef.current = mode; }, [mode]);

  // ── Activate draw mode ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !drawRef.current) return;
    if (mode === "edit" && editingLayerId) {
      drawRef.current.setMode(drawMode);
    } else if (mode === "identify") {
      drawRef.current.setMode("polygon");
    } else {
      drawRef.current.setMode("select");
    }
  }, [drawMode, editingLayerId, mode, mapReady]);

  // ── Sync rendered layers onto the map ───────────────────────────────────────
  const syncRender = useCallback((render: LayerRender, hidden = false) => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const sourceId = `layer-${render.layerId}`;

    // Remove if hidden or being edited (terra-draw owns the geometry then)
    if (hidden || render.layerId === editingLayerId) {
      ["circle", "line", "fill", "outline"].forEach((suf) => {
        const id = `${sourceId}-${suf}`;
        if (map.getLayer(id)) map.removeLayer(id);
      });
      if (map.getSource(sourceId)) map.removeSource(sourceId);
      return;
    }

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: render.features.map((f) => ({
        type: "Feature",
        geometry: f.geom,
        properties: f.properties,
      })),
    };

    if (map.getSource(sourceId)) {
      (map.getSource(sourceId) as maplibregl.GeoJSONSource).setData(geojson);
    } else {
      map.addSource(sourceId, { type: "geojson", data: geojson });
      map.addLayer({ id: `${sourceId}-circle`, type: "circle", source: sourceId,
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 6, "circle-color": render.color, "circle-stroke-width": 1.5, "circle-stroke-color": "#fff" } });
      map.addLayer({ id: `${sourceId}-line`, type: "line", source: sourceId,
        filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
        paint: { "line-color": render.color, "line-width": 2 } });
      map.addLayer({ id: `${sourceId}-fill`, type: "fill", source: sourceId,
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "fill-color": render.color, "fill-opacity": 0.25 } });
      map.addLayer({ id: `${sourceId}-outline`, type: "line", source: sourceId,
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "line-color": render.color, "line-width": 1.5 } });
    }
  }, [editingLayerId, mapReady]);

  useEffect(() => {
    if (!mapReady) return;
    Object.values(layerRenders).forEach((r) => syncRender(r));
  }, [layerRenders, syncRender, mapReady]);

  // ── Identify ────────────────────────────────────────────────────────────────
  async function runIdentify(polygon: GeoJSON.Polygon) {
    if (!selectedDb) return;
    setIdentifyBusy(true);
    try {
      const res = await layersApi.identify(selectedDb, polygon);
      setIdentifyResults(res.tree);
    } catch {
      message.error("Identify failed");
    } finally {
      setIdentifyBusy(false);
    }
  }

  function exitIdentify() {
    setMode("view");
    setIdentifyResults(null);
    const draw = drawRef.current;
    if (draw) {
      const ids = draw.getSnapshot().map((f) => f.id as string);
      if (ids.length) draw.removeFeatures(ids);
    }
  }

  function startIdentify() {
    if (!selectedDb) {
      message.warning("Select a database first.");
      return;
    }
    if (editingLayerId) stopEdit();
    setIdentifyResults(null);
    setMode("identify");
    message.info("Draw a polygon on the map (double-click to finish).");
  }

  async function loadIdentifyLayer(layerId: string, name: string, _polygon?: never) {
    void _polygon;
    // Try to use the last drawn polygon from the snapshot — but at this point
    // we already cleared it. Fall back to fetching all features.
    // Simpler: re-fetch everything for the layer (the spec says load with
    // spatial filter, but the polygon is gone after identify completes).
    // We persist the polygon in state to enable spatial-filtered loading.
    if (!lastIdentifyPolygonRef.current) {
      message.warning("Polygon expired — please draw again.");
      return;
    }
    try {
      const res = await client.get<ApiFeature[]>(
        `/layers/${layerId}/features`,
        {
          params: {
            spatial_op: "intersects",
            filter_geojson: JSON.stringify(lastIdentifyPolygonRef.current),
            limit: 5000,
          },
        }
      );
      const idx = Object.keys(layerRendersRef.current).length;
      setLayerRenders((prev) => ({
        ...prev,
        [layerId]: {
          layerId,
          name,
          color: COLORS[idx % COLORS.length],
          features: res.data,
        },
      }));
      message.success(`Loaded ${res.data.length} features from "${name}"`);
    } catch {
      message.error(`Failed to load "${name}"`);
    }
  }

  async function loadAllWithData() {
    if (!identifyResults) return;
    const flat: IdentifyLayerNode[] = [];
    function recurse(nodes: IdentifyTreeNode[]) {
      for (const n of nodes) {
        if (n.type === "layer") flat.push(n);
        else recurse(n.children as unknown as IdentifyTreeNode[]);
      }
    }
    recurse(identifyResults);
    const withData = flat.filter((l) => l.feature_count_in_area > 0);
    for (const l of withData) {
      await loadIdentifyLayer(l.layer_id, l.name);
    }
  }

  // Persist the last polygon so Load buttons can use spatial_op
  const lastIdentifyPolygonRef = useRef<GeoJSON.Polygon | null>(null);
  // Capture the polygon BEFORE we clear it from terra-draw
  useEffect(() => {
    const draw = drawRef.current;
    if (!draw) return;
    type FinishId = Parameters<Parameters<TerraDraw["on"]>[1]>[0];
    const onFinish = async (id: FinishId) => {
      if (modeRef.current !== "identify") return;
      const feat = draw.getSnapshot().find((f) => f.id === id);
      if (feat && feat.geometry.type === "Polygon") {
        lastIdentifyPolygonRef.current = feat.geometry as GeoJSON.Polygon;
      }
    };
    draw.on("finish", onFinish);
    return () => { draw.off("finish", onFinish); };
  }, [mapReady]);

  // ── Edit workflow ───────────────────────────────────────────────────────────
  async function startEdit(layerId: string, layerName: string) {
    if (mode === "identify") exitIdentify();
    setMode("edit");
    setEditingLayerId(layerId);
    setHasChanges(false);
    setDrawMode("select");
    originalFeaturesRef.current = [];

    let features: ApiFeature[] = [];
    const existing = layerRenders[layerId];
    if (existing) {
      features = existing.features;
    } else {
      try {
        const res = await client.get<ApiFeature[]>(`/layers/${layerId}/features?limit=5000`);
        features = res.data;
      } catch {
        message.error("Failed to load features — you can still draw new ones");
      }
    }

    originalFeaturesRef.current = features;

    // Make sure the layer is rendered so the user sees what's already there
    setLayerRenders((prev) => ({
      ...prev,
      [layerId]: prev[layerId] ?? {
        layerId, name: layerName,
        color: COLORS[Object.keys(prev).length % COLORS.length],
        features,
      },
    }));

    const draw = drawRef.current;
    if (!draw) {
      message.warning("Map is still loading — drawing tools will activate in a moment");
      return;
    }

    if (features.length > 0) {
      draw.addFeatures(toDrawFeatures(features));
      const coords: [number, number][] = [];
      features.forEach((f) => {
        if (f.geom.type === "Point") coords.push(f.geom.coordinates as [number, number]);
        if (f.geom.type === "LineString") coords.push(...(f.geom.coordinates as [number, number][]));
      });
      if (coords.length > 0) {
        const lngs = coords.map((c) => c[0]);
        const lats = coords.map((c) => c[1]);
        mapRef.current?.fitBounds(
          [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
          { padding: 80, maxZoom: 14 }
        );
      }
    }
  }

  function stopEdit() {
    const draw = drawRef.current;
    if (draw) {
      const ids = draw.getSnapshot().map((f) => f.id as string);
      if (ids.length > 0) draw.removeFeatures(ids);
      draw.setMode("select");
    }
    setMode("view");
    setEditingLayerId(null);
    setDrawMode("select");
    setHasChanges(false);
    originalFeaturesRef.current = [];
  }

  async function saveEdits() {
    const draw = drawRef.current;
    if (!draw || !editingLayerId) return;
    setSaving(true);
    try {
      const snapshot = draw.getSnapshot();
      const originals = originalFeaturesRef.current;
      const drawnApiIds = new Set(
        snapshot.map((f) => f.properties._api_id).filter((id) => id != null)
      );
      const creates = snapshot.filter((f) => !f.properties._api_id);
      const updates = snapshot.filter((f) => f.properties._api_id != null);
      const deletes = originals.filter((f) => !drawnApiIds.has(f.id));

      await Promise.all([
        ...creates.map((f) =>
          client.post(`/layers/${editingLayerId}/features`, {
            geom: f.geometry,
            properties: omitInternal(f.properties as Record<string, unknown>),
          })
        ),
        ...updates.map((f) =>
          client.put(`/layers/${editingLayerId}/features/${f.properties._api_id}`, {
            geom: f.geometry,
            properties: omitInternal(f.properties as Record<string, unknown>),
            version: f.properties._api_version,
          })
        ),
        ...deletes.map((f) => client.delete(`/layers/${editingLayerId}/features/${f.id}`)),
      ]);
      message.success(`Saved: ${creates.length} created, ${updates.length} updated, ${deletes.length} deleted`);

      const featRes = await client.get<ApiFeature[]>(`/layers/${editingLayerId}/features?limit=5000`);
      originalFeaturesRef.current = featRes.data;
      const ids = draw.getSnapshot().map((f) => f.id as string);
      if (ids.length) draw.removeFeatures(ids);
      draw.addFeatures(toDrawFeatures(featRes.data));
      setLayerRenders((prev) => ({
        ...prev,
        [editingLayerId]: { ...(prev[editingLayerId] ?? { layerId: editingLayerId, name: editingLayerId, color: COLORS[0] }), features: featRes.data },
      }));
      setHasChanges(false);
      // Refresh the tree (geometry_types may have changed)
      loadMapData();
    } catch {
      message.error("Save failed — check for version conflicts and try again");
    } finally {
      setSaving(false);
    }
  }

  // ── Table panel drag-to-resize ─────────────────────────────────────────────
  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      if (!tableDragging.current) return;
      const delta = tableDragStartY.current - e.clientY;
      const maxH = window.innerHeight * 0.75;
      setTablePanelHeight(Math.min(maxH, Math.max(120, tableDragStartH.current + delta)));
    }
    function onMouseUp() {
      if (tableDragging.current) {
        tableDragging.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  function onTableDragStart(e: React.MouseEvent) {
    e.preventDefault();
    tableDragging.current = true;
    tableDragStartY.current = e.clientY;
    tableDragStartH.current = tablePanelHeight;
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
  }
  function closeTab(id: string) {
    setOpenTableIds((prev) => prev.filter((x) => x !== id));
    setActiveTableId((prev) => (prev !== id ? prev : openTableIds.filter((x) => x !== id).slice(-1)[0] ?? null));
  }

  // ── Create layer (adds to current map root) ─────────────────────────────────
  async function createLayer(values: { name: string }) {
    if (!selectedDb) return;
    setCreatingLayer(true);
    try {
      const res = await client.post<Layer>("/layers", {
        name: values.name,
        database_id: selectedDb,
        srid: 4326,
      });
      // If a map is selected, attach the new layer to its root
      if (selectedMap) {
        try {
          await mapsApi.addLayer(selectedMap, { layer_id: res.data.id });
        } catch {
          message.warning(`Layer created but couldn't attach to map`);
        }
      }
      message.success(`Layer "${res.data.name}" created`);
      setNewLayerOpen(false);
      newLayerForm.resetFields();
      loadMapData();
    } catch {
      message.error("Failed to create layer");
    } finally {
      setCreatingLayer(false);
    }
  }

  // ── Per-layer click → start edit ────────────────────────────────────────────
  function handleLayerClick(node: MapLayerNode) {
    if (mode === "identify") return;
    if (editingLayerId === node.layer_id) {
      stopEdit();
    } else {
      startEdit(node.layer_id, node.name);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  const editingLayerNode = editingLayerId
    ? flatLayers.find((l) => l.layer_id === editingLayerId)
    : null;

  const modeButtons: { mode: DrawMode; label: string }[] = [
    { mode: "select", label: "Select" },
    { mode: "point", label: "Point" },
    { mode: "linestring", label: "Line" },
    { mode: "polygon", label: "Polygon" },
  ];

  return (
    <div style={{ display: "flex", height: "calc(100vh - 64px)" }}>
      {/* ── Left panel ── */}
      <div style={{
        width: 320, flexShrink: 0, background: "#fafafa",
        borderRight: "1px solid #f0f0f0", display: "flex",
        flexDirection: "column", padding: "12px 12px", overflowY: "auto",
      }}>
        <Typography.Text strong style={{ marginBottom: 4, display: "block" }}>Database</Typography.Text>
        <Select
          placeholder="Select database"
          style={{ width: "100%", marginBottom: 8 }}
          value={selectedDb || undefined}
          options={databases.map((d) => ({ value: d.id, label: d.name }))}
          onChange={(v) => { setSelectedDb(v); exitIdentify(); }}
        />

        {selectedDb && (
          <>
            <Typography.Text strong style={{ marginBottom: 4, display: "block" }}>Map</Typography.Text>
            {maps.length === 0 ? (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 8 }}
                message="No maps in this database"
                description="Create one from the Maps page."
              />
            ) : (
              <Select
                placeholder="Select map"
                style={{ width: "100%", marginBottom: 8 }}
                value={selectedMap || undefined}
                options={maps.map((m) => ({ value: m.id, label: m.name }))}
                onChange={(v) => { setSelectedMap(v); setIdentifyResults(null); setEditingLayerId(null); }}
              />
            )}
          </>
        )}

        {selectedMap && (
          <Space style={{ marginBottom: 8, marginTop: 4 }} wrap>
            <Tooltip title="New layer (added to this map)">
              <Button size="small" icon={<PlusOutlined />} onClick={() => setNewLayerOpen(true)}>New layer</Button>
            </Tooltip>
            <Tooltip title="Identify by polygon">
              <Button
                size="small"
                type={mode === "identify" ? "primary" : "default"}
                icon={<AimOutlined />}
                onClick={mode === "identify" ? exitIdentify : startIdentify}
              >
                {mode === "identify" ? "Exit identify" : "Identify"}
              </Button>
            </Tooltip>
          </Space>
        )}

        {loadingMap && <Spin size="small" />}

        {/* Identify results panel — shown in place of the tree */}
        {identifyResults !== null && (
          <Card size="small" style={{ marginBottom: 12 }} title="Identify results">
            {identifyBusy && <Spin size="small" />}
            {!identifyBusy && (
              <>
                <Space style={{ marginBottom: 8 }}>
                  <Button size="small" type="primary" onClick={loadAllWithData}>
                    Load all with data
                  </Button>
                  <Button size="small" onClick={() => setIdentifyResults(null)}>Clear</Button>
                </Space>
                <IdentifyResultsTree
                  tree={identifyResults}
                  onLoad={(l) => loadIdentifyLayer(l.layer_id, l.name)}
                />
              </>
            )}
          </Card>
        )}

        {/* Map tree — hidden when identify results are showing */}
        {selectedMap && identifyResults === null && !loadingMap && (
          <MapGroupTree
            tree={mapTree}
            mapId={selectedMap}
            onRefresh={loadMapData}
            onLayerClick={handleLayerClick}
          />
        )}

        {!selectedMap && selectedDb && maps.length > 0 && (
          <Empty description="Pick a map" style={{ marginTop: 24 }} />
        )}

        {editingLayerId && (
          <>
            <Divider style={{ margin: "12px 0" }} />
            <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
              Editing: <strong>{editingLayerNode?.name}</strong>
            </Typography.Text>
            <Space wrap style={{ marginBottom: 12 }}>
              {modeButtons.map(({ mode: m, label }) => (
                <Button
                  key={m} size="small"
                  type={drawMode === m ? "primary" : "default"}
                  onClick={() => setDrawMode(m)}
                >
                  {label}
                </Button>
              ))}
            </Space>
            <Space style={{ width: "100%" }} direction="vertical">
              <Button
                type="primary" icon={<SaveOutlined />} block
                loading={saving} disabled={!hasChanges}
                onClick={saveEdits}
              >
                Save changes
              </Button>
              <Button block icon={<CloseOutlined />} onClick={stopEdit}>Stop editing</Button>
            </Space>
            {hasChanges && (
              <Tag color="orange" style={{ marginTop: 8, textAlign: "center", width: "100%" }}>
                Unsaved changes
              </Tag>
            )}
            {editingLayerNode && (
              <Space style={{ marginTop: 8 }} wrap>
                <Tooltip title="Attribute table">
                  <Button size="small" icon={<TableOutlined />}
                    onClick={() => {
                      setOpenTableIds((p) => p.includes(editingLayerId) ? p : [...p, editingLayerId]);
                      setActiveTableId(editingLayerId);
                    }}
                  />
                </Tooltip>
                <Tooltip title="Fields">
                  <Button size="small" icon={<SettingOutlined />} onClick={() => setSchemaLayerId(editingLayerId)} />
                </Tooltip>
              </Space>
            )}
          </>
        )}

        <Modal
          title="New layer"
          open={newLayerOpen}
          onOk={newLayerForm.submit}
          onCancel={() => { setNewLayerOpen(false); newLayerForm.resetFields(); }}
          confirmLoading={creatingLayer}
        >
          <Form form={newLayerForm} layout="vertical" onFinish={createLayer}>
            <Form.Item name="name" label="Name" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Form>
        </Modal>
      </div>

      {/* ── Map + table column ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div ref={mapContainer} style={{ flex: 1 }} />

        {openTableIds.length > 0 && (
          <div style={{
            height: tablePanelHeight, flexShrink: 0,
            display: "flex", flexDirection: "column",
            borderTop: "2px solid #d9d9d9", background: "#fff",
          }}>
            <div onMouseDown={onTableDragStart} style={{
              height: 6, cursor: "ns-resize", flexShrink: 0,
              background: "linear-gradient(180deg, #e8e8e8 0%, #f5f5f5 100%)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <div style={{ width: 40, height: 3, borderRadius: 2, background: "#bfbfbf" }} />
            </div>
            <div style={{
              display: "flex", alignItems: "stretch", borderBottom: "1px solid #f0f0f0",
              flexShrink: 0, background: "#fafafa", overflow: "auto hidden",
            }}>
              {openTableIds.map((id) => {
                const isActive = id === activeTableId;
                const name = flatLayers.find((l) => l.layer_id === id)?.name ?? "Layer";
                return (
                  <div
                    key={id} onClick={() => setActiveTableId(id)}
                    style={{
                      display: "flex", alignItems: "center", gap: 6, padding: "4px 12px",
                      cursor: "pointer", whiteSpace: "nowrap", fontSize: 12,
                      fontWeight: isActive ? 600 : 400,
                      borderBottom: isActive ? "2px solid #1677ff" : "2px solid transparent",
                      background: isActive ? "#fff" : "transparent",
                      color: isActive ? "#1677ff" : "#595959",
                    }}
                  >
                    {name}
                    <span
                      onClick={(e) => { e.stopPropagation(); closeTab(id); }}
                      style={{
                        display: "inline-flex", alignItems: "center", justifyContent: "center",
                        width: 16, height: 16, borderRadius: "50%", fontSize: 10, lineHeight: 1, color: "#8c8c8c",
                      }}
                    >✕</span>
                  </div>
                );
              })}
            </div>
            <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
              {openTableIds.map((id) => (
                <div key={id} style={{
                  display: id === activeTableId ? "flex" : "none",
                  flexDirection: "column", height: "100%",
                }}>
                  <AttributeTable
                    layerId={id}
                    refreshKey={tableRefreshKey}
                    onFeaturesChanged={() => {
                      client.get<ApiFeature[]>(`/layers/${id}/features?limit=5000`).then((r) => {
                        setLayerRenders((prev) => prev[id]
                          ? { ...prev, [id]: { ...prev[id], features: r.data } }
                          : prev
                        );
                      });
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {schemaLayerId && (
        <SchemaEditor
          layerId={schemaLayerId}
          open={!!schemaLayerId}
          onClose={() => setSchemaLayerId(null)}
          onSaved={() => setTableRefreshKey((k) => k + 1)}
        />
      )}
    </div>
  );
}

// ── Identify-results sub-tree ──────────────────────────────────────────────────

function IdentifyResultsTree({
  tree, onLoad,
}: {
  tree: IdentifyTreeNode[];
  onLoad: (l: IdentifyLayerNode) => void;
}) {
  function renderLayer(l: IdentifyLayerNode, key: string) {
    const dim = l.feature_count_in_area === 0;
    return (
      <div
        key={key}
        style={{ padding: "4px 0", display: "flex", justifyContent: "space-between", alignItems: "center", opacity: dim ? 0.5 : 1 }}
      >
        <Space size={6} style={{ flex: 1, minWidth: 0 }}>
          <EnvironmentOutlined />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140 }} title={l.name}>
            {l.name}
          </span>
          <Badge count={l.feature_count_in_area} style={{ backgroundColor: dim ? "#bfbfbf" : "#1677ff" }} showZero />
        </Space>
        <Button size="small" icon={<EyeOutlined />} onClick={() => onLoad(l)} disabled={dim}>Load</Button>
      </div>
    );
  }

  function renderGroup(g: IdentifyGroupNode, key: string) {
    return (
      <div key={key} style={{ marginBottom: 6 }}>
        <Typography.Text strong style={{ fontSize: 12 }}>
          {g.name} <Tag color="default" style={{ fontSize: 10 }}>{g.features_in_area}</Tag>
        </Typography.Text>
        <div style={{ paddingLeft: 12 }}>
          {g.children.map((l, i) => renderLayer(l, `${key}-${i}`))}
        </div>
      </div>
    );
  }

  if (tree.length === 0) {
    return <div style={{ color: "#8c8c8c", fontSize: 12 }}>No accessible layers in this database.</div>;
  }

  return (
    <div>
      {tree.map((n, i) => n.type === "group" ? renderGroup(n, `g-${i}`) : renderLayer(n, `l-${i}`))}
    </div>
  );
}
