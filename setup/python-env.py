#!/usr/bin/env python3
"""Create the shared venv and install packages declared in python-packages.toml."""

import argparse
from html import escape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
from urllib.error import URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import venv


def read_manifest(path):
    data = tomllib.loads(path.read_text())
    environment = Path(data["environment"]["path"]).expanduser()
    if not environment.is_absolute():
        raise ValueError("environment.path должен быть абсолютным путём или начинаться с ~/.")
    packages = data.get("packages", {})
    requirements = packages.get("requirements", [])
    if not isinstance(requirements, list) or any(
        not isinstance(item, str) or not item.strip() or item.startswith("-")
        for item in requirements
    ):
        raise ValueError("packages.requirements должен быть списком требований pip без флагов.")
    directories = packages.get("wheel_directories", [])
    if not isinstance(directories, list):
        raise ValueError("packages.wheel_directories должен быть списком таблиц.")
    for entry in directories:
        if not isinstance(entry, dict) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", entry.get("name", "")):
            raise ValueError("У каждого wheel_directories должно быть корректное имя пакета name.")
        if not isinstance(entry.get("url"), str) or not entry["url"].strip():
            raise ValueError("У каждого wheel_directories должен быть url каталога.")
        if not isinstance(entry.get("prerelease", False), bool):
            raise ValueError("prerelease должен быть true или false.")
    return environment, requirements, directories


def raw_wheel_url(requirement):
    """Accept GitHub blob links as well as direct wheel download URLs."""
    match = re.fullmatch(r"(?:(.+?)\s+@\s+)?(https://github\.com/\S+)", requirement)
    if not match:
        return requirement
    parsed = urlsplit(match[2])
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 5 and parts[2] == "blob" and parts[-1].endswith(".whl"):
        path = "/" + "/".join(parts[:2] + parts[3:])
        url = urlunsplit(("https", "raw.githubusercontent.com", path, "", parsed.fragment))
        return f"{match[1]} @ {url}" if match[1] else url
    return requirement


def run_pip(interpreter, *args, cwd):
    subprocess.run(
        [str(interpreter), "-I", "-m", "pip", "--disable-pip-version-check", "--no-input", *args],
        cwd=cwd,
        check=True,
    )


def ensure_environment(environment):
    if os.path.lexists(environment):
        if not (environment / "pyvenv.cfg").is_file():
            raise ValueError(f"{environment} уже существует и не является venv; содержимое не изменено.")
    else:
        venv.EnvBuilder(with_pip=True).create(environment)
    interpreter = environment / "bin/python"
    probe = subprocess.run(
        [str(interpreter), "-I", "-c", "import json,sys; print(json.dumps([sys.prefix, sys.base_prefix]))"],
        capture_output=True, text=True, check=True,
    )
    prefix, base_prefix = json.loads(probe.stdout)
    if Path(prefix).resolve() != environment.resolve() or prefix == base_prefix:
        raise ValueError(f"{interpreter} не запускает ожидаемое виртуальное окружение.")
    pip = subprocess.run([str(interpreter), "-I", "-m", "pip", "--version"], capture_output=True)
    if pip.returncode:
        subprocess.run([str(interpreter), "-I", "-m", "ensurepip", "--upgrade"], check=True)
    return interpreter


def directory_links(url, folder, manifest_dir):
    """Turn a GitHub directory listing into a pip-compatible HTML wheel index."""
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.netloc == "github.com":
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 4 or parts[2] not in ("tree", "blob"):
            raise ValueError("Для каталога GitHub используйте URL /tree/BRANCH/path.")
        owner, repo, _, ref, *path = (unquote(part) for part in parts)
        api = (f"https://api.github.com/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
               f"/contents/{quote('/'.join(path), safe='/')}?ref={quote(ref, safe='')}")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "dotfiles-stow-all"}
        if token := os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        with urlopen(Request(api, headers=headers), timeout=30) as response:
            listing = json.load(response)
        if not isinstance(listing, list):
            raise ValueError("URL wheel_directories должен указывать на каталог, а не на файл.")
        urls = [entry["download_url"] for entry in listing
                if entry.get("type") == "file" and entry.get("name", "").endswith(".whl")
                and entry.get("download_url")]
        if not urls:
            raise ValueError(f"В каталоге {url} нет wheel-файлов.")
        index = folder / "wheels.html"
        index.write_text("\n".join(f'<a href="{escape(link, quote=True)}">{escape(link)}</a>' for link in urls))
        return str(index)
    if parsed.scheme:
        if parsed.scheme not in ("https", "http", "file"):
            raise ValueError("Каталог wheel должен быть HTTPS/HTTP/file URL или локальным путём.")
        return url
    return str((manifest_dir / Path(url).expanduser()).resolve())


def latest_wheel(interpreter, entry, manifest_dir):
    # Let pip compare PEP 440 versions and check wheel tags / Requires-Python.
    # --no-index keeps a same-named PyPI package out of this selection.
    with tempfile.TemporaryDirectory(prefix="usamg1t-wheel-") as temp:
        folder = Path(temp)
        links = directory_links(entry["url"], folder, manifest_dir)
        report = folder / "report.json"
        args = ["install", "--dry-run", "--ignore-installed", "--no-deps", "--no-index",
                "--only-binary=:all:", "--find-links", links, "--report", str(report)]
        if entry.get("prerelease", False):
            args.append("--pre")
        run_pip(interpreter, *args, entry["name"], cwd=manifest_dir)
        packages = json.loads(report.read_text())["install"]
        if len(packages) != 1:
            raise ValueError(f"Не удалось однозначно выбрать wheel для {entry['name']}.")
        package = packages[0]
        normalized = lambda name: re.sub(r"[-_.]+", "-", name).lower()
        if normalized(package["metadata"]["name"]) != normalized(entry["name"]):
            raise ValueError("Имя выбранного wheel не совпадает с манифестом.")
        url = package["download_info"]["url"]
        checksum = package["download_info"].get("archive_info", {}).get("hashes", {}).get("sha256")
        if checksum:
            parsed = urlsplit(url)
            url = urlunsplit((*parsed[:4], f"sha256={checksum}"))
        print(f"{entry['name']}: выбрана версия {package['metadata']['version']}", flush=True)
        return f"{entry['name']} @ {url}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Проверить манифест без установки и сетевых запросов")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "python-packages.toml")
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise ValueError("Окружение нужно устанавливать от обычного пользователя, без sudo.")
    manifest = args.manifest.resolve()
    environment, requirements, directories = read_manifest(manifest)
    if args.dry_run:
        state = "проверить" if environment.exists() else "создать"
        print(f"Python: {state} {environment}; требований: {len(requirements)}, каталогов wheel: {len(directories)}.")
        return
    interpreter = ensure_environment(environment)
    resolved = [raw_wheel_url(requirement) for requirement in requirements]
    resolved.extend(latest_wheel(interpreter, entry, manifest.parent) for entry in directories)
    if resolved:
        run_pip(interpreter, "install", *resolved, cwd=manifest.parent)
    run_pip(interpreter, "check", cwd=manifest.parent)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError, URLError) as error:
        print(f"python-env: {error}", file=sys.stderr)
        sys.exit(1)
