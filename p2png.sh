#!/bin/bash
# usage: ./p2png.sh <Input path> <output path>
# convert jpg/jpeg/png/gif/webp to png

IPATH="$1"
OPATH="$2"

if [ ! -f "$IPATH" ]; then
    echo "Error: $IPATH doesn't exist"
    exit 1
fi

if [ ! -d "$(dirname $OPATH)" ]; then
    mkdir -p "$(dirname $OPATH)"
fi

type=$(file --mime-type -b "$IPATH")

case "$type" in
    image/png)
    cp "$IPATH" "$OPATH"
    ;;
    image/jpeg)
    ffmpeg -y -i "$IPATH" -vcodec png -pix_fmt rgba -update 1 "$OPATH"
    ;;
    image/jpg)
    ffmpeg -y -i "$IPATH" -vcodec png -pix_fmt rgba -update 1 "$OPATH"
    ;;
    image/gif)
    ffmpeg -y -i "$IPATH" -vcodec png -pix_fmt rgba -update 1 "$OPATH"
    ;;
    image/webp)
    ffmpeg -y -i "$IPATH" -vframes 1 -vcodec png -pix_fmt rgba -update 1 "$OPATH"
    ;;
    *)
    echo "Unsupported format: $type, skipping."
    ;;
esac