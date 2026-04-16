import { useState, useEffect, useRef, useCallback } from "react";
import {
  Select, Typography, Button, Tooltip, Space, Spin, message,
  List, Tag, Divider,
} from "antd";
import {
  EyeOutlined, EyeInvisibleOutlined, EditOutlined,
  SaveOutlined, CloseOutlined,
} from "@ant-design/icons";
import maplibregl from "maplibre-gl";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "maplibre-gl/dist/maplibre-gl.css";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";
import client from "../api/client";
import type { GeoDatabase, Layer } from "../types";

// ── Types ──────────────────────────────────────────────────────────────────────

interface ApiFeature {
  id: number;
  layer_id: string;
  geom: GeoJSON.Geometry;
  properties: Record<string, unknown>;
  version: number;
}

interface LayerState {
  layer: Layer;
  color: string;
  visible: boolean;
  features: ApiFeature[];
  loaded: boolean;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const COLORS = [
  "#1677ff", "#52c41a", "#fa8c16", "#eb2f96",
  "#722ed1", "#13c2c2", "#f5222d", "#a0d911",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function toDrawFeature(f: ApiFeature): GeoJSON.Feature {
  return {
    type: "Feature",
    id: String(f.id),
    geometry: f.geom,
    properties: { ...f.properties, _api_id: f.id, _api_version: f.version },
  };
}

function omitInternal(props: Record<string, unknown>): Record<string, unknown> {
  const { _api_id, _api_version, ...rest } = props;
  void _api_id; void _api_version;
  return rest;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function MapPage() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const drawRef = useRef<MapboxDraw | null>(null);
  const mapReadyRef = useRef(false);

  const [databases, setDatabases] = useState<GeoDatabase[]>([]);
  const [selectedDb, setSelectedDb] = useState<string>("");
  const [layerStates, setLayerStates] = useState<LayerState[]>([]);
  const [loadingLayers, setLoadingLayers] = useState(false);
  const [editingLayerId, setEditingLayerId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  const originalFeaturesRef = useRef<ApiFeature[]>([]);

  // ── Load databases ──────────────────────────────────────────────────────────
  useEffect(() => {
    client.get<GeoDatabase[]>("/databases").then((r) => setDatabases(r.data));
  }, []);

  // ── Load layers when DB selected ────────────────────────────────────────────
  useEffect(() => {
    if (!selectedDb) return;
    setLoadingLayers(true);
    setLayerStates([]);
    setEditingLayerId(null);
    client.get<Layer[]>(`/layers?database_id=${selectedDb}`)
      .then((r) => {
        setLayerStates(
          r.data.map((layer, i) => ({
            layer,
            color: COLORS[i % COLORS.length],
            visible: false,
            features: [],
            loaded: false,
          }))
        );
      })
      .finally(() => setLoadingLayers(false));
  }, [selectedDb]);

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

    const draw = new MapboxDraw({
      displayControlsDefault: false,
      controls: { point: true, line_string: true, polygon: true, trash: true },
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(draw as unknown as maplibregl.IControl, "top-left");

    map.on("load", () => { mapReadyRef.current = true; });
    map.on("draw.create", () => setHasChanges(true));
    map.on("draw.update", () => setHasChanges(true));
    map.on("draw.delete", () => setHasChanges(true));

    mapRef.current = map;
    drawRef.current = draw;

    return () => {
      map.remove();
      mapRef.current = null;
      drawRef.current = null;
      mapReadyRef.current = false;
    };
  }, []);

  // ── Add / remove view layer sources on the map ──────────────────────────────
  const syncViewLayer = useCallback((ls: LayerState) => {
    const map = mapRef.current;
    if (!map || !mapReadyRef.current) return;
    const sourceId = `layer-${ls.layer.id}`;

    if (!ls.visible || ls.layer.id === editingLayerId) {
      // Remove if hidden or currently being edited (draw tool owns it)
      if (map.getLayer(`${sourceId}-circle`)) map.removeLayer(`${sourceId}-circle`);
      if (map.getLayer(`${sourceId}-line`)) map.removeLayer(`${sourceId}-line`);
      if (map.getLayer(`${sourceId}-fill`)) map.removeLayer(`${sourceId}-fill`);
      if (map.getLayer(`${sourceId}-outline`)) map.removeLayer(`${sourceId}-outline`);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
      return;
    }

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: ls.features.map((f) => ({
        type: "Feature",
        geometry: f.geom,
        properties: f.properties,
      })),
    };

    if (map.getSource(sourceId)) {
      (map.getSource(sourceId) as maplibregl.GeoJSONSource).setData(geojson);
    } else {
      map.addSource(sourceId, { type: "geojson", data: geojson });
      map.addLayer({
        id: `${sourceId}-circle`,
        type: "circle",
        source: sourceId,
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 6, "circle-color": ls.color, "circle-stroke-width": 1.5, "circle-stroke-color": "#fff" },
      });
      map.addLayer({
        id: `${sourceId}-line`,
        type: "line",
        source: sourceId,
        filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
        paint: { "line-color": ls.color, "line-width": 2 },
      });
      map.addLayer({
        id: `${sourceId}-fill`,
        type: "fill",
        source: sourceId,
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "fill-color": ls.color, "fill-opacity": 0.25 },
      });
      map.addLayer({
        id: `${sourceId}-outline`,
        type: "line",
        source: sourceId,
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "line-color": ls.color, "line-width": 1.5 },
      });
    }
  }, [editingLayerId]);

  // ── Toggle layer visibility ─────────────────────────────────────────────────
  async function toggleVisible(layerId: string) {
    let targetState: LayerState | undefined;

    setLayerStates((prev) =>
      prev.map((ls) => {
        if (ls.layer.id !== layerId) return ls;
        targetState = { ...ls, visible: !ls.visible };
        return targetState;
      })
    );

    // Load features if first time showing
    const ls = layerStates.find((l) => l.layer.id === layerId);
    if (ls && !ls.loaded && !ls.visible) {
      const res = await client.get<ApiFeature[]>(`/layers/${layerId}/features?limit=5000`);
      setLayerStates((prev) =>
        prev.map((l) =>
          l.layer.id === layerId
            ? { ...l, features: res.data, loaded: true, visible: true }
            : l
        )
      );
    }
  }

  // Sync map whenever layer states or editingLayerId change
  useEffect(() => {
    if (!mapReadyRef.current) return;
    layerStates.forEach(syncViewLayer);
  }, [layerStates, syncViewLayer]);

  // ── Start editing a layer ───────────────────────────────────────────────────
  async function startEdit(layerId: string) {
    const draw = drawRef.current;
    if (!draw) return;

    // Clear any previous draw state
    draw.deleteAll();
    setHasChanges(false);

    // Load features if not already loaded
    let features: ApiFeature[] = [];
    const existing = layerStates.find((l) => l.layer.id === layerId);
    if (existing?.loaded) {
      features = existing.features;
    } else {
      const res = await client.get<ApiFeature[]>(`/layers/${layerId}/features?limit=5000`);
      features = res.data;
      setLayerStates((prev) =>
        prev.map((l) =>
          l.layer.id === layerId ? { ...l, features, loaded: true, visible: true } : l
        )
      );
    }

    originalFeaturesRef.current = features;
    setEditingLayerId(layerId);

    // Load into draw tool
    if (features.length > 0) {
      draw.set({ type: "FeatureCollection", features: features.map(toDrawFeature) });

      // Fit map to features
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

  // ── Stop editing ────────────────────────────────────────────────────────────
  function stopEdit() {
    drawRef.current?.deleteAll();
    setEditingLayerId(null);
    setHasChanges(false);
    originalFeaturesRef.current = [];
  }

  // ── Save changes ────────────────────────────────────────────────────────────
  async function saveEdits() {
    const draw = drawRef.current;
    if (!draw || !editingLayerId) return;
    setSaving(true);

    try {
      const drawn = draw.getAll().features;
      const originals = originalFeaturesRef.current;
      const drawnApiIds = new Set(
        drawn.map((f) => f.properties?._api_id).filter((id) => id != null)
      );

      const creates = drawn.filter((f) => !f.properties?._api_id);
      const updates = drawn.filter((f) => f.properties?._api_id != null);
      const deletes = originals.filter((f) => !drawnApiIds.has(f.id));

      await Promise.all([
        ...creates.map((f) =>
          client.post(`/layers/${editingLayerId}/features`, {
            geom: f.geometry,
            properties: omitInternal(f.properties ?? {}),
          })
        ),
        ...updates.map((f) =>
          client.put(`/layers/${editingLayerId}/features/${f.properties!._api_id}`, {
            geom: f.geometry,
            properties: omitInternal(f.properties ?? {}),
            version: f.properties!._api_version,
          })
        ),
        ...deletes.map((f) =>
          client.delete(`/layers/${editingLayerId}/features/${f.id}`)
        ),
      ]);

      message.success(
        `Saved: ${creates.length} created, ${updates.length} updated, ${deletes.length} deleted`
      );

      // Reload features into draw to pick up new IDs/versions
      const res = await client.get<ApiFeature[]>(`/layers/${editingLayerId}/features?limit=5000`);
      originalFeaturesRef.current = res.data;
      draw.set({ type: "FeatureCollection", features: res.data.map(toDrawFeature) });

      setLayerStates((prev) =>
        prev.map((l) =>
          l.layer.id === editingLayerId ? { ...l, features: res.data } : l
        )
      );
      setHasChanges(false);
    } catch {
      message.error("Save failed — check for version conflicts and try again");
    } finally {
      setSaving(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const editingLayer = layerStates.find((l) => l.layer.id === editingLayerId);

  return (
    <div style={{ display: "flex", height: "calc(100vh - 64px)", gap: 0 }}>

      {/* ── Left panel ── */}
      <div style={{
        width: 260,
        flexShrink: 0,
        background: "#fafafa",
        borderRight: "1px solid #f0f0f0",
        display: "flex",
        flexDirection: "column",
        padding: "16px 12px",
        overflowY: "auto",
      }}>
        <Typography.Text strong style={{ marginBottom: 8, display: "block" }}>Database</Typography.Text>
        <Select
          placeholder="Select database"
          style={{ width: "100%", marginBottom: 16 }}
          value={selectedDb || undefined}
          options={databases.map((d) => ({ value: d.id, label: d.name }))}
          onChange={(v) => setSelectedDb(v)}
        />

        {loadingLayers && <Spin size="small" />}

        {layerStates.length > 0 && (
          <>
            <Typography.Text strong style={{ marginBottom: 8, display: "block" }}>Layers</Typography.Text>
            <List
              size="small"
              dataSource={layerStates}
              renderItem={(ls) => {
                const isEditing = ls.layer.id === editingLayerId;
                return (
                  <List.Item
                    style={{
                      padding: "6px 4px",
                      background: isEditing ? "#e6f4ff" : undefined,
                      borderRadius: 4,
                    }}
                  >
                    <Space style={{ width: "100%", justifyContent: "space-between" }}>
                      <Space>
                        <span style={{
                          width: 10, height: 10, borderRadius: "50%",
                          background: ls.color, display: "inline-block", flexShrink: 0,
                        }} />
                        <Typography.Text
                          ellipsis
                          style={{ maxWidth: 120, fontSize: 13 }}
                          title={ls.layer.name}
                        >
                          {ls.layer.name}
                        </Typography.Text>
                      </Space>
                      <Space size={4}>
                        <Tooltip title={ls.visible ? "Hide" : "Show"}>
                          <Button
                            type="text"
                            size="small"
                            icon={ls.visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                            onClick={() => toggleVisible(ls.layer.id)}
                            disabled={isEditing}
                          />
                        </Tooltip>
                        <Tooltip title={isEditing ? "Stop editing" : "Edit"}>
                          <Button
                            type={isEditing ? "primary" : "text"}
                            size="small"
                            icon={isEditing ? <CloseOutlined /> : <EditOutlined />}
                            onClick={() => isEditing ? stopEdit() : startEdit(ls.layer.id)}
                            disabled={!!editingLayerId && !isEditing}
                          />
                        </Tooltip>
                      </Space>
                    </Space>
                  </List.Item>
                );
              }}
            />
          </>
        )}

        {editingLayerId && (
          <>
            <Divider style={{ margin: "12px 0" }} />
            <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
              Editing: <strong>{editingLayer?.layer.name}</strong>
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 11, display: "block", marginBottom: 12 }}>
              Use the toolbar on the map to draw. Click a shape to select and drag to move.
            </Typography.Text>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              block
              loading={saving}
              disabled={!hasChanges}
              onClick={saveEdits}
            >
              Save changes
            </Button>
            {hasChanges && (
              <Tag color="orange" style={{ marginTop: 8, textAlign: "center", width: "100%" }}>
                Unsaved changes
              </Tag>
            )}
          </>
        )}
      </div>

      {/* ── Map ── */}
      <div ref={mapContainer} style={{ flex: 1 }} />
    </div>
  );
}
