import client from "./client";
import type { GroupLayer, Layer } from "../types";

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
};
