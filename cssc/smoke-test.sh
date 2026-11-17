#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 NEW_EVIDENCE_DIRECTORY [LOCAL_DOCKER_IMAGE]" >&2
    exit 2
fi

mkdir -- "$1"
cd -- "$1"

verify_copy() {
    printf '%s  %s\n' "$(sha256sum "$1" | cut -d ' ' -f1)" "$2" | sha256sum --check --strict
}

verify_blob() {
    local file=$1 digest=$2 size=$3
    [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ && "$size" =~ ^[0-9]+$ ]]
    printf '%s  %s\n' "${digest#sha256:}" "$file" | sha256sum --check --strict
    [[ $(wc -c < "$file") -eq "$size" ]]
}

finalize_layout() {
    local layout=$1 raw_config=$2 digest size
    jq -e '.schemaVersion == 2 and (.manifests | length) == 1
        and .manifests[0].mediaType == "application/vnd.oci.image.manifest.v1+json"
        and (.manifests[0].size | type) == "number"' "$layout/index.json"
    digest=$(jq -er '.manifests[0].digest' "$layout/index.json")
    size=$(jq -er '.manifests[0].size' "$layout/index.json")
    verify_blob "$layout/blobs/sha256/${digest#sha256:}" "$digest" "$size"
    cp "$layout/blobs/sha256/${digest#sha256:}" "$layout/converted.manifest.json"
    jq -e '.schemaVersion == 2 and .mediaType == "application/vnd.oci.image.manifest.v1+json"
        and .config.mediaType == "application/vnd.oci.image.config.v1+json"
        and (.config.size | type) == "number" and (.layers | type) == "array"' \
        "$layout/converted.manifest.json"
    digest=$(jq -er '.config.digest' "$layout/converted.manifest.json")
    size=$(jq -er '.config.size' "$layout/converted.manifest.json")
    verify_blob "$layout/blobs/sha256/${digest#sha256:}" "$digest" "$size"
    cp "$layout/blobs/sha256/${digest#sha256:}" "$layout/converted.config.json"
    jq -e '.os == "linux" and (.architecture | type == "string" and length > 0)
        and (.config | type) == "object"
        and .rootfs.type == "layers" and (.rootfs.diff_ids | type) == "array"
        and all(.rootfs.diff_ids[]; type == "string" and test("^sha256:[a-f0-9]{64}$"))' "$raw_config"
    jq -e --slurpfile raw "$raw_config" \
        '.os == $raw[0].os and .architecture == $raw[0].architecture and .rootfs == $raw[0].rootfs' \
        "$layout/converted.config.json"

    # Conversion may normalize Docker-only fields; retain the authenticated original bytes.
    digest=sha256:$(sha256sum "$raw_config" | cut -d ' ' -f1)
    size=$(wc -c < "$raw_config")
    cp "$raw_config" "$layout/blobs/sha256/${digest#sha256:}"
    jq --arg digest "$digest" --argjson size "$size" \
        '.config.digest = $digest | .config.size = $size' \
        "$layout/converted.manifest.json" > "$layout/finalized.manifest.json"
    verify_blob "$layout/blobs/sha256/${digest#sha256:}" "$digest" "$size"
    digest=sha256:$(sha256sum "$layout/finalized.manifest.json" | cut -d ' ' -f1)
    size=$(wc -c < "$layout/finalized.manifest.json")
    cp "$layout/finalized.manifest.json" "$layout/blobs/sha256/${digest#sha256:}"
    jq --arg digest "$digest" --argjson size "$size" \
        '.manifests[0].digest = $digest | .manifests[0].size = $size' \
        "$layout/index.json" > "$layout/finalized.index.json"
    mv "$layout/finalized.index.json" "$layout/index.json"
    digest=$(jq -er '.manifests[0].digest' "$layout/index.json")
    size=$(jq -er '.manifests[0].size' "$layout/index.json")
    verify_blob "$layout/finalized.manifest.json" "$digest" "$size"
    verify_copy "$layout/finalized.manifest.json" "$layout/blobs/sha256/${digest#sha256:}"
}

verify_layers() {
    local layout=$1 manifest=$2 config=$3 count i digest size expected actual media_type file
    count=$(jq -er '.layers | length' "$manifest")
    jq -e --argjson count "$count" '.rootfs.diff_ids | length == $count' "$config"
    for ((i = 0; i < count; i++)); do
        digest=$(jq -er --argjson i "$i" '.layers[$i].digest' "$manifest")
        size=$(jq -er --argjson i "$i" '.layers[$i].size | select(type == "number")' "$manifest")
        file="$layout/blobs/sha256/${digest#sha256:}"
        verify_blob "$file" "$digest" "$size"
        expected=$(jq -er --argjson i "$i" '.rootfs.diff_ids[$i]' "$config")
        media_type=$(jq -er --argjson i "$i" '.layers[$i].mediaType' "$manifest")
        case "$media_type" in
            application/vnd.oci.image.layer.v1.tar+gzip)
                actual=$(gzip -dc "$file" | sha256sum | cut -d ' ' -f1) ;;
            application/vnd.oci.image.layer.v1.tar)
                actual=$(sha256sum "$file" | cut -d ' ' -f1) ;;
            *) echo "Unsupported layer media type: $media_type" >&2; return 1 ;;
        esac
        [[ "sha256:$actual" == "$expected" ]]
    done
}

for tool in acr copa oras trivy syft skopeo docker bash jq sha256sum tar gzip; do
    command -v "$tool"
done
acr version > acr-version.txt
acr --help > acr-help.txt
ACR_EXPERIMENTAL_CSSC=true acr cssc --help > acr-cssc-help.txt
copa --version > copa-version.txt
copa patch --help > copa-patch-help.txt
oras version > oras-version.txt
oras repo ls --help > oras-repo-ls-help.txt
oras repo tags --help > oras-repo-tags-help.txt
oras resolve --help > oras-resolve-help.txt
oras attach --help > oras-attach-help.txt
trivy version --format json > trivy-version.json
jq -e '.Version | type == "string" and length > 0' trivy-version.json
trivy image --help > trivy-image-help.txt
syft version -o json > syft-version.json
skopeo --version > skopeo-version.txt
docker --version > docker-version.txt
docker exec --help > docker-exec-help.txt
bash --version > bash-version.txt
jq --version > jq-version.txt
sha256sum --version > sha256sum-version.txt
rpm -qa | sort > rpm-packages.txt

mkdir -p source/layer
printf 'cssc local export fixture\n' > source/layer/retention.txt
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    -cf source/layer.tar -C source/layer .
layer_digest=$(sha256sum source/layer.tar | cut -d ' ' -f1)
jq -cn --arg digest "sha256:$layer_digest" \
    '{architecture:"amd64",os:"linux",config:{Env:["CSSC_RETENTION=unchanged"],
      Labels:{"example.retention":"unchanged"}},
      rootfs:{type:"layers",diff_ids:[$digest]},history:[{created_by:"cssc smoke fixture"}]}' \
    > source/config.json
printf '[{"Config":"config.json","RepoTags":["cssc-smoke:fixture"],"Layers":["layer.tar"]}]\n' \
    > source/manifest.json
tar -cf source.tar -C source config.json manifest.json layer.tar

# The archive path tests conversion without a daemon or a registry.
skopeo copy --format oci "docker-archive:$PWD/source.tar" oci:exported:fixture
finalize_layout exported source/config.json
oras manifest fetch --oci-layout exported:fixture --output manifest.json
verify_layers exported manifest.json source/config.json
config_digest=$(jq -er '.config.digest' manifest.json)
oras blob fetch --oci-layout "exported@$config_digest" --output exported-config.json
verify_copy source/config.json exported-config.json
skopeo inspect --raw --config oci:exported:fixture > inspected-config.json
verify_copy source/config.json inspected-config.json
layer_digest=$(jq -er '.layers[0].digest | sub("^sha256:";"")' manifest.json)
gzip -dc "exported/blobs/sha256/$layer_digest" > exported-layer.tar
verify_copy source/layer.tar exported-layer.tar

# Exercise local ORAS copy with nonempty base and unrelated manifest annotations.
jq '.annotations = ({"org.opencontainers.image.base.name":"example.invalid/base:v1",
    "org.opencontainers.image.base.digest":("sha256:" + ("a" * 64)),
    "example.retention":"unchanged"} + (.annotations // {}))' manifest.json > annotated-manifest.json
manifest_digest=$(sha256sum annotated-manifest.json | cut -d ' ' -f1)
cp annotated-manifest.json "exported/blobs/sha256/$manifest_digest"
jq --arg digest "sha256:$manifest_digest" --argjson size "$(wc -c < annotated-manifest.json)" \
    '.manifests[0].digest = $digest | .manifests[0].size = $size' \
    exported/index.json > annotated-index.json
mv annotated-index.json exported/index.json
oras cp --from-oci-layout --to-oci-layout exported:fixture copied:fixture
oras manifest fetch --oci-layout copied:fixture --output copied-manifest.json
verify_copy annotated-manifest.json copied-manifest.json
verify_layers copied copied-manifest.json source/config.json
oras blob fetch --oci-layout "copied@$config_digest" --output copied-config.json
verify_copy source/config.json copied-config.json

if [[ $# == 2 ]]; then
    image_id=$(docker image inspect --format '{{.Id}}' "$2")
    [[ "$image_id" =~ ^sha256:[a-f0-9]{64}$ ]]
    printf '%s\n' "$image_id" > daemon-image-id.txt
    skopeo inspect --raw --config "docker-daemon:$image_id" > daemon-config.json
    [[ "sha256:$(sha256sum daemon-config.json | cut -d ' ' -f1)" == "$image_id" ]]
    skopeo copy --format oci "docker-daemon:$image_id" oci:daemon-export:patched
    finalize_layout daemon-export daemon-config.json
    oras manifest fetch --oci-layout daemon-export:patched --output daemon-manifest.json
    verify_layers daemon-export daemon-manifest.json daemon-config.json
    digest=$(jq -er '.config.digest' daemon-manifest.json)
    oras blob fetch --oci-layout "daemon-export@$digest" --output daemon-export-config.json
    verify_copy daemon-config.json daemon-export-config.json
    oras cp --from-oci-layout --to-oci-layout daemon-export:patched daemon-copied:patched
    oras manifest fetch --oci-layout daemon-copied:patched --output daemon-copied-manifest.json
    verify_copy daemon-manifest.json daemon-copied-manifest.json
    verify_layers daemon-copied daemon-copied-manifest.json daemon-config.json
    oras blob fetch --oci-layout "daemon-copied@$digest" --output daemon-copied-config.json
    verify_copy daemon-config.json daemon-copied-config.json
fi

echo "Local tool/OCI smoke checks passed; no registry was contacted."
