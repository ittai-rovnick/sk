import client from "./client";
import type {
  GeoMap, MapGroup, MapOpenResponse, MapFreshnessResponse,
  LayerStats,
} from "../types";

export const mapsApi = {
  list: (databaseId: string) =>
    client.get<GeoMap[]>(`/maps?database_id=${databaseId}`).then((r) => r.data),

  create: (data: { name: string; description?: string; database_id: string }) =>
    client.post<GeoMap>("/maps", data).then((r) => r.data),

  get: (id: string) => client.get<GeoMap>(`/maps/${id}`).then((r) => r.data),

  update: (id: string, data: Partial<Pick<GeoMap, "name" | "description">>) =>
    client.put<GeoMap>(`/maps/${id}`, data).then((r) => r.data),

  delete: (id: string) => client.delete(`/maps/${id}`),

  open: (id: string, etag?: string) =>
    client.get<MapOpenResponse>(`/maps/${id}/open`, {
      headers: etag ? { "If-None-Match": etag } : undefined,
      // 304 should NOT raise
      validateStatus: (s) => s === 200 || s === 304,
    }),

  freshness: (id: string, sinceISO: string) =>
    client
      .get<MapFreshnessResponse>(`/maps/${id}/freshness?since=${encodeURIComponent(sinceISO)}`)
      .then((r) => r.data),

  // ── Groups ──────────────────────────────────────────────────────────────────
  listGroups: (mapId: string) =>
    client.get<MapGroup[]>(`/maps/${mapId}/groups`).then((r) => r.data),

  createGroup: (mapId: string, data: {
    name: string;
    parent_id?: string | null;
    embedded_map_id?: string | null;
    sort_order?: number;
  }) => client.post<MapGroup>(`/maps/${mapId}/groups`, data).then((r) => r.data),

  updateGroup: (mapId: string, groupId: string, data: {
    name?: string;
    parent_id?: string | null;
    sort_order?: number;
    is_expanded?: boolean;
  }) => client.put<MapGroup>(`/maps/${mapId}/groups/${groupId}`, data).then((r) => r.data),

  deleteGroup: (mapId: string, groupId: string) =>
    client.delete(`/maps/${mapId}/groups/${groupId}`),

  // ── Layer membership ────────────────────────────────────────────────────────
  addLayer: (mapId: string, data: {
    layer_id: string;
    group_id?: string | null;
    sort_order?: number;
    filter_expression?: object | null;
  }) => client.post(`/maps/${mapId}/layers`, data).then((r) => r.data),

  removeLayer: (mapId: string, layerId: string) =>
    client.delete(`/maps/${mapId}/layers/${layerId}`),

  updateLayer: (mapId: string, layerId: string, data: {
    group_id?: string | null;
    sort_order?: number;
    is_visible?: boolean;
    filter_expression?: object | null;
  }) => client.put(`/maps/${mapId}/layers/${layerId}`, data).then((r) => r.data),

  // ── Bulk group permission grant ─────────────────────────────────────────────
  grantGroupPermissions: (mapId: string, groupId: string, data: {
    ms_user_id?: string;
    ms_group_id?: string;
    role_id: string;
    allow?: boolean;
  }) => client.post(`/maps/${mapId}/groups/${groupId}/permissions`, data).then((r) => r.data),
};

// ── Export URL helper (auth via Bearer interceptor; for window.open() use direct API call instead) ──

export function layerExportUrl(layerId: string, format: "geojson" | "shapefile" | "gpkg", srid?: number): string {
  const base = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8000";
  const qs = new URLSearchParams({ format });
  if (srid !== undefined) qs.set("srid", String(srid));
  return `${base}/layers/${layerId}/export?${qs.toString()}`;
}

// Trigger an authenticated download (axios → blob → temporary anchor)
export async function downloadLayerExport(
  layerId: string,
  format: "geojson" | "shapefile" | "gpkg",
  srid?: number,
  filename?: string,
): Promise<void> {
  const params: Record<string, string | number> = { format };
  if (srid !== undefined) params.srid = srid;
  const res = await client.get(`/layers/${layerId}/export`, {
    params,
    responseType: "blob",
  });
  const blob = res.data as Blob;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename ?? `layer-${layerId}.${format === "shapefile" ? "zip" : format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Stats ──────────────────────────────────────────────────────────────────────

export const layerStatsApi = {
  get: (layerId: string) =>
    client.get<LayerStats>(`/layers/${layerId}/stats`).then((r) => r.data),
};
