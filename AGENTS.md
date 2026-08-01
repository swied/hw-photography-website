# Repository Guidelines

## Project Structure & Module Organization

This repository combines a Python photo-processing pipeline with a Hugo frontend. Automation lives in `scripts/`: `sync_engine.py` reads galleries from Google Cloud Storage and writes `site/data/photos.json`, while the Tkinter utilities manage local photos and gallery metadata. The deploy-triggering Google Cloud Function is in `cloud_function/`. Hugo templates are under `site/layouts/`, gallery configuration is under `site/content/gallery/`, and Tailwind input is in `site/assets/css/input.css`. Architecture and setup notes live in the root Markdown files and `docs/`.

Generated output such as `site/public/`, `site/resources/_gen/`, and `site/data/admin_photos.json` is intentionally ignored. Do not commit it.

## Build, Test, and Development Commands

- `python -m pip install google-cloud-storage Pillow` installs sync-engine dependencies.
- `GCS_BUCKET_NAME=<bucket> python scripts/sync_engine.py --mode public` refreshes the public photo manifest; Google application-default credentials are required.
- `cd site && npm install` installs Tailwind tooling.
- `cd site && npm run build:css` creates minified CSS at `site/static/css/style.css`.
- `cd site && hugo server -D` runs the local site at `http://localhost:1313/`.
- `cd site && hugo --minify` performs the production build used by GitHub Actions.
- `python -m compileall scripts cloud_function` provides a quick Python syntax check.

Use Hugo Extended 0.110.0 or newer, Python 3.9+, and Node 20 when matching CI.

## Coding Style & Naming Conventions

Use four-space indentation throughout Python, HTML, CSS, and JavaScript. Follow Python conventions: `snake_case` for functions and variables, `UPPER_SNAKE_CASE` for constants, and focused helper functions for image or metadata operations. Use lowercase kebab-case for gallery IDs and directories, for example `site/content/gallery/lifeguard-tower/`. Preserve the existing JSON schema when editing gallery `config.json` files. No formatter or linter is configured, so match nearby code and keep diffs narrow.

## Testing Guidelines

There is currently no automated test framework or coverage threshold. Before opening a PR, run the syntax check, CSS build, and production Hugo build. Manually inspect affected galleries, responsive layouts, lightbox behavior, and generated photo metadata. If adding Python tests, place them in `tests/` and name files `test_<feature>.py`.

## Commit & Pull Request Guidelines

Recent commits use short, imperative summaries such as `fix photo caching race condition`. Keep each commit scoped to one behavior. PRs should explain the user-visible effect, note configuration or GCS schema changes, list validation commands, link related issues, and include screenshots for layout or gallery changes. Never commit credentials; use environment variables and GitHub secrets for GCS and GitHub tokens.
