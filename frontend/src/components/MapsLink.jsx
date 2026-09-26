import { useEffect, useState } from "react";
import QRCode from "qrcode";

// Maps link + a QR code that is shown only in the printed PDF (print: variant).
export default function MapsLink({ url, label = "Apri in Google Maps", testid = "maps" }) {
  const [qr, setQr] = useState("");
  useEffect(() => {
    if (!url) { setQr(""); return; }
    QRCode.toDataURL(url, { margin: 1, width: 120 }).then(setQr).catch(() => setQr(""));
  }, [url]);
  if (!url) return null;
  return (
    <span className="inline-flex items-center gap-2 align-middle">
      <a href={url} target="_blank" rel="noreferrer" className="text-tiffany-active hover:underline font-medium" data-testid={`${testid}-link`}>📍 {label}</a>
      {qr && <img src={qr} alt="QR Google Maps" className="hidden print:inline-block w-16 h-16" data-testid={`${testid}-qr`} />}
    </span>
  );
}
