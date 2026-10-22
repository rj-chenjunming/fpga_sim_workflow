"""Offline delivery boundaries: corrupt resources and incompatible hosts fail early."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "spikes/browser_offline.py"


@pytest.fixture
def offline():
    spec = importlib.util.spec_from_file_location("browser_offline", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_corrupt_resource_rejected(offline, tmp_path):
    file = tmp_path / "package.whl"
    content = b"expected wheel"
    file.write_bytes(content)
    manifest = {"files": {file.name: {"sha256": hashlib.sha256(content).hexdigest(),
                                     "bytes": len(content)}}}
    offline.verify_bundle(tmp_path, manifest)
    file.write_bytes(b"tampered wheel")
    with pytest.raises(RuntimeError, match="SHA-256|size"):
        offline.verify_bundle(tmp_path, manifest)


def test_rocky_compatibility_floor(offline):
    offline.check_platform(system="Linux", machine="x86_64", python_version=(3, 11), libc="2.28")
    with pytest.raises(RuntimeError, match="glibc"):
        offline.check_platform(system="Linux", machine="x86_64", python_version=(3, 11), libc="2.17")
    with pytest.raises(RuntimeError, match="CPython"):
        offline.check_platform(system="Linux", machine="x86_64", python_version=(3, 10), libc="2.28")
    with pytest.raises(RuntimeError, match="x86_64"):
        offline.check_platform(system="Linux", machine="aarch64", python_version=(3, 11), libc="2.28")


def archive(path, members):
    with tarfile.open(path, "w:xz") as tar:
        for name, kind in members:
            item = tarfile.TarInfo(name)
            item.mode = 0o755
            if kind == "symlink":
                item.type = tarfile.SYMTYPE
                item.linkname = "/etc/passwd"
                tar.addfile(item)
            else:
                item.size = 1
                tar.addfile(item, io.BytesIO(b"x"))


@pytest.mark.parametrize("bad", ["../../outside", "opt/google/chrome/../../../../outside"])
def test_archive_escape_never_publishes_cache(offline, tmp_path, bad):
    source = tmp_path / "runtime.tar.xz"
    archive(source, [("opt/google/chrome/chrome", "file"), (bad, "file")])
    target = tmp_path / "cache"
    with pytest.raises(RuntimeError, match="unsafe"):
        offline.extract_runtime(source, target)
    assert not target.exists()
    assert not (tmp_path / "outside").exists()


def test_archive_symlink_rejected(offline, tmp_path):
    source = tmp_path / "runtime.tar.xz"
    archive(source, [("opt/google/chrome/chrome", "symlink")])
    with pytest.raises(RuntimeError, match="link|type"):
        offline.extract_runtime(source, tmp_path / "cache")


def test_extract_does_not_install_system_files(offline, tmp_path):
    source = tmp_path / "runtime.tar.xz"
    archive(source, [("opt/google/chrome/chrome", "file"), ("etc/cron.daily/chrome", "file")])
    target = tmp_path / "cache"
    offline.extract_runtime(source, target)
    assert (target / "chrome").read_bytes() == b"x"
    assert not (target / "etc").exists()


def test_invalid_explicit_browser_does_not_fall_back(offline, tmp_path):
    with pytest.raises(RuntimeError, match="explicit"):
        offline.system_browser(str(tmp_path / "missing"))
