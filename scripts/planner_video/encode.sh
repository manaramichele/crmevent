#!/usr/bin/env bash
# Converte i fotogrammi in video (MP4 H.264 + WebM VP9) e crea l'anteprima.
# Uso: FRAMES=frames OUT_NAME=event-planner-demo POSTER_FRAME=00800 bash encode.sh
set -euo pipefail
cd "$(dirname "$0")"
FF=$(python3 -c "import imageio_ffmpeg as i;print(i.get_ffmpeg_exe())")
DEST=/app/frontend/public/media
FRAMES=${FRAMES:-frames}
OUT_NAME=${OUT_NAME:-event-planner-demo}
mkdir -p "$DEST"
POSTER_FRAME=${POSTER_FRAME:-$(ls "$FRAMES" | wc -l | awk '{printf "%05d", $1-80}')}
"$FF" -y -loglevel error -framerate 25 -i "$FRAMES/f%05d.jpg" -c:v libx264 -preset slow -crf 25 -pix_fmt yuv420p -movflags +faststart -an "$DEST/$OUT_NAME.mp4"
"$FF" -y -loglevel error -framerate 25 -i "$FRAMES/f%05d.jpg" -c:v libvpx-vp9 -b:v 0 -crf 38 -row-mt 1 -deadline good -cpu-used 4 -an "$DEST/$OUT_NAME.webm"
"$FF" -y -loglevel error -i "$FRAMES/f${POSTER_FRAME}.jpg" -q:v 4 "$DEST/$OUT_NAME-poster.jpg"
ls -la "$DEST"
