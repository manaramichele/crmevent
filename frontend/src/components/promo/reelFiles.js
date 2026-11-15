import { useEffect, useState } from "react";
import api, { API } from "@/lib/api";

const isApi = (u) => u && u.startsWith("/api/");

export async function downloadFile(url, name) {
  const a = document.createElement("a");
  if (isApi(url)) {
    const r = await api.get(url.replace(/^\/api/, ""), { responseType: "blob" });
    a.href = URL.createObjectURL(r.data);
  } else {
    a.href = url;
  }
  a.download = name;
  a.click();
}

export function useFileUrl(url) {
  const [src, setSrc] = useState(isApi(url) ? null : url);
  useEffect(() => {
    if (!isApi(url)) { setSrc(url); return undefined; }
    let obj;
    api.get(url.replace(/^\/api/, ""), { responseType: "blob" }).then((r) => { obj = URL.createObjectURL(r.data); setSrc(obj); }).catch(() => setSrc(null));
    return () => { if (obj) URL.revokeObjectURL(obj); };
  }, [url]);
  return src;
}

export const absUrl = (u) => (isApi(u) ? `${API}${u.slice(4)}` : u);
