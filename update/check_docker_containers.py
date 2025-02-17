#!/usr/bin/env python3

import json
import os
import subprocess
import requests
import logging
import logging.handlers
import sys
import re
from datetime import datetime, timedelta
from packaging.version import Version, InvalidVersion

# Configure logging
LOG_FILENAME = "docker_check.log"
logger = logging.getLogger("docker_updater")
logger.setLevel(logging.DEBUG)

# File handler (DEBUG level)
fh = logging.handlers.RotatingFileHandler(
    LOG_FILENAME, maxBytes=5*1024*1024, backupCount=3
)
fh.setLevel(logging.DEBUG)
file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
fh.setFormatter(file_formatter)
logger.addHandler(fh)

# Console handler (INFO level)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(levelname)s: %(message)s")
ch.setFormatter(console_formatter)
logger.addHandler(ch)

# Optional: set Docker Hub credentials as environment variables
DOCKER_HUB_USERNAME = os.environ.get("DOCKER_HUB_USERNAME", "antonio.fontoura@gmail.com")
DOCKER_HUB_PASSWORD = os.environ.get("DOCKER_HUB_PASSWORD", "Depress-Imply-Ducking1")

# Default threshold in months (approx. 3 months)
threshold_months = 3

def parse_datetime(dt_str):
    """
    Safely parse an ISO8601-like string (with or without 'Z') to a datetime object.
    Returns None if parsing fails.
    """
    if not dt_str:
        return None
    # Replace trailing 'Z' with '+00:00' if present
    dt_str = dt_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None

def should_update(local_created_str, remote_created_str, months=3):
    """
    Return True if the difference between remote and local creation date exceeds `months`.
    Otherwise return False.
    """
    local_dt = parse_datetime(local_created_str)
    remote_dt = parse_datetime(remote_created_str)
    if not local_dt or not remote_dt:
        # If either is missing or unparseable, default to False (no automatic update).
        return False

    # Approximate months by days
    threshold_days = months * 30
    diff = (remote_dt - local_dt).days
    return diff > threshold_days

def get_repo_tag(image_full):
    if ":" in image_full:
        repo, tag = image_full.rsplit(":", 1)
    else:
        repo, tag = image_full, "latest"
    return repo, tag

def get_docker_hub_token(username, password):
    if not username or not password:
        logger.debug("No Docker Hub credentials found; proceeding anonymously.")
        return None
    url = "https://hub.docker.com/v2/users/login/"
    payload = {"username": username, "password": password}
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        token = resp.json().get("token")
        logger.debug("Authenticated with Docker Hub successfully.")
        return token
    except requests.RequestException as e:
        logger.warning(f"Failed to authenticate with Docker Hub: {e}")
        return None

def normalize_repo(repo):
    if repo.startswith("lscr.io/"):
        # Switch to Docker Hub name for LinuxServer images
        return repo.replace("lscr.io/", "")
    return repo

def get_local_image_created_date(image_full):
    """
    Returns the locally stored image's creation date (ISO string) if available,
    or None if the image doesn't exist locally under that reference.
    """
    try:
        cmd = ["docker", "image", "inspect", image_full, "--format", "{{.Created}}"]
        output = subprocess.check_output(cmd, universal_newlines=True).strip()
        return output if output else None
    except subprocess.CalledProcessError:
        return None

def get_latest_version_tag(repo, token=None, pages=2):
    """
    Pull multiple pages of tags from Docker Hub, ignoring non-semver or special tags,
    then return the highest semver tag and its 'last_updated' date.
    """
    if "/" not in repo:
        repo = f"library/{repo}"

    repo = normalize_repo(repo)

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    page = 1
    found_tags = []

    while page <= pages:
        url = (
            f"https://hub.docker.com/v2/repositories/{repo}/tags"
            f"?page_size=50&page={page}&ordering=last_updated"
        )
        try:
            r = requests.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch tags for {repo}: {e}")
            break

        results = data.get("results", [])
        if not results:
            break

        for result in results:
            name = result.get("name", "")
            last_updated = result.get("last_updated", "")

            # Skip non-release or dev-like tags
            if any(x in name for x in ["latest", "dev", "beta", "rc"]):
                continue

            try:
                ver = Version(name)
                found_tags.append((ver, name, last_updated))
            except InvalidVersion:
                pass

        next_page = data.get("next")
        if not next_page:
            break
        page += 1

    if not found_tags:
        return None, None

    # Highest semantic version
    found_tags.sort(key=lambda x: x[0], reverse=True)
    _, highest_tag, last_updated = found_tags[0]
    return highest_tag, last_updated

def main():
    logger.info("Starting Docker container version check.")

    token = get_docker_hub_token(DOCKER_HUB_USERNAME, DOCKER_HUB_PASSWORD)
    
    # List all running containers
    cmd = ["docker", "ps", "--format", "{{.ID}} {{.Image}}"]
    try:
        output = subprocess.check_output(cmd, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to run docker ps: {e}")
        return

    lines = output.strip().split("\n")
    results = []

    for line in lines:
        if not line.strip():
            continue
        container_id, image_full = line.strip().split()
        repo, tag = get_repo_tag(image_full)
        current_version = tag

        logger.debug(f"Checking container={container_id}, repo={repo}, tag={tag}")

        # Local creation date (ISO string)
        local_created_date = get_local_image_created_date(image_full)

        # Remote latest semantic version info
        latest_tag, updated_date = get_latest_version_tag(repo, token=token)

        # Decide if we should update
        # Compare local_created_date vs. updated_date
        update_needed = should_update(local_created_date, updated_date, months=threshold_months)

        results.append({
            "container_id": container_id,
            "image": repo,
            "current_tag": current_version,
            "current_image_created_date": local_created_date,
            "latest_tag": latest_tag,
            "latest_release_date": updated_date,
            "update": update_needed
        })

    try:
        with open("docker_versions.json", "w") as f:
            json.dump(results, f, indent=2)
        logger.info("docker_versions.json generated successfully.")
    except IOError as e:
        logger.error(f"Failed to write docker_versions.json: {e}")

if __name__ == "__main__":
    main()