#!/usr/bin/env python3
"""Install/check/run browser checks from Git resources without network access."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

LOOP = Path(__file__).resolve().parents[1]
BUNDLE = LOOP / "offline/browser-linux-x86_64"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(data)
    return value.hexdigest()


def verify_bundle(root, manifest):
    root = Path(root).resolve()
    for name, entry in manifest["files"].items():
        target = root / name
        if not target.resolve().is_relative_to(root) or not target.is_file():
            raise RuntimeError(f"missing/unsafe bundle file: {name}")
        if target.stat().st_size != entry["bytes"]:
            raise RuntimeError(f"bundle size mismatch: {name}")
        if digest(target) != entry["sha256"]:
            raise RuntimeError(f"bundle SHA-256 mismatch: {name}")


def check_platform(*, system=None, machine=None, python_version=None, libc=None):
    system = system or platform.system()
    machine = machine or platform.machine()
    version = python_version or sys.version_info[:2]
    if system != "Linux" or machine != "x86_64":
        raise RuntimeError("offline bundle requires Linux x86_64")
    if platform.python_implementation() != "CPython" or tuple(version) not in ((3, 11), (3, 12)):
        raise RuntimeError("offline bundle requires CPython 3.11 or 3.12")
    if libc is None:
        libc = platform.libc_ver()[1]
    try:
        glibc = tuple(int(item) for item in libc.split(".")[:2])
    except (ValueError, AttributeError):
        raise RuntimeError("cannot determine glibc; requires glibc >= 2.28") from None
    if glibc < (2, 28):
        raise RuntimeError(f"requires glibc >= 2.28, got {libc}")


def extract_runtime(archive, destination):
    """Only publish Chrome files after all members have been checked/extracted."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"cache destination already exists: {destination}")
    with tempfile.TemporaryDirectory(prefix="chrome-extract-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "runtime"
        stage.mkdir()
        with tarfile.open(archive, "r:*") as stream:
            for item in stream:
                relative = PurePosixPath(item.name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise RuntimeError(f"unsafe archive path: {item.name}")
                if relative.parts[:3] != ("opt", "google", "chrome"):
                    continue  # Never install cron jobs, system symlinks or RPM/dpkg metadata.
                if len(relative.parts) == 3:
                    continue
                if not (item.isdir() or item.isfile()):
                    raise RuntimeError(f"archive link/type not allowed: {item.name}")
                target = stage.joinpath(*relative.parts[3:])
                if item.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with stream.extractfile(item) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(0o755 if item.mode & 0o111 else 0o644)
        if not (stage / "chrome").is_file():
            raise RuntimeError("archive has no Chrome executable")
        stage.rename(destination)


def system_browser(explicit=None):
    if explicit:
        candidate = Path(explicit).expanduser().absolute()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise RuntimeError(f"invalid explicit browser executable: {explicit}")
        return candidate
    for command in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(command)
        if found:
            return Path(found)
    return None


def bundled_browser(root, manifest, cache):
    cache = Path(cache) / manifest["id"]
    target = cache / "chrome"
    marker = cache / ".bundle-sha256"
    archive_hash = manifest["browser"]["sha256"]
    if target.is_file() and marker.is_file() and marker.read_text().strip() == archive_hash:
        return target
    if cache.exists():
        raise RuntimeError(f"incomplete/unrecognized cache, inspect or remove it before retry: {cache}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chrome-join-", dir=cache.parent) as temporary:
        archive = Path(temporary) / "runtime.tar.xz"
        with archive.open("wb") as output:
            for name in manifest["browser"]["parts"]:
                with (root / name).open("rb") as source:
                    shutil.copyfileobj(source, output)
        if digest(archive) != archive_hash:
            raise RuntimeError("joined browser archive SHA-256 mismatch")
        extract_runtime(archive, cache)
    marker.write_text(archive_hash + "\n")
    return target


def smoke(executable):
    from playwright.sync_api import sync_playwright

    # Report missing host libraries before the less specific browser launch error.
    if shutil.which("ldd"):
        result = subprocess.run(["ldd", str(executable)], capture_output=True, text=True)
        missing = [line.strip() for line in result.stdout.splitlines() if "not found" in line]
        if missing:
            raise RuntimeError("missing host libraries (use Rocky 8 RPMs): " + "; ".join(missing))
    with sync_playwright() as driver:
        with driver.chromium.launch(executable_path=str(executable), headless=True) as browser:
            page = browser.new_page()
            page.set_content("<title>offline-browser-check</title><h1>离线浏览器验证</h1>")
            if page.title() != "offline-browser-check" or page.locator("h1").inner_text() != "离线浏览器验证":
                raise RuntimeError("local browser smoke assertion failed")
            print(f"PASS: local browser smoke; version={browser.version}; executable={executable}")


def run_tests(executable):
    import pytest

    class Results:
        skipped = 0
        collected = 0

        def pytest_collection_finish(self, session):
            self.collected = len(session.items)

        def pytest_runtest_logreport(self, report):
            if report.skipped:
                self.skipped += 1

        def pytest_collectreport(self, report):
            if report.skipped:
                self.skipped += 1

    os.environ["LOOP_BROWSER_EXECUTABLE"] = str(executable)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    os.chdir(LOOP)
    results = Results()
    code = pytest.main(["tests/browser", "-q"], plugins=[results])
    if code == 0 and (not results.collected or results.skipped):
        print("FAIL: browser validation had no tests or included skips", file=sys.stderr)
        return 2
    return int(code)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "check", "run", "verify"))
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--cache-root", type=Path, default=LOOP / ".browser-cache")
    parser.add_argument("--executable", default=os.environ.get("LOOP_BROWSER_EXECUTABLE"))
    parser.add_argument("--bundled", action="store_true", help="force the version shipped in Git")
    args = parser.parse_args(argv)
    if args.bundled and args.executable:
        parser.error("--bundled cannot be combined with --executable / LOOP_BROWSER_EXECUTABLE")
    root = args.bundle.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    check_platform()
    verify_bundle(root, manifest)
    print("PASS: offline bundle platform and SHA-256 verification", flush=True)
    if args.action == "verify":
        return 0
    if args.action == "install":
        lock = root / f"requirements-cp{sys.version_info.major}{sys.version_info.minor}.lock"
        subprocess.run([sys.executable, "-m", "pip", "--isolated", "install", "--no-index",
                        "--find-links", str(root / "wheels"), "--only-binary=:all:",
                        "--require-hashes", "--no-deps", "--no-cache-dir",
                        "--disable-pip-version-check", "-r", str(lock)], check=True)
    for name, expected in manifest["python_packages"].items():
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise RuntimeError(f"{name} version {actual} != {expected}; run install first")
    executable = None if args.bundled else system_browser(args.executable)
    if executable is None:
        executable = bundled_browser(root, manifest, args.cache_root.resolve())
    smoke(executable)
    return run_tests(executable) if args.action == "run" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
