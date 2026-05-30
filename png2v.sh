#!/bin/bash
# usage: ./png2v.sh <Input path> <output path>
# convert png to png a random seconds mp4 with the highest possible mass and the smallest possible volume

IPATH="$1"
OPATH="$2"

if [ ! -f "$IPATH" ]; then
    echo "Error: $IPATH doesn't exist"
    exit 1
fi

if [ ! -d "$(dirname "$OPATH")" ]; then
    mkdir -p "$(dirname "$OPATH")"
fi

duration=$(awk -v min=1 -v max=5 'BEGIN{srand(); printf "%.3f", min + rand() * (max - min)}')
echo "Converting: $IPATH -> $OPATH"
ffmpeg -y -loop 1 -i "$IPATH" \
    -f lavfi -i anullsrc \
    -c:v libx264 -crf 1 -preset ultrafast -g 114514 -t "$duration" \
    -pix_fmt yuv420p \
    -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
    -shortest "$OPATH"