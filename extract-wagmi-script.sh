#!/bin/sh

# Extract the script src path from an HTML file and update base.html template
# Usage: ./extract-wagmi-script.sh <html-file> <base-html-file> [--dry-run]

DRY_RUN=0
BASE_HTML=""

# Parse arguments
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        *)
            if [ -z "$HTML_FILE" ]; then
                HTML_FILE="$arg"
            elif [ -z "$BASE_HTML" ]; then
                BASE_HTML="$arg"
            fi
            ;;
    esac
done

if [ -z "$HTML_FILE" ] || [ -z "$BASE_HTML" ]; then
    echo "Usage: $0 <html-file> <base-html-file> [--dry-run]"
    exit 1
fi

if [ ! -f "$HTML_FILE" ]; then
    echo "Error: HTML file $HTML_FILE not found"
    exit 1
fi

if [ ! -f "$BASE_HTML" ]; then
    echo "Error: Base HTML file $BASE_HTML not found"
    exit 1
fi

# Extract the script path from the HTML file
SCRIPT_PATH=$(grep -o 'src="[^"]*\.js"' "$HTML_FILE" | sed 's/src="//;s/"//')

if [ -z "$SCRIPT_PATH" ]; then
    echo "Error: No script tag found in $HTML_FILE"
    exit 1
fi

# Extract just the filename from the path (e.g., /assets/index-Co4bq4Ui.js -> index-Co4bq4Ui.js)
JS_FILENAME=$(basename "$SCRIPT_PATH")

if [ $DRY_RUN -eq 1 ]; then
    echo "[DRY RUN] Would replace path after 'filename=' with 'js/$JS_FILENAME' in $BASE_HTML"
else
    # Replace the path after filename= in base.html
    sed -i'' -e "s|filename=['\"]js/[^'\"]*['\"]|filename='js/$JS_FILENAME'|g" "$BASE_HTML"
    echo "Replaced path after 'filename=' with 'js/$JS_FILENAME' in $BASE_HTML"
fi
