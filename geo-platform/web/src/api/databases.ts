import client from "./client";
import type { GeoDatabase } from "../types";

export const databases = {
  list: () => client.get<GeoDatabase[]>("/databases").then((r) => r.data),
  get: (id: string) => client.get<GeoDatabase>(`/databases/${id}`).then((r) => r.data),
  create: (data: Partial<GeoDatabase>) =>
    client.post<GeoDatabase>("/databases", data).then((r) => r.data),
  update: (id: string, data: Partial<GeoDatabase>) =>
    client.put<GeoDatabase>(`/databases/${id}`, data).then((r) => r.data),
  delete: (id: string) => client.delete(`/databases/${id}`),
};
