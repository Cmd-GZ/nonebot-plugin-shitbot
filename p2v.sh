#!/bin/bash
# usage: ./p2v.sh <Input dir> <output dir>
# convert jpg/jpeg/png to a 1s mp4 with the highest possible mass and the smallest possible volume

IMGDIR="$1"
OUTDIR="$2"

if [ ! -d "$IMGDIR" ]; then
    echo "Error: $IMGDIR doesn't exist"
    exit 1
fi

mkdir -p "$OUTDIR"

# handle all the pictures in the $IMGDIR with filename dictionary sorting order
shopt -s nullglob
for rawfile in "$IMGDIR"/*; do
    [ -f "$rawfile" ] || continue
    mime=$(file --mime-type -b "$rawfile")
    pngfile="${rawfile}.png"

    case "$mime" in
        image/png)
	    mv "$rawfile" "$pngfile"
	    ;;
	image/jpeg)
	    ffmpeg -y -i "$rawfile" -vcodec png -pix_fmt rgba -update 1 "$pngfile"
	    rm "$rawfile"
	    ;;
	image/gif)
	    ffmpeg -y -i "$rawfile" -vframes 1 -vcodec png -update 1 "$pngfile"
	    rm "$rawfile"
	    ;;
	*)
	    echo "Unsupported format: $mime, skipping."
	    rm "$rawfile"
	    ;;
    esac
done

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
