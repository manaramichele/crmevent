#!/usr/bin/env bash
# Converte i fotogrammi in video per la homepage (MP4 H.264 + WebM VP9) e crea l'immagine di anteprima.
set -euo pipefail
cd "$(dirname "$0")"
FF=$(python3 -c "import imageio_ffmpeg as i;print(i.get_ffmpeg_exe())")
DEST=/app/frontend/public/media
mkdir -p "$DEST"
POSTER_FRAME=${POSTER_FRAME:-$(ls frames | wc -l | awk '{printf "%05d", $1-80}')}
"$FF" -y -loglevel error -framerate 25 -i frames/f%05d.jpg -c:v libx264 -preset slow -crf 25 -pix_fmt yuv420p -movflags +faststart -an "$DEST/event-planner-demo.mp4"
"$FF" -y -loglevel error -framerate 25 -i frames/f%05d.jpg -c:v libvpx-vp9 -b:v 0 -crf 38 -row-mt 1 -deadline good -cpu-used 4 -an "$DEST/event-planner-demo.webm"
"$FF" -y -loglevel error -i "frames/f${POSTER_FRAME}.jpg" -q:v 4 "$DEST/event-planner-poster.jpg"
ls -la "$DEST"
