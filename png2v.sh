#!/bin/bash
# usage: ./png2v.sh <Input dir> <output dir>
# convert jpg/jpeg/png to a 1s mp4 with the highest possible mass and the smallest possible volume

IMGDIR="$1"
OUTDIR="$2"

if [ ! -d "$IMGDIR" ]; then
    echo "Error: $IMGDIR doesn't exist"
    exit 1
fi

mkdir -p "$OUTDIR"

for img in "$IMGDIR"/*.png; do
    name=$(basename "$img" .png)
    output="$OUTDIR/${name}.mp4"
    duration=$(awk -v min=1 -v max=5 'BEGIN{srand(); printf "%.3f", min + rand() * (max - min)}') 
    echo "Converting: $img -> $output"
    ffmpeg -y -loop 1 -i "$img" \
        -f lavfi -i anullsrc \
        -c:v libx264 -crf 1 -preset ultrafast -g 114514 -t $duration \
        -pix_fmt yuv420p \
        -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
        -shortest "$output"
done
