import client from "./client";
import type { Permission } from "../types";

export const permissions = {
  list: (params: Record<string, string>) =>
    client.get<Permission[]>("/permissions", { params }).then((r) => r.data),
  grant: (data: Partial<Permission>) =>
    client.post<Permission>("/permissions", data).then((r) => r.data),
  revoke: (id: string) => client.delete(`/permissions/${id}`),
};
