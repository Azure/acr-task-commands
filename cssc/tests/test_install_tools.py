import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallToolsTests(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / ".test-work" / self.id().split(".")[-1]
        self.work.mkdir(parents=True)
        self.addCleanup(self.remove_work_root)
        self.addCleanup(shutil.rmtree, self.work)
        self.archive = self.work / "release.tar.gz"
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, content in (
                ("release-cli", b"#!/bin/sh\nprintf 'fixture release\\n'\n"),
                ("LICENSE", b"fixture license\n"),
            ):
                member = tarfile.TarInfo(name)
                member.size = len(content)
                member.mode = 0o755 if name == "release-cli" else 0o644
                member.mtime = 0
                archive.addfile(member, io.BytesIO(content))
        boundary = self.work / "boundary"
        boundary.mkdir()
        curl = boundary / "curl"
        curl.write_text(
            '#!/bin/sh\n'
            '[ "${RELEASE_HTTP_FAILURE:-0}" = 0 ] || exit 22\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  if [ "$1" = "--output" ]; then cp "$RELEASE_RESPONSE" "$2"; exit; fi\n'
            '  shift\n'
            'done\n'
            'exit 1\n'
        )
        curl.chmod(0o755)
        self.env = {
            **os.environ,
            "LC_ALL": "C",
            "PATH": str(boundary) + os.pathsep + os.environ["PATH"],
            "RELEASE_RESPONSE": str(self.archive),
        }

    def remove_work_root(self):
        root = ROOT / ".test-work"
        if root.exists() and not any(root.iterdir()):
            root.rmdir()

    def run_installer(self, checksum):
        lock = self.work / "tools.lock"
        lock.write_text(
            "example release-cli https://github.com/example/tool/releases/download/v1/release.tar.gz "
            + checksum + "\n"
        )
        return subprocess.run(
            ["bash", str(ROOT / "install-tools.sh"), str(lock), str(self.work / "output")],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_verified_release_is_installed_with_its_license(self):
        result = self.run_installer(hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertEqual(result.returncode, 0, result.stderr)
        executable = self.work / "output/bin/example"
        result = subprocess.run([executable], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "fixture release\n")
        self.assertEqual(
            (self.work / "output/licenses/example/LICENSE").read_text(),
            "fixture license\n",
        )

    def test_checksum_mismatch_does_not_install_unverified_content(self):
        result = self.run_installer("0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse((self.work / "output/bin/example").exists())

    def test_download_failure_does_not_install_content(self):
        self.env["RELEASE_HTTP_FAILURE"] = "1"
        result = self.run_installer(hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "output/bin/example").exists())


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.work = ROOT / ".test-work" / self.id().split(".")[-1]
        self.work.mkdir(parents=True)
        self.addCleanup(self.remove_work_root)
        self.addCleanup(shutil.rmtree, self.work)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            content = b"retained layer content\n"
            member = tarfile.TarInfo("retention.txt")
            member.size = len(content)
            member.mtime = 0
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(content))
        layer = buffer.getvalue()
        (self.work / "layer").write_bytes(layer)
        config = {
            "architecture": "amd64",
            "os": "linux",
            "config": {"Labels": {"example.retention": "unchanged"}},
            "container_config": {"preserve": "Docker-specific raw content"},
            "rootfs": {
                "type": "layers",
                "diff_ids": ["sha256:" + hashlib.sha256(layer).hexdigest()],
            },
        }
        self.raw = (json.dumps(config, sort_keys=True) + "\n").encode()
        (self.work / "raw.json").write_bytes(self.raw)
        boundary = self.work / "boundary"
        boundary.mkdir()
        implementation = boundary / "tool"
        implementation.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import gzip
            import hashlib
            import json
            import os
            from pathlib import Path
            import shutil
            import sys
            import tarfile

            name, args = Path(sys.argv[0]).name, sys.argv[1:]
            fixture = Path(os.environ["SMOKE_FIXTURE"])
            def digest(data):
                return "sha256:" + hashlib.sha256(data).hexdigest()
            def blob(layout, data, media_type):
                value = digest(data)
                (layout / "blobs/sha256" / value[7:]).write_bytes(data)
                return {"digest": value, "size": len(data), "mediaType": media_type}
            def manifest(layout):
                descriptor = json.loads((layout / "index.json").read_bytes())["manifests"][0]
                return layout / "blobs/sha256" / descriptor["digest"][7:]
            if "--help" in args:
                print("boundary fixture help")
            elif name == "trivy":
                print('{"Version":"boundary-fixture"}')
            elif name == "docker":
                if args[:2] == ["image", "inspect"]:
                    value = digest((fixture / "raw.json").read_bytes())
                    print("sha256:" + "0" * 64 if os.getenv("WRONG_IMAGE_ID") else value)
                else:
                    print("boundary fixture Docker")
            elif name == "skopeo" and args[0] == "copy":
                source, destination = args[-2:]
                if source.startswith("docker-archive:"):
                    with tarfile.open(source.split(":", 1)[1]) as archive:
                        raw = archive.extractfile("config.json").read()
                        layer = archive.extractfile("layer.tar").read()
                else:
                    raw = (fixture / "raw.json").read_bytes()
                    layer = (fixture / "layer").read_bytes()
                    if os.getenv("WRONG_LAYER"):
                        layer += b"unexpected content"
                converted = json.loads(raw)
                converted.pop("container_config", None)
                layout = Path(destination.split(":")[1])
                (layout / "blobs/sha256").mkdir(parents=True)
                config = blob(layout, json.dumps(converted).encode(),
                              "application/vnd.oci.image.config.v1+json")
                layer = blob(layout, gzip.compress(layer, mtime=0),
                             "application/vnd.oci.image.layer.v1.tar+gzip")
                image = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                         "config": config, "layers": [layer],
                         "annotations": {"example.converted": "preserve",
                                         "org.opencontainers.image.base.name": "example.invalid/original:v2",
                                         "org.opencontainers.image.base.digest": "sha256:" + "b" * 64}}
                if os.getenv("WRONG_BLOB"):
                    (layout / "blobs/sha256" / layer["digest"][7:]).write_bytes(b"corrupted")
                descriptor = blob(layout, json.dumps(image).encode(), image["mediaType"])
                descriptor["annotations"] = {"org.opencontainers.image.ref.name":
                                             destination.rsplit(":", 1)[1]}
                if os.getenv("WRONG_DESCRIPTOR"):
                    descriptor["size"] += 1
                (layout / "index.json").write_text(json.dumps({"schemaVersion": 2,
                                                               "manifests": [descriptor]}))
                (layout / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
            elif name == "skopeo" and args[0] == "inspect":
                source = args[-1]
                if source.startswith("docker-daemon:"):
                    data = (fixture / "raw.json").read_bytes()
                else:
                    layout = Path(source.split(":")[1])
                    descriptor = json.loads(manifest(layout).read_bytes())["config"]
                    data = (layout / "blobs/sha256" / descriptor["digest"][7:]).read_bytes()
                sys.stdout.buffer.write(data)
            elif name == "oras" and args[0] == "cp":
                source, target = args[-2:]
                shutil.copytree(source.split(":")[0], target.split(":")[0])
            elif name == "oras" and args[1:2] == ["fetch"]:
                reference = args[args.index("--oci-layout") + 1]
                if args[0] == "manifest":
                    path = manifest(Path(reference.split(":")[0]))
                else:
                    layout, value = reference.split("@")
                    path = Path(layout) / "blobs/sha256" / value[7:]
                Path(args[args.index("--output") + 1]).write_bytes(path.read_bytes())
            else:
                print("boundary fixture version")
            """))
        implementation.chmod(0o755)
        for tool in ("acr", "copa", "oras", "trivy", "syft", "skopeo", "docker", "rpm"):
            (boundary / tool).symlink_to("tool")
        self.env = {
            **os.environ,
            "LC_ALL": "C",
            "PATH": str(boundary) + os.pathsep + os.environ["PATH"],
            "SMOKE_FIXTURE": str(self.work),
        }

    def remove_work_root(self):
        root = ROOT / ".test-work"
        if root.exists() and not any(root.iterdir()):
            root.rmdir()

    def run_smoke(self):
        return subprocess.run(
            ["bash", str(ROOT / "smoke-test.sh"), str(self.work / "run"), "fixture:patched"],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_smoke_restores_raw_config_after_conversion(self):
        result = self.run_smoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = self.work / "run"
        self.assertEqual((evidence / "daemon-export-config.json").read_bytes(), self.raw)
        self.assertEqual((evidence / "daemon-copied-config.json").read_bytes(), self.raw)
        self.assertEqual(
            (evidence / "daemon-manifest.json").read_bytes(),
            (evidence / "daemon-copied-manifest.json").read_bytes(),
        )
        self.assertEqual(
            (evidence / "copied-config.json").read_bytes(),
            (evidence / "source/config.json").read_bytes(),
        )
        manifest = json.loads((evidence / "daemon-manifest.json").read_bytes())
        self.assertEqual(manifest["annotations"]["example.converted"], "preserve")
        for path in ("daemon-manifest.json", "copied-manifest.json"):
            annotations = json.loads((evidence / path).read_bytes())["annotations"]
            self.assertEqual(annotations["org.opencontainers.image.base.name"], "example.invalid/original:v2")
            self.assertEqual(annotations["org.opencontainers.image.base.digest"], "sha256:" + "b" * 64)

    def test_smoke_rejects_raw_config_not_matching_docker_image_id(self):
        self.env["WRONG_IMAGE_ID"] = "1"
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.work / "run/daemon-config.json").exists())
        self.assertFalse((self.work / "run/daemon-export").exists())

    def test_smoke_rejects_layer_not_matching_raw_diffid(self):
        self.env["WRONG_LAYER"] = "1"
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.work / "run/daemon-manifest.json").exists())
        self.assertFalse((self.work / "run/daemon-export-config.json").exists())

    def test_smoke_rejects_corrupted_layer_blob(self):
        self.env["WRONG_BLOB"] = "1"
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse((self.work / "run/exported-config.json").exists())

    def test_smoke_rejects_invalid_manifest_descriptor_size(self):
        self.env["WRONG_DESCRIPTOR"] = "1"
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.work / "run/exported-config.json").exists())


if __name__ == "__main__":
    unittest.main()
