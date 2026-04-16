import client from "./client";
import type { User } from "../types";

export const auth = {
  login: (username: string) =>
    client.post<{ token: string; user: User }>("/auth/login", { username }).then((r) => r.data),
  me: () =>
    client.get<User>("/auth/me").then((r) => r.data),
};
