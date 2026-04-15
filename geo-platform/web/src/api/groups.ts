import client from "./client";

export const groups = {
  list: () => client.get("/groups").then((r) => r.data),
  get: (id: string) => client.get(`/groups/${id}`).then((r) => r.data),
  sync: () => client.post("/groups/sync").then((r) => r.data),
};
