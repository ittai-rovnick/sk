import client from "./client";
import type {
  GroupLayer, Layer,
  LayerIdentifyResponse,
  VersionListItem, VersionDetail,
  SavedExpressionListItem, SavedExpressionDetail,
} from "../types";

export const groupLayers = {
  tree: (databaseId: string) =>
    client.get<GroupLayer[]>(`/group-layers?database_id=${databaseId}`).then((r) => r.data),
  create: (data: Partial<GroupLayer>) =>
    client.post<GroupLayer>("/group-layers", data).then((r) => r.data),
  update: (id: string, data: Partial<GroupLayer>) =>
    client.put<GroupLayer>(`/group-layers/${id}`, data).then((r) => r.data),
  delete: (id: string) => client.delete(`/group-layers/${id}`),
};

export const layers = {
  list: (databaseId: string) =>
    client.get<Layer[]>(`/layers?database_id=${databaseId}`).then((r) => r.data),
  get: (id: string) => client.get<Layer>(`/layers/${id}`).then((r) => r.data),
  create: (data: Partial<Layer>) =>
    client.post<Layer>("/layers", data).then((r) => r.data),
  update: (id: string, data: Partial<Layer>) =>
    client.put<Layer>(`/layers/${id}`, data).then((r) => r.data),
  delete: (id: string) => client.delete(`/layers/${id}`),
  lock: (id: string, reason?: string) =>
    client.post<Layer>(`/layers/${id}/lock`, { reason }).then((r) => r.data),
  unlock: (id: string) =>
    client.post<Layer>(`/layers/${id}/unlock`).then((r) => r.data),

  // POST /layers/identify — registered before /{layer_id} on the server
  identify: (databaseId: string, geometry: object) =>
    client
      .post<LayerIdentifyResponse>("/layers/identify", {
        database_id: databaseId,
        geometry,
      })
      .then((r) => r.data),

  // ── Versions ────────────────────────────────────────────────────────────────
  versions: {
    list: (layerId: string, limit = 50, offset = 0) =>
      client
        .get<VersionListItem[]>(`/layers/${layerId}/versions?limit=${limit}&offset=${offset}`)
        .then((r) => r.data),
    get: (layerId: string, version: number) =>
      client.get<VersionDetail>(`/layers/${layerId}/versions/${version}`).then((r) => r.data),
    restore: (layerId: string, version: number) =>
      client
        .post<{ version: number; message: string }>(`/layers/${layerId}/versions/${version}/restore`)
        .then((r) => r.data),
  },

  // ── Saved Expressions (DSL filter library) ──────────────────────────────────
  expressions: {
    list: (layerId: string) =>
      client.get<SavedExpressionListItem[]>(`/layers/${layerId}/expressions`).then((r) => r.data),
    get: (layerId: string, exprId: string) =>
      client.get<SavedExpressionDetail>(`/layers/${layerId}/expressions/${exprId}`).then((r) => r.data),
    create: (layerId: string, data: { name: string; description?: string; expression: object }) =>
      client.post<SavedExpressionDetail>(`/layers/${layerId}/expressions`, data).then((r) => r.data),
    update: (layerId: string, exprId: string, data: { name?: string; description?: string; expression?: object }) =>
      client.put<SavedExpressionDetail>(`/layers/${layerId}/expressions/${exprId}`, data).then((r) => r.data),
    delete: (layerId: string, exprId: string) =>
      client.delete(`/layers/${layerId}/expressions/${exprId}`),
  },
};
