#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# != 2 ]]; then
    echo "Usage: $0 TOOLS_LOCK OUTPUT_DIRECTORY" >&2
    exit 2
fi

lock=$1
output=$2
mkdir .tool-downloads
trap 'rm -rf -- .tool-downloads' EXIT
mkdir -p "$output/bin" "$output/licenses"

while read -r tool member url checksum; do
    [[ -n "$tool" && "$tool" != \#* ]] || continue
    archive=.tool-downloads/release.tar.gz
    curl --fail --show-error --silent --location --retry 5 \
        --proto '=https' --proto-redir '=https' --output "$archive" "$url"
    printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --strict
    tar -xzf "$archive" -C .tool-downloads -- "$member" LICENSE
    install -m 0755 ".tool-downloads/$member" "$output/bin/$tool"
    mkdir -p "$output/licenses/$tool"
    install -m 0644 .tool-downloads/LICENSE "$output/licenses/$tool/LICENSE"
    rm -- "$archive" ".tool-downloads/$member" .tool-downloads/LICENSE
done < "$lock"
