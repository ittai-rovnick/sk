import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Typography, Space, Button, Spin, Descriptions, Tag, Badge, Alert,
  Tabs, Collapse, Table, Card, Dropdown, Popconfirm, message, Empty,
} from "antd";
import {
  ArrowLeftOutlined, DownloadOutlined, RollbackOutlined,
  HistoryOutlined, BarChartOutlined, EnvironmentOutlined,
} from "@ant-design/icons";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import client from "../api/client";
import { layers as layersApi } from "../api/layers";
import { downloadLayerExport, layerStatsApi } from "../api/maps";
import type {
  Layer, LayerStats, FieldStat,
  VersionListItem, VersionDetail,
} from "../types";

interface Feature {
  id: number;
  layer_id: string;
  geom: GeoJSON.Geometry;
  properties: Record<string, unknown>;
  version: number;
}

const STATUS_COLOR: Record<string, string> = { draft: "default", review: "orange", published: "green" };
const HEALTH_COLOR: Record<string, string> = { ok: "success", stale: "warning", error: "error", syncing: "processing" };

export function LayerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<maplibregl.Map | null>(null);

  const [layer, setLayer] = useState<Layer | null>(null);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [loadingLayer, setLoadingLayer] = useState(true);
  const [loadingFeatures, setLoadingFeatures] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Stats
  const [stats, setStats] = useState<LayerStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsLoaded, setStatsLoaded] = useState(false);

  // Versions
  const [versions, setVersions] = useState<VersionListItem[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<VersionDetail | null>(null);

  useEffect(() => {
    if (!id) return;
    client.get<Layer>(`/layers/${id}`)
      .then((r) => setLayer(r.data))
      .catch(() => setError("Layer not found"))
      .finally(() => setLoadingLayer(false));

    client.get<Feature[]>(`/layers/${id}/features?limit=5000`)
      .then((r) => setFeatures(r.data))
      .catch(() => setError("Failed to load features"))
      .finally(() => setLoadingFeatures(false));
  }, [id]);

  // Init map
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    mapInstance.current = new maplibregl.Map({
      container: mapRef.current,
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

    mapInstance.current.addControl(new maplibregl.NavigationControl(), "top-right");

    return () => {
      mapInstance.current?.remove();
      mapInstance.current = null;
    };
  }, []);

  // Add features to map
  useEffect(() => {
    const map = mapInstance.current;
    if (!map || loadingFeatures || features.length === 0) return;

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: features.map((f) => ({
        type: "Feature",
        geometry: f.geom,
        properties: { id: f.id, ...f.properties },
      })),
    };

    function addFeatures() {
      if (!map) return;
      if (map.getSource("features")) {
        (map.getSource("features") as maplibregl.GeoJSONSource).setData(geojson);
        return;
      }
      map.addSource("features", { type: "geojson", data: geojson });
      map.addLayer({ id: "features-circle", type: "circle", source: "features",
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-radius": 6, "circle-color": "#1677ff", "circle-stroke-width": 1.5, "circle-stroke-color": "#fff" } });
      map.addLayer({ id: "features-line", type: "line", source: "features",
        filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
        paint: { "line-color": "#1677ff", "line-width": 2 } });
      map.addLayer({ id: "features-fill", type: "fill", source: "features",
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "fill-color": "#1677ff", "fill-opacity": 0.3 } });
      map.addLayer({ id: "features-outline", type: "line", source: "features",
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "line-color": "#1677ff", "line-width": 1.5 } });

      (["features-circle", "features-fill"] as const).forEach((layerId) => {
        map.on("click", layerId, (e) => {
          if (!e.features?.[0]) return;
          const props = e.features[0].properties ?? {};
          const html = Object.entries(props).map(([k, v]) => `<b>${k}:</b> ${v}`).join("<br/>") || "(no properties)";
          new maplibregl.Popup().setLngLat(e.lngLat).setHTML(html).addTo(map);
        });
        map.on("mouseenter", layerId, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", layerId, () => { map.getCanvas().style.cursor = ""; });
      });

      // Prefer the layer's own bbox, fall back to features
      try {
        if (layer?.bbox) {
          map.fitBounds(
            [[layer.bbox[0], layer.bbox[1]], [layer.bbox[2], layer.bbox[3]]],
            { padding: 60, maxZoom: 14, animate: false }
          );
        } else {
          const allCoords: [number, number][] = [];
          features.forEach((f) => {
            if (f.geom.type === "Point") allCoords.push(f.geom.coordinates as [number, number]);
            if (f.geom.type === "LineString") allCoords.push(...(f.geom.coordinates as [number, number][]));
          });
          if (allCoords.length > 0) {
            const lngs = allCoords.map((c) => c[0]);
            const lats = allCoords.map((c) => c[1]);
            map.fitBounds(
              [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
              { padding: 60, maxZoom: 14 }
            );
          }
        }
      } catch {
        // ignore
      }
    }

    if (map.loaded()) addFeatures();
    else map.on("load", addFeatures);
  }, [features, loadingFeatures, layer]);

  // ── Stats (lazy) ───────────────────────────────────────────────────────────
  async function loadStats() {
    if (!id || statsLoaded || statsLoading) return;
    setStatsLoading(true);
    try {
      const s = await layerStatsApi.get(id);
      setStats(s);
      setStatsLoaded(true);
    } catch {
      message.error("Failed to load stats");
    } finally {
      setStatsLoading(false);
    }
  }

  // ── Versions (lazy) ────────────────────────────────────────────────────────
  async function loadVersions() {
    if (!id) return;
    setVersionsLoading(true);
    try {
      const rows = await layersApi.versions.list(id);
      setVersions(rows);
    } catch {
      message.error("Failed to load versions");
    } finally {
      setVersionsLoading(false);
    }
  }

  async function viewVersion(v: VersionListItem) {
    if (!id) return;
    try {
      const detail = await layersApi.versions.get(id, v.version);
      setSelectedVersion(detail);
    } catch {
      message.error("Failed to load version detail");
    }
  }

  async function restoreVersion(v: VersionListItem) {
    if (!id) return;
    try {
      const result = await layersApi.versions.restore(id, v.version);
      message.success(`Restored — new version v${result.version}`);
      // Reload layer + versions
      const fresh = await layersApi.get(id);
      setLayer(fresh);
      loadVersions();
      setSelectedVersion(null);
    } catch {
      message.error("Restore failed");
    }
  }

  // ── Export ─────────────────────────────────────────────────────────────────
  async function doExport(format: "geojson" | "shapefile" | "gpkg") {
    if (!id || !layer) return;
    try {
      await downloadLayerExport(id, format, undefined, `${layer.name}.${format === "shapefile" ? "zip" : format}`);
    } catch {
      message.error(`Export failed: ${format}`);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  if (loadingLayer) return <Spin style={{ display: "block", marginTop: 80 }} />;
  if (error) return <Alert type="error" message={error} />;
  if (!layer) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 64px)" }}>
      <Space style={{ padding: "12px 0", flexShrink: 0 }} wrap>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>Back</Button>
        <Typography.Title level={4} style={{ margin: 0 }}>{layer.name}</Typography.Title>
        <Tag color={STATUS_COLOR[layer.status]}>{layer.status}</Tag>
        <Badge status={HEALTH_COLOR[layer.health] as never} text={layer.health} />
        {layer.is_locked && <Tag color="orange">Locked</Tag>}

        <Dropdown
          menu={{
            items: [
              { key: "geojson",   label: "GeoJSON",     onClick: () => doExport("geojson") },
              { key: "shapefile", label: "Shapefile",   onClick: () => doExport("shapefile") },
              { key: "gpkg",      label: "GeoPackage",  onClick: () => doExport("gpkg") },
            ],
          }}
          trigger={["click"]}
        >
          <Button icon={<DownloadOutlined />}>Export ▾</Button>
        </Dropdown>
      </Space>

      <Descriptions size="small" column={4} style={{ flexShrink: 0, marginBottom: 12 }}>
        <Descriptions.Item label="Geometry">
          {layer.geometry_types?.length
            ? <Space size={2} wrap>{layer.geometry_types.map((t) => <Tag key={t}>{t}</Tag>)}</Space>
            : <Tag color="default">empty</Tag>
          }
        </Descriptions.Item>
        <Descriptions.Item label="SRID">{layer.srid}</Descriptions.Item>
        <Descriptions.Item label="Features">{loadingFeatures ? "…" : features.length}</Descriptions.Item>
        <Descriptions.Item label="Shard">{layer.shard_id}</Descriptions.Item>
      </Descriptions>

      <Tabs
        defaultActiveKey="map"
        style={{ flexShrink: 0 }}
        onChange={(k) => {
          if (k === "stats") loadStats();
          if (k === "versions") loadVersions();
        }}
        items={[
          {
            key: "map",
            label: <span><EnvironmentOutlined /> Map</span>,
            children: (
              <div ref={mapRef} style={{ height: "calc(100vh - 320px)", borderRadius: 8, overflow: "hidden" }} />
            ),
          },
          {
            key: "stats",
            label: <span><BarChartOutlined /> Stats</span>,
            children: (
              <StatsPanel
                stats={stats}
                loading={statsLoading}
                onReload={() => { setStatsLoaded(false); loadStats(); }}
              />
            ),
          },
          {
            key: "versions",
            label: <span><HistoryOutlined /> Versions</span>,
            children: (
              <VersionsPanel
                versions={versions}
                loading={versionsLoading}
                selected={selectedVersion}
                onView={viewVersion}
                onRestore={restoreVersion}
                onClose={() => setSelectedVersion(null)}
              />
            ),
          },
        ]}
      />
    </div>
  );
}

// ── Stats panel ────────────────────────────────────────────────────────────────

function StatsPanel({
  stats, loading, onReload,
}: {
  stats: LayerStats | null;
  loading: boolean;
  onReload: () => void;
}) {
  if (loading) return <Spin style={{ display: "block", marginTop: 40 }} />;
  if (!stats) return <Empty description="No stats yet" />;

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button size="small" onClick={onReload}>Reload</Button>
      </Space>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space size="large" wrap>
          <Descriptions size="small" column={1} style={{ minWidth: 200 }}>
            <Descriptions.Item label="Total features">
              <Typography.Text strong>{stats.total_count.toLocaleString()}</Typography.Text>
            </Descriptions.Item>
          </Descriptions>
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>Geometry types</Typography.Text>
            <div>
              {Object.keys(stats.geometry_type_counts).length === 0 && <Tag>none</Tag>}
              {Object.entries(stats.geometry_type_counts).map(([t, c]) => (
                <Tag key={t} color="blue">{t}: {c}</Tag>
              ))}
            </div>
          </div>
        </Space>
      </Card>

      <Collapse
        defaultActiveKey={Object.keys(stats.field_stats).length > 0 ? ["fields"] : []}
        items={[{
          key: "fields",
          label: `Field statistics (${Object.keys(stats.field_stats).length})`,
          children: (
            <Table
              size="small"
              pagination={false}
              rowKey="name"
              dataSource={Object.entries(stats.field_stats).map(([name, fs]) => ({ name, fs }))}
              columns={[
                { title: "Field", dataIndex: "name", key: "name", render: (n: string) => <Typography.Text strong>{n}</Typography.Text> },
                { title: "Type",  dataIndex: "fs",   key: "type", render: (fs: FieldStat) => <Tag>{fs.type}</Tag> },
                {
                  title: "Stats",
                  dataIndex: "fs",
                  key: "stats",
                  render: (fs: FieldStat) => renderFieldStat(fs),
                },
              ]}
            />
          ),
        }]}
      />
    </div>
  );
}

function renderFieldStat(fs: FieldStat) {
  if ("error" in fs && fs.error) {
    return <Tag color="red">error: {fs.error}</Tag>;
  }
  // The fallback `{ type: string; error? }` variant breaks discriminated-union
  // narrowing on `type`, so cast explicitly per branch.
  if (fs.type === "string") {
    const s = fs as Extract<FieldStat, { type: "string" }>;
    return (
      <Space size={4} wrap>
        <Tag>nulls: {s.null_count}</Tag>
        <Tag>unique: {s.unique_count}</Tag>
        {s.top_values.slice(0, 5).map((v) => (
          <Tag key={String(v.value)} color="default">{String(v.value)} × {v.count}</Tag>
        ))}
        {s.top_values.length > 5 && <Tag>+ more</Tag>}
      </Space>
    );
  }
  if (fs.type === "number") {
    const n = fs as Extract<FieldStat, { type: "number" }>;
    return (
      <Space size={4} wrap>
        <Tag>min: {fmtNum(n.min)}</Tag>
        <Tag>max: {fmtNum(n.max)}</Tag>
        <Tag>avg: {fmtNum(n.avg)}</Tag>
        <Tag>nulls: {n.null_count}</Tag>
      </Space>
    );
  }
  if (fs.type === "boolean") {
    const b = fs as Extract<FieldStat, { type: "boolean" }>;
    return (
      <Space size={4} wrap>
        <Tag color="green">true: {b.true_count}</Tag>
        <Tag color="red">false: {b.false_count}</Tag>
        <Tag>nulls: {b.null_count}</Tag>
      </Space>
    );
  }
  return <Tag>—</Tag>;
}

function fmtNum(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(3);
}

// ── Versions panel ─────────────────────────────────────────────────────────────

function VersionsPanel({
  versions, loading, selected, onView, onRestore, onClose,
}: {
  versions: VersionListItem[];
  loading: boolean;
  selected: VersionDetail | null;
  onView: (v: VersionListItem) => void;
  onRestore: (v: VersionListItem) => void;
  onClose: () => void;
}) {
  if (loading) return <Spin style={{ display: "block", marginTop: 40 }} />;

  return (
    <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 1fr" : "1fr", gap: 12 }}>
      <Card size="small" title={`Versions (${versions.length})`}>
        {versions.length === 0 && <Empty description="No history yet" />}
        <Table
          size="small"
          rowKey="id"
          pagination={{ pageSize: 25 }}
          dataSource={versions}
          columns={[
            {
              title: "Ver",
              dataIndex: "version",
              key: "version",
              width: 60,
              render: (v: number) => <Tag color="blue">v{v}</Tag>,
            },
            {
              title: "Changed fields",
              dataIndex: "changed_fields",
              key: "changed_fields",
              render: (fs: string[]) => fs?.length
                ? <Space size={2} wrap>{fs.map((f) => <Tag key={f}>{f}</Tag>)}</Space>
                : <span style={{ color: "#bfbfbf" }}>—</span>,
            },
            {
              title: "When",
              dataIndex: "changed_at",
              key: "when",
              width: 170,
              render: (v: string) => new Date(v).toLocaleString(),
            },
            {
              title: "",
              key: "actions",
              width: 160,
              render: (_: unknown, row: VersionListItem) => (
                <Space>
                  <Button size="small" onClick={() => onView(row)}>View</Button>
                  <Popconfirm
                    title={`Restore v${row.version}?`}
                    okText="Restore"
                    onConfirm={() => onRestore(row)}
                  >
                    <Button size="small" danger icon={<RollbackOutlined />}>Restore</Button>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      {selected && (
        <Card
          size="small"
          title={`Snapshot — v${selected.version}`}
          extra={<Button size="small" onClick={onClose}>Close</Button>}
        >
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="When">{new Date(selected.changed_at).toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label="Message">{selected.message ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="Changed fields">
              {selected.changed_fields?.length
                ? <Space size={2} wrap>{selected.changed_fields.map((f) => <Tag key={f}>{f}</Tag>)}</Space>
                : "—"}
            </Descriptions.Item>
          </Descriptions>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginTop: 8 }}>Snapshot</Typography.Text>
          <pre style={{
            background: "#fafafa", padding: 8, borderRadius: 4,
            maxHeight: 360, overflow: "auto", fontSize: 11, marginTop: 4,
          }}>
            {JSON.stringify(selected.snapshot, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
}
