#/bin/sh
OUTPUT_FILE=$1
FRAMERATE=6
ffmpeg -framerate $FRAMERATE -i cube-%03d.png -c:v libx264 -crf 18 -pix_fmt yuv420p $OUTPUT_FILE
