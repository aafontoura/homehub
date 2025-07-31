#!/usr/bin/env python3
"""
docker_versions_report.py

Reports, for each RUNNING Docker container:
- Image and installed version (tag)
- Most recent stable version available (numeric, not 'latest')
- Time gap (days) between the installed tag's update date and the newest stable tag's update date

Logging:
- Configure with --log-level (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- Use --json-logs for JSON-formatted logs on stderr
- Use --log-file to also write logs to a file

Requirements:
    pip install docker requests packaging
"""

import argparse
import csv
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests
from packaging.version import Version, InvalidVersion

try:
    import docker  # type: ignore
except Exception:
    docker = None

LOG = logging.getLogger("docker_versions_report")
HTTP_TIMEOUT = 15  # seconds
HUB_TAGS_URL = "https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags/?page_size=100"
STABLE_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+){0,3})$")  # 1, 1.2, 1.2.3, 1.2.3.4; optional leading v


# -------- Logging setup --------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str, json_logs: bool, log_file: Optional[str]) -> None:
    level_value = getattr(logging, level.upper(), logging.INFO)
    LOG.setLevel(level_value)
    root = logging.getLogger()
    root.setLevel(level_value)

    # Clear any existing handlers (useful when re-running in notebooks)
    for h in list(root.handlers):
        root.removeHandler(h)

    stderr_handler = logging.StreamHandler(sys.stderr)
    if json_logs:
        stderr_handler.setFormatter(JsonFormatter())
    else:
        fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
        datefmt = "%Y-%m-%dT%H:%M:%S%z"
        stderr_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    root.addHandler(stderr_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        if json_logs:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(file_handler)


# -------- Helpers --------
def run(cmd: List[str]) -> Tuple[int, str, str]:
    LOG.debug("Running command: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate()
        LOG.debug("Command exited with %s", proc.returncode)
        if err.strip():
            LOG.debug("Command stderr: %s", err.strip())
        return proc.returncode, out, err
    except FileNotFoundError:
        LOG.error("Command not found: %s", cmd[0])
        return 127, "", f"{cmd[0]} not found"
    except Exception as e:
        LOG.exception("Failed to run command: %s", e)
        return 1, "", str(e)


def normalize_image_ref(image: str) -> Tuple[str, str, str, str]:
    """
    Return (registry, namespace, repo, tag)
    Defaults to docker.io/library and tag=latest.
    """
    LOG.debug("Normalizing image ref: %s", image)
    tag = "latest"

    if ":" in image and "/" in image.split(":")[-2]:
        name_part, tag = image.rsplit(":", 1)
    elif ":" in image and "/" not in image:
        name_part, tag = image.rsplit(":", 1)
    else:
        name_part = image

    parts = name_part.split("/")

    if len(parts) == 1:
        registry = "docker.io"
        namespace = "library"
        repo = parts[0]
    elif len(parts) == 2:
        if "." in parts[0] or ":" in parts[0]:
            registry = parts[0]
            namespace = "library"
            repo = parts[1]
        else:
            registry = "docker.io"
            namespace, repo = parts
    else:
        if "." in parts[0] or ":" in parts[0]:
            registry = parts[0]
            namespace = parts[1]
            repo = "/".join(parts[2:])
        else:
            registry = "docker.io"
            namespace = parts[0]
            repo = "/".join(parts[1:])

    LOG.debug("Parsed image -> registry=%s namespace=%s repo=%s tag=%s", registry, namespace, repo, tag)
    return registry, namespace, repo, tag


def is_stable_numeric_tag(tag: str) -> Optional[Version]:
    m = STABLE_VERSION_RE.match(tag.strip())
    if not m:
        return None
    norm = tag.lstrip("v")
    try:
        return Version(norm)
    except InvalidVersion:
        LOG.debug("Tag not a valid version after normalization: %s", tag)
        return None


def fetch_docker_hub_tags(namespace: str, repo: str) -> List[Dict]:
    url = HUB_TAGS_URL.format(namespace=namespace, repo=repo)
    tags: List[Dict] = []
    page = 1
    while url:
        LOG.debug("Fetching Docker Hub tags: %s (page %s)", url, page)
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT)
        except Exception:
            LOG.exception("HTTP error contacting Docker Hub")
            break
        if r.status_code != 200:
            LOG.warning("Docker Hub returned %s for %s", r.status_code, url)
            break
        data = r.json()
        results = data.get("results", [])
        tags.extend(results)
        url = data.get("next")
        page += 1
    LOG.info("Fetched %d tags for %s/%s from Docker Hub", len(tags), namespace, repo)
    return tags


def fetch_registry_v2_tags(registry: str, full_name: str) -> List[str]:
    url = f"https://{registry}/v2/{full_name}/tags/list"
    LOG.debug("Fetching Registry V2 tag list: %s", url)
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            tags = data.get("tags") or []
            LOG.info("Fetched %d tags from %s", len(tags), registry)
            return tags
        LOG.warning("Registry %s returned %s for tag list", registry, r.status_code)
    except Exception:
        LOG.exception("Error fetching tags from registry %s", registry)
    return []


def parse_iso8601(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    for fmt in ("fromiso", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            if fmt == "fromiso":
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    LOG.debug("Unable to parse datetime: %s", dt_str)
    return None


def newest_stable_from_hub(namespace: str, repo: str) -> Tuple[Optional[str], Optional[datetime]]:
    tags = fetch_docker_hub_tags(namespace, repo)
    candidates: List[Tuple[Version, str, Optional[datetime]]] = []
    for t in tags:
        name = t.get("name") or ""
        ver = is_stable_numeric_tag(name)
        if not ver:
            continue
        last_updated = parse_iso8601(t.get("last_updated"))
        candidates.append((ver, name, last_updated))

    if not candidates:
        LOG.warning("No stable numeric tags found on Docker Hub for %s/%s", namespace, repo)
        return None, None

    candidates.sort(key=lambda x: x[0])
    best = candidates[-1]
    LOG.info("Newest stable tag for %s/%s is %s", namespace, repo, best[1])
    return best[1], best[2]


def installed_tag_date_from_hub(namespace: str, repo: str, tag_name: str) -> Optional[datetime]:
    tags = fetch_docker_hub_tags(namespace, repo)
    for t in tags:
        if (t.get("name") or "") == tag_name:
            dt = parse_iso8601(t.get("last_updated"))
            LOG.debug("Installed tag %s last_updated=%s", tag_name, dt)
            return dt
    LOG.debug("Installed tag %s not found on Docker Hub for %s/%s", tag_name, namespace, repo)
    return None


def get_running_containers() -> List[Dict]:
    containers: List[Dict] = []
    if docker is not None:
        try:
            client = docker.from_env()
            LOG.debug("Listing containers via Docker SDK")
            for c in client.containers.list():  # running only
                image_ref = c.attrs.get("Config", {}).get("Image") or ""
                if not image_ref:
                    tags = list(c.image.tags or [])
                    image_ref = tags[0] if tags else ""
                containers.append({"name": c.name, "image_ref": image_ref})
            LOG.info("Found %d running containers (SDK)", len(containers))
            return containers
        except Exception:
            LOG.exception("Docker SDK failed; falling back to CLI")

    LOG.debug("Listing containers via Docker CLI")
    rc, out, err = run(["docker", "ps", "--format", "{{.Names}}|{{.Image}}"])
    if rc != 0:
        LOG.error("Failed to run 'docker ps' (rc=%s). Ensure Docker is available.", rc)
        sys.exit(2)

    for line in out.strip().splitlines():
        if not line.strip():
            continue
        try:
            name, image = line.split("|", 1)
            containers.append({"name": name, "image_ref": image})
        except ValueError:
            LOG.warning("Unexpected docker ps line format: %r", line)

    LOG.info("Found %d running containers (CLI)", len(containers))
    return containers


def compute_report() -> List[Dict[str, str]]:
    containers = get_running_containers()
    if not containers:
        LOG.info("No running containers found.")
        return []

    rows: List[Dict[str, str]] = []

    for c in containers:
        name = c["name"]
        img = c["image_ref"]
        LOG.info("Processing container '%s' image '%s'", name, img)

        reg, ns, repo, tag = normalize_image_ref(img)
        full_repo_display = f"{ns}/{repo}" if reg in ("docker.io", "index.docker.io", "registry-1.docker.io") else f"{reg}/{ns}/{repo}"

        newest_tag = None
        newest_date = None
        installed_date = None

        if reg in ("docker.io", "index.docker.io", "registry-1.docker.io", "hub.docker.com"):
            newest_tag, newest_date = newest_stable_from_hub(ns, repo)
            installed_tag_name = tag.split("@")[0]
            installed_date = installed_tag_date_from_hub(ns, repo, installed_tag_name)
        else:
            LOG.warning("Non-Hub registry detected (%s); dates may be unavailable", reg)
            tags = fetch_registry_v2_tags(reg, f"{ns}/{repo}")
            stable_versions: List[Tuple[Version, str]] = []
            for t in tags:
                ver = is_stable_numeric_tag(t)
                if ver:
                    stable_versions.append((ver, t))
            if stable_versions:
                stable_versions.sort(key=lambda x: x[0])
                newest_tag = stable_versions[-1][1]

        gap_days: Optional[int] = None
        if installed_date and newest_date:
            delta = newest_date - installed_date
            gap_days = max(delta.days, 0)
            LOG.debug("Computed gap_days=%s for %s", gap_days, name)
        else:
            if not installed_date:
                LOG.debug("Installed date unavailable for %s", name)
            if not newest_date:
                LOG.debug("Newest stable tag date unavailable for %s", name)

        rows.append({
            "Container": name,
            "Image": full_repo_display,
            "Installed Tag": tag,
            "Newest Stable Tag": newest_tag or "N/A",
            "Installed Tag Date": installed_date.isoformat() if installed_date else "N/A",
            "Newest Tag Date": newest_date.isoformat() if newest_date else "N/A",
            "Time Gap (days)": str(gap_days) if gap_days is not None else "N/A",
        })

    return rows


def print_table(rows: List[Dict[str, str]]) -> None:
    if not rows:
        print("No running containers found.")
        return
    headers = list(rows[0].keys())
    col_widths = [max(len(h), max((len(str(r[h])) for r in rows), default=0)) for h in headers]
    fmt = "  ".join("{:<" + str(w) + "}" for w in col_widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in col_widths]))
    for r in rows:
        print(fmt.format(*[r[h] for h in headers]))


def main():
    parser = argparse.ArgumentParser(description="Report Docker image versions vs newest stable and time gap.")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--json-logs", action="store_true", help="Emit logs as JSON to stderr")
    parser.add_argument("--log-file", default=None, help="Also write logs to this file")
    parser.add_argument("--output", choices=["table", "json", "csv"], default="table", help="Output format")
    args = parser.parse_args()

    configure_logging(args.log_level, args.json_logs, args.log_file)
    LOG.info("Starting report generation")

    try:
        rows = compute_report()
    except KeyboardInterrupt:
        LOG.warning("Interrupted by user")
        sys.exit(130)
    except Exception:
        LOG.exception("Unhandled error while computing report")
        sys.exit(1)

    if args.output == "json":
        print(json.dumps(rows, indent=2))
    elif args.output == "csv":
        if rows:
            headers = list(rows[0].keys())
            w = csv.DictWriter(sys.stdout, fieldnames=headers)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        else:
            # still emit headers for consistency
            w = csv.DictWriter(sys.stdout, fieldnames=["Container","Image","Installed Tag","Newest Stable Tag","Installed Tag Date","Newest Tag Date","Time Gap (days)"])
            w.writeheader()
    else:
        print_table(rows)

    LOG.info("Done.")


if __name__ == "__main__":
    main()