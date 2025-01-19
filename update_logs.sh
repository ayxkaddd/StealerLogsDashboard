#!/bin/bash

DIR="/path/to/your/folder"
temp_file=$(mktemp)

echo "[" > "$temp_file"

first=true
for file in "$DIR"/*.txt; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")

        lines=$(wc -l < "$file")

        if [ "$first" = true ]; then
            first=false
        else
            echo "," >> "$temp_file"
        fi

        echo "{
            \"name\": \"$filename\",
            \"lines_count\": $lines,
            \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
        }" >> "$temp_file"
    fi
done

echo "]" >> "$temp_file"

if command -v jq >/dev/null 2>&1; then
    jq '.' "$temp_file" > "$DIR/file_stats_cache.json"
else
    mv "$temp_file" "$DIR/file_stats_cache.json"
fi

rm -f "$temp_file"

echo "File statistics have been updated in file_stats_cache.json"
