#!/bin/sh

# Extract script src and CSS href from HTML file, update base.html, and merge CSS into main.css
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

# Extract the CSS path from the HTML file
CSS_PATH=$(grep -o 'href="[^"]*\.css"' "$HTML_FILE" | sed 's/href="//;s/"//' | head -1)

if [ -z "$CSS_PATH" ]; then
    echo "Warning: No CSS link found in $HTML_FILE"
fi

# Extract just the filenames from the paths
JS_FILENAME=$(basename "$SCRIPT_PATH")
CSS_FILENAME=$(basename "$CSS_PATH")

if [ $DRY_RUN -eq 1 ]; then
    echo "[DRY RUN] Would replace JS path with 'js/$JS_FILENAME' in $BASE_HTML"
    if [ -n "$CSS_FILENAME" ]; then
        echo "[DRY RUN] Would merge CSS from $(dirname "$HTML_FILE")/css/$CSS_FILENAME into app/static/css/main.css"
    fi
else
    # Replace the JS path in base.html
    sed -i'' -e "s|filename=['\"]js/[^'\"]*['\"]|filename='js/$JS_FILENAME'|g" "$BASE_HTML"
    echo "✓ Replaced JS path with 'js/$JS_FILENAME' in $BASE_HTML"

    # Merge CSS into main.css
    if [ -n "$CSS_FILENAME" ]; then
        HTML_DIR=$(dirname "$HTML_FILE")
        GENERATED_CSS="$HTML_DIR/css/$CSS_FILENAME"
        MAIN_CSS="app/static/css/main.css"

        if [ -f "$GENERATED_CSS" ]; then
            echo "✓ Merging CSS from $GENERATED_CSS into $MAIN_CSS..."

            # Determine the correct path for merge-css.py
            # In Docker context, it's in ./app/, otherwise it's in current directory
            if [ -f "./app/merge-css.py" ]; then
                python3 ./app/merge-css.py "$GENERATED_CSS" "$MAIN_CSS"
            else
                python3 ./merge-css.py "$GENERATED_CSS" "$MAIN_CSS"
            fi
        else
            echo "Warning: Generated CSS file not found: $GENERATED_CSS"
        fi
    fi
fi
