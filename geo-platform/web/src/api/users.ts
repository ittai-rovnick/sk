import client from "./client";
import type { User } from "../types";

export const users = {
  me: () => client.get<User>("/auth/me").then((r) => r.data),
  list: () => client.get<User[]>("/users").then((r) => r.data),
  get: (id: string) => client.get<User>(`/users/${id}`).then((r) => r.data),
  deactivate: (id: string) => client.post(`/users/${id}/deactivate`),
};
