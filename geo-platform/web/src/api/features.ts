import client from "./client";

export const features = {
  list: (layerId: string, params?: Record<string, unknown>) =>
    client.get(`/features`, { params: { layer_id: layerId, ...params } }).then((r) => r.data),
  get: (layerId: string, featureId: number) =>
    client.get(`/features/${featureId}?layer_id=${layerId}`).then((r) => r.data),
  create: (layerId: string, data: unknown) =>
    client.post(`/features?layer_id=${layerId}`, data).then((r) => r.data),
  update: (layerId: string, featureId: number, data: unknown) =>
    client.put(`/features/${featureId}?layer_id=${layerId}`, data).then((r) => r.data),
  delete: (layerId: string, featureId: number) =>
    client.delete(`/features/${featureId}?layer_id=${layerId}`),
};
