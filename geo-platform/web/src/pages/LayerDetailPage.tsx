import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Typography, Space, Button, Spin, Descriptions, Tag, Badge, Alert } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import client from "../api/client";
import type { Layer } from "../types";

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

      map.addLayer({
        id: "features-circle",
        type: "circle",
        source: "features",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 6,
          "circle-color": "#1677ff",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#fff",
        },
      });

      map.addLayer({
        id: "features-line",
        type: "line",
        source: "features",
        filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
        paint: { "line-color": "#1677ff", "line-width": 2 },
      });

      map.addLayer({
        id: "features-fill",
        type: "fill",
        source: "features",
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "fill-color": "#1677ff", "fill-opacity": 0.3 },
      });

      map.addLayer({
        id: "features-outline",
        type: "line",
        source: "features",
        filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
        paint: { "line-color": "#1677ff", "line-width": 1.5 },
      });

      // Popups on click
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

      // Fit to features
      try {
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
      } catch {
        // ignore fit errors for edge cases
      }
    }

    if (map.loaded()) addFeatures();
    else map.on("load", addFeatures);
  }, [features, loadingFeatures]);

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
      </Space>

      <Descriptions size="small" column={4} style={{ flexShrink: 0, marginBottom: 12 }}>
        <Descriptions.Item label="Geometry">{layer.geometry_type}</Descriptions.Item>
        <Descriptions.Item label="SRID">{layer.srid}</Descriptions.Item>
        <Descriptions.Item label="Features">{loadingFeatures ? "…" : features.length}</Descriptions.Item>
        <Descriptions.Item label="Shard">{layer.shard_id}</Descriptions.Item>
      </Descriptions>

      <div ref={mapRef} style={{ flex: 1, borderRadius: 8, overflow: "hidden" }} />
    </div>
  );
}
