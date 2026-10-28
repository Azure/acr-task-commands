# cssc

This Linux/amd64 image supplies the command-line tools used by the cssc workflows.

## Building

Build from this directory using an available Docker daemon:

```sh
docker build --platform linux/amd64 --tag cssc:local .
```

The base is the digest-pinned Azure Linux 3.0 `acr-cli:0.21` image.
[tools.lock](./tools.lock) pins official release archives and their SHA-256 checksums:

- Copa 0.15.0, including single-platform Docker output, report-driven patching and OpenVEX output.
- ORAS 1.3.6, including local OCI layout copy, manifest fetch and blob fetch.
- Trivy 0.76.1.
- Syft 1.55.0.

`acr` is retained from the pinned official base. Its current `acr version` output has empty version/revision fields;
do not replace that observation with the base tag when reporting runtime versions.
The base binary embeds Go 1.26.10, whereas the separate 0.21 release archive embeds the older Go 1.26.0.
Retaining the maintained base avoids that compiler downgrade while preserving `acr --help` and `acr cssc`.

The Dockerfile installs signed Azure Linux packages without changing repository, TLS or signature policies.
Skopeo uses the maintained Azure Linux `1.14.4-15.azl3` package, not upstream 1.24.1:
upstream does not publish a Linux binary archive, and the distro package supplies compatible libraries and
security backports without a custom source rebuild.
Azure Linux 3.0 uses `docker-cli` (`25.0.7-6.azl3`) rather than the old `moby-cli` package.
The image only needs a client for the external Task Docker daemon; it does not install a daemon or containerd.
Base packages receive normal distro updates during the build. The resulting RPM inventory is `/app/rpm-packages.txt`;
release inputs are retained at `/app/tools.lock`, and release licenses are under `/usr/share/licenses/cssc`.
The inventory and actual tool versions, not just these input pins, belong in candidate validation evidence.

## Validation

Run the offline installer tests and shell syntax checks from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s cssc/tests -v
for script in cssc/install-tools.sh cssc/smoke-test.sh cssc/docker-entrypoint.sh; do
  bash -n "$script" || exit
done
```

After building, run the real tools and a local Docker-archive-to-OCI/ORAS round trip without contacting a registry:

```sh
mkdir -p evidence
docker run --rm --volume "$PWD/evidence:/evidence" \
  cssc:local cssc-smoke-test /evidence/run-001
```

The evidence directory passed to `cssc-smoke-test` must not exist yet.
Conversion may normalize Docker config fields. Before checking preservation, the smoke restores the original raw
config blob and finalizes its config, manifest and index descriptors locally.
It verifies descriptor hashes/sizes, raw config identity, actual uncompressed layers against source diffIDs,
and exact ORAS copying of a manifest with nonempty fixture base/unrelated annotations.
It records actual versions and checks the existing command help surfaces.
`acr cssc` still requires the existing `ACR_EXPERIMENTAL_CSSC=true` opt-in.

To additionally check the production local-Docker export transport, use an existing local image and a trusted daemon:

```sh
docker run --rm --volume "$PWD/evidence:/evidence" \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  cssc:local cssc-smoke-test /evidence/run-002 local-patched-image:tag
```

The export interface is `skopeo copy --format oci docker-daemon:IMAGE oci:DIRECTORY:TAG`.
The optional daemon check resolves the image ID first, uses that immutable ID for raw-config capture/conversion,
and requires the captured config's SHA-256 to match the Docker image ID before finalization.
Use `skopeo inspect --raw --config docker-daemon:IMAGE_ID` for source config bytes.
Copa's `--oci-dir` is a multi-platform feature; this does not claim native single-platform Copa OCI output.
The service remains responsible for preserving genuine source annotations, finalizing the actual manifest
and publishing it.

These checks do not replace an actual candidate build, full unfiltered vulnerability scan/SBOM,
Copa patch/VEX execution, running BuildKit version capture through `docker exec`,
or the integrated Task preservation/publication tests.
No candidate security or release acceptance follows from offline tests or CLI help alone.

## Usage

Refer to [acb.yaml](./acb.yaml) for the existing build/push workflow.
