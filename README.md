# Heather Wied Photography

Source code and content pipeline for [heatherwiedphotography.com](https://heatherwiedphotography.com/), a responsive photography portfolio deployed to GitHub Pages.

The project combines a Hugo frontend with a Python synchronization engine. Photos and gallery metadata originate in Google Cloud Storage (GCS); the sync engine creates web-ready image variants, extracts EXIF metadata, and generates the JSON manifest consumed by Hugo.

## Features

- Responsive gallery and sub-album layouts
- Alpine.js lightbox with photo details
- Automatic WebP display images and thumbnails
- Gallery stories, photo captions, and configurable covers
- Optional Lemon Squeezy purchase links and stock licensing URLs
- Automated deployment following repository or GCS updates

## Architecture

```text
GCS originals/<gallery>/
        │
        ▼
scripts/sync_engine.py ──► GCS display/ and thumbnails/
        │
        ▼
site/data/photos.json ──► Hugo + Tailwind CSS ──► GitHub Pages
```

The principal directories are:

```text
cloud_function/        GCS event handler that requests a GitHub build
scripts/               Sync engine and local gallery-management utilities
site/assets/           Tailwind CSS source
site/content/gallery/  Gallery content and configuration
site/data/             Generated photo manifest
site/layouts/          Hugo templates
docs/                  Architecture and project background
```

## Prerequisites

- Python 3.9 or newer (CI uses Python 3.10)
- Hugo Extended 0.110.0 or newer
- Node.js 20 and npm
- A GCP project and bucket when synchronizing real galleries
- Google Cloud application-default credentials with appropriate bucket access

## Local Setup

Clone the repository, create a virtual environment, and install the Python and frontend dependencies:

```bash
git clone git@github.com:swied/hw-photography-website.git
cd hw-photography-website
python3 -m venv .venv
source .venv/bin/activate
python -m pip install google-cloud-storage Pillow
npm --prefix site install
```

The site requires a valid `site/data/photos.json`. To generate it from GCS, authenticate and run the sync engine from the repository root:

```bash
gcloud auth application-default login
export GCS_BUCKET_NAME="your-bucket-name"
python scripts/sync_engine.py --mode public
```

> **Caution:** The sync engine can upload missing WebP variants to `display/` and `thumbnails/` in the selected bucket and make those objects public. Confirm `GCS_BUCKET_NAME` before running it.

Build the CSS and start Hugo:

```bash
npm --prefix site run build:css
cd site
hugo server -D
```

Open `http://localhost:1313/`. For a production-equivalent build, run `hugo --minify` from `site/`; output is written to `site/public/`.

## Gallery Data

Each source gallery lives at `gs://<bucket>/originals/<gallery-name>/`. Place supported images (`.jpg`, `.jpeg`, or `.png`) and an optional `config.json` in that directory. A minimal configuration is:

```json
{
  "title": "Coastal Light",
  "story": "Photographs from the Pacific coast.",
  "visibility": "public",
  "sort_by": "date",
  "photos": {
    "wave.jpg": {
      "title": "Incoming Tide",
      "story": "Late afternoon near the headland."
    }
  }
}
```

Supported sort modes are `filename`, `date`, and `random`. Run the sync engine with `--mode admin` to create the ignored `site/data/admin_photos.json` manifest containing temporary signed URLs.

For a graphical metadata editor, run `python scripts/gallery_manager.py`. The separate `python scripts/organize_photos.py` utility copies local JPEGs into date- or session-based folders. Both tools require Tkinter and open desktop dialogs.

## Validation

No automated test suite is currently configured. Before submitting changes, run the available syntax and build checks:

```bash
python -m compileall scripts cloud_function
npm --prefix site run build:css
cd site && hugo --minify
```

Also inspect affected galleries at mobile and desktop widths and verify lightbox behavior and generated metadata.

## Deployment and Configuration

Pushes to `main`, manual workflow dispatches, and `gcs-update` repository dispatches run `.github/workflows/deploy.yml`. The workflow synchronizes public data, builds Tailwind CSS and Hugo, and deploys the artifact to GitHub Pages.

GitHub Actions requires these repository secrets:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `GCS_BUCKET_NAME`

The optional cloud function uses `GITHUB_REPO` and `GITHUB_TOKEN` environment variables. Never commit credentials, signed URLs, `.env` files, or generated admin manifests.

## Contributing

See [AGENTS.md](AGENTS.md) for repository conventions, validation expectations, and pull request guidance. Additional setup details are available in [step-by-step-build-guide.md](step-by-step-build-guide.md), and the data model is described in [project-file-schema.md](project-file-schema.md).
