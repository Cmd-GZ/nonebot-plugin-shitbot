#!/bin/bash
# usage: ./png2fr.sh <Input path> <Output path>
# add a random-width white border to a png image

IPATH="$1"
OPATH="$2"

if [ ! -f "$IPATH" ]; then
    echo "Error: $IPATH doesn't exist"
    exit 1
fi

if [ ! -d "$(dirname "$OPATH")" ]; then
    mkdir -p "$(dirname "$OPATH")"
fi

border=$(awk -v min=10 -v max=50 'BEGIN{srand(); printf "%.0f", min + rand() * (max - min)}')
echo "Adding border (${border}px) to: $IPATH -> $OPATH"
ffmpeg -i "$IPATH" -vf "pad=iw+${border}:ih+${border}:(ow-iw)/2:(oh-ih)/2:black" -update 1 "$OPATH"
