import axios from "axios";
import { msalInstance, loginRequest } from "../auth/msalConfig";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

client.interceptors.request.use(async (config) => {
  const account = msalInstance.getActiveAccount();
  if (account) {
    const result = await msalInstance.acquireTokenSilent({
      ...loginRequest,
      account,
    });
    config.headers.Authorization = `Bearer ${result.accessToken}`;
  }
  return config;
});

export default client;
