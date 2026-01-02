import os
import requests
import functions_framework

# CONFIGURATION (Set these as Environment Variables during deployment)
GITHUB_REPO = os.environ.get("GITHUB_REPO") # e.g., "your-username/your-repo"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") # Personal Access Token (PAT)

@functions_framework.cloud_event
def trigger_github_build(cloud_event):
    """
    Triggered by a change to a Cloud Storage bucket.
    """
    data = cloud_event.data
    event_type = cloud_event["type"]
    bucket = data["bucket"]
    name = data["name"]

    print(f"Event: {event_type} | Bucket: {bucket} | File: {name}")

    # OPTIONAL: Filter to avoid triggering on thumbnail generation
    # If the file is in the 'thumbnails/' folder, ignore it to prevent infinite loops.
    if "thumbnails/" in name or "display/" in name:
        print("Skipping thumbnail change to prevent loop.")
        return "Skipped"

    # The Endpoint for triggering GitHub Actions
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}",
    }

    # The payload matches your deploy.yml 'repository_dispatch' type
    payload = {
        "event_type": "gcs-update",
        "client_payload": {
            "file": name,
            "bucket": bucket
        }
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 204:
        print(f"Successfully triggered build for {GITHUB_REPO}")
        return "Success"
    else:
        print(f"Failed to trigger build: {response.status_code} - {response.text}")
        # Raising an exception will cause Cloud Functions to retry (be careful with this)
        # raise Exception(f"GitHub API Error: {response.status_code}")
        return "Failed"