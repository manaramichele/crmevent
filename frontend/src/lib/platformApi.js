import axios from "axios";
import { API } from "./api";

// Platform-scope client for CRMEvent OFFICIAL social (Super Admin only).
// Forces ?scope=platform so data is NOT tied to the active org selector (X-Org-Id).
const platformApi = axios.create({ baseURL: API, withCredentials: true });

platformApi.interceptors.request.use((config) => {
  config.params = { ...(config.params || {}), scope: "platform" };
  return config;
});

export default platformApi;
