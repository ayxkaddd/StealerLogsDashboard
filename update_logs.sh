#!/bin/bash

DIR="/path/to/your/folder"
temp_file=$(mktemp)
cache_file="file_stats_cache.json"

get_file_timestamp() {
    local file="$1"
    if stat -c %W "$file" >/dev/null 2>&1; then
        timestamp=$(stat -c %W "$file")
    else
        timestamp=$(stat -c %Y "$file")
    fi
    date -u -d "@$timestamp" +"%Y-%m-%dT%H:%M:%SZ"
}

is_file_processed() {
    local filename="$1"
    local timestamp="$2"

    if [ -f "$cache_file" ]; then
        jq -e ".[] | select(.name == \"$filename\" and .timestamp == \"$timestamp\")" "$cache_file" >/dev/null 2>&1
        return $?
    fi
    return 1
}

if [ ! -f "$cache_file" ]; then
    echo "[]" > "$cache_file"
fi

echo "[" > "$temp_file"

first=true
for file in "$DIR"/*.txt; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        timestamp=$(get_file_timestamp "$file")

        if is_file_processed "$filename" "$timestamp"; then
            echo "Skipping $filename - already processed"
            continue
        fi

        lines=$(wc -l < "$file")

        if [ "$first" = true ]; then
            first=false
        else
            echo "," >> "$temp_file"
        fi

        echo "{
            \"name\": \"$filename\",
            \"lines_count\": $lines,
            \"timestamp\": \"$timestamp\"
        }" >> "$temp_file"

        echo "Processed $filename"
    fi
done

if [ "$first" = true ]; then
    echo "No new files to process"
    rm -f "$temp_file"
    exit 0
fi

echo "]" >> "$temp_file"

if command -v jq >/dev/null 2>&1; then
    jq -s '.[0] + .[1] | unique_by(.name)' "$cache_file" "$temp_file" > "${temp_file}.merged"
    mv "${temp_file}.merged" "$cache_file"
else
    echo "Warning: jq is not installed. JSON formatting and merging skipped."
    mv "$temp_file" "$cache_file"
fi

rm -f "$temp_file"

echo "File statistics have been updated in file_stats_cache.json"
