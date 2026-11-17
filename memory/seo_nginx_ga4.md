# nginx crmevent.it — SEO (da applicare sul server Aruba)

```nginx
server {
    listen 443 ssl http2;
    server_name www.crmevent.it;
    # ssl_certificate ... (come il blocco esistente)
    return 301 https://crmevent.it$request_uri;
}

# nel server { server_name crmevent.it; ... } esistente:
location / {
    try_files $uri $uri/index.html /index.html;
}
gzip_static on;
gzip on;
gzip_types text/css application/javascript text/javascript application/json image/svg+xml application/xml;
```
Poi: `sudo nginx -t && sudo systemctl reload nginx`.

GA4 (Admin → Impostazioni dati → Gruppi di canali → Crea nuovo gruppo): canale "Assistenti AI" con condizione
Sorgente sessione corrisponde a regex `.*(chatgpt|openai|perplexity|gemini\.google|copilot\.microsoft|claude\.ai).*`, posizionato sopra "Referral".
L'app invia anche l'evento `ai_assistant_visit` (parametro `ai_assistant`): registrarlo come dimensione personalizzata a livello evento.
