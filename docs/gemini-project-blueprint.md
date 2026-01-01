# **Project Blueprint: Automated Hybrid Portfolio**

This document contains the complete source code for the "Storyteller" Portfolio architecture (Hugo + GCS + Python + Tailwind).

## **1. CI/CD Workflow**

**File:** `.github/workflows/deploy.yml`

```yaml
name: Deploy Portfolio

on:  
  push:  
    branches: ["main"]  
  workflow_dispatch:  
  repository_dispatch:  
    types: [gcs-update]

permissions:  
  contents: read  
  pages: write  
  id-token: write

concurrency:  
  group: "pages"  
  cancel-in-progress: false

jobs:  
  build:  
    runs-on: ubuntu-latest  
    steps:  
      - name: Checkout  
        uses: actions/checkout@v4

      # Python for Sync Engine  
      - name: Setup Python  
        uses: actions/setup-python@v4  
        with:  
          python-version: '3.10'

      - name: Install Python Deps  
        run: |  
          pip install google-cloud-storage Pillow

      # Google Cloud Auth  
      - name: Authenticate to Google Cloud  
        uses: google-github-actions/auth@v2  
        with:  
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}  
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      # The Core Logic: Generates JSON data from GCS  
      - name: Run Sync Engine  
        env:  
          GCS_BUCKET_NAME: ${{ secrets.GCS_BUCKET_NAME }}  
        run: |  
          python scripts/sync_engine.py --mode public

      # Generate Hugo Pages for each gallery found in JSON  
      - name: Generate Gallery Stubs  
        run: |  
          mkdir -p site/content/gallery  
          python -c "import json, os;   
          data_path='site/data/photos.json';  
          print(f'Checking {data_path}...');  
          if os.path.exists(data_path):  
              data=json.load(open(data_path));   
              [open(f'site/content/gallery/{g["id"]}.md', 'w').write(f'---ntitle: {g["title"]}n---') for g in data['galleries']]  
          else:  
              print('No photos.json found, skipping stub generation.')"

      # Node.js for Tailwind CSS  
      - name: Setup Node.js  
        uses: actions/setup-node@v4  
        with:  
          node-version: '20'

      - name: Install Dependencies & Build CSS  
        working-directory: ./site  
        run: |  
          npm install  
          npm run build:css

      # Hugo Build  
      - name: Setup Hugo  
        uses: peaceiris/actions-hugo@v2  
        with:  
          hugo-version: '0.110.0'  
          extended: true

      - name: Build Site  
        working-directory: ./site  
        run: hugo --minify

      - name: Upload artifact  
        uses: actions/upload-pages-artifact@v3  
        with:  
          path: ./site/public

  deploy:  
    environment:  
      name: github-pages  
      url: ${{ steps.deployment.outputs.page_url }}  
    runs-on: ubuntu-latest  
    needs: build  
    steps:  
      - name: Deploy to GitHub Pages  
        id: deployment  
        uses: actions/deploy-pages@v4
```

## **2. Logic & Scripts**

**File:** `scripts/sync_engine.py`

```python
import os  
import json  
import logging  
import argparse  
from io import BytesIO  
from datetime import timedelta  
from google.cloud import storage  
from PIL import Image, ExifTags

# Configuration  
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "my-photo-portfolio-bucket")  
THUMB_SIZE = (800, 800)  
DATA_FILE_PATH = "site/data/photos.json"  
ADMIN_DATA_FILE_PATH = "site/data/admin_photos.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_exif_data(image_bytes):  
    """Extracts basic EXIF data from image bytes."""  
    exif_data = {"iso": "N/A", "aperture": "N/A", "shutter": "N/A", "focal_length": "N/A", "camera": "N/A", "lens": "N/A", "date": "N/A"}  
    try:  
        img = Image.open(BytesIO(image_bytes))  
        exif = img.getexif()  
        if not exif: return exif_data

        for key, val in exif.items():  
            if key in ExifTags.TAGS:  
                tag_name = ExifTags.TAGS[key]  
                if tag_name == "ISOSpeedRatings": exif_data["iso"] = val  
                if tag_name == "Model": exif_data["camera"] = str(val)  
                if tag_name == "DateTime": exif_data["date"] = str(val)  
                if tag_name == "ExifOffset":  
                    sub_ifd = img.getexif().get_ifd(key)  
                    for sub_key, sub_val in sub_ifd.items():  
                        sub_tag = ExifTags.TAGS.get(sub_key)  
                        if sub_tag == "FNumber": exif_data["aperture"] = f"f/{float(sub_val):.1f}"  
                        if sub_tag == "ExposureTime": exif_data["shutter"] = f"{sub_val}s"  
                        if sub_tag == "FocalLength": exif_data["focal_length"] = f"{int(sub_val)}mm"  
                        if sub_tag == "LensModel": exif_data["lens"] = str(sub_val)  
    except Exception as e:  
        logging.warning(f"Could not extract EXIF: {e}")  
    return exif_data

def process_gallery(bucket, prefix, mode="public"):  
    gallery_name = prefix.strip("/").split("/")[-1]  
    logging.info(f"Processing Gallery: {gallery_name}")

    config_blob = bucket.get_blob(f"{prefix}config.json")  
    gallery_meta = {  
        "id": gallery_name,  
        "title": gallery_name.replace("-", " ").title(),  
        "story": "",  
        "visibility": "public",  
        "photos_meta": {}  
    }  
      
    if config_blob:  
        try:  
            loaded_meta = json.loads(config_blob.download_as_text())  
            if "photos" in loaded_meta:  
                gallery_meta["photos_meta"] = loaded_meta.pop("photos")  
            gallery_meta.update(loaded_meta)  
        except Exception as e:  
            logging.error(f"Error reading config.json: {e}")

    if mode == "public" and gallery_meta["visibility"] != "public":  
        return None

    photos = []  
    blobs = bucket.list_blobs(prefix=f"originals/{gallery_name}/")

    for blob in blobs:  
        if blob.name.lower().endswith(('.jpg', '.jpeg', '.png')):  
            filename = os.path.basename(blob.name)  
            thumb_path = f"thumbnails/{gallery_name}/{os.path.splitext(filename)[0]}.webp"  
              
            if mode == "admin":  
                img_url = blob.generate_signed_url(expiration=timedelta(hours=1))  
                thumb_blob = bucket.blob(thumb_path)  
                thumb_url = thumb_blob.generate_signed_url(expiration=timedelta(hours=1)) if thumb_blob.exists() else None  
            else:  
                img_url = blob.public_url  
                thumb_url = f"[https://storage.googleapis.com/](https://storage.googleapis.com/){BUCKET_NAME}/{thumb_path}"

            thumb_blob = bucket.blob(thumb_path)  
            if not thumb_blob.exists() and mode != "read_only":  
                logging.info(f"Generating thumbnail for {filename}")  
                img_bytes = blob.download_as_bytes()  
                exif = get_exif_data(img_bytes)  
                with Image.open(BytesIO(img_bytes)) as img:  
                    img.thumbnail(THUMB_SIZE)  
                    thumb_buffer = BytesIO()  
                    img.save(thumb_buffer, format="WEBP", quality=80)  
                    thumb_blob.upload_from_string(thumb_buffer.getvalue(), content_type="image/webp")  
            else:  
                 exif = {} 

            photo_data = {  
                "filename": filename,  
                "src": img_url,  
                "thumb": thumb_url,  
                "exif": exif,  
                "title": "",  
                "story": "",  
                "product_id": None,  
                "licensing": {}  
            }

            if filename in gallery_meta["photos_meta"]:  
                photo_data.update(gallery_meta["photos_meta"][filename])

            photos.append(photo_data)

    gallery_meta["photos"] = photos  
    del gallery_meta["photos_meta"]  
      
    if photos and "cover" not in gallery_meta:  
        gallery_meta["cover"] = photos[0]["thumb"]  
      
    return gallery_meta

def main():  
    parser = argparse.ArgumentParser()  
    parser.add_argument("--mode", choices=["public", "admin"], default="public")  
    args = parser.parse_args()

    client = storage.Client()  
    bucket = client.bucket(BUCKET_NAME)  
    iterator = bucket.list_blobs(prefix="originals/", delimiter="/")  
    list(iterator)  
    prefixes = iterator.prefixes

    output_data = {"galleries": []}  
    for prefix in prefixes:  
        gallery_data = process_gallery(bucket, prefix, mode=args.mode)  
        if gallery_data:  
            output_data["galleries"].append(gallery_data)

    target_file = ADMIN_DATA_FILE_PATH if args.mode == "admin" else DATA_FILE_PATH  
    os.makedirs(os.path.dirname(target_file), exist_ok=True)  
    with open(target_file, "w") as f:  
        json.dump(output_data, f, indent=2)  
    logging.info(f"Manifest generated at {target_file}")

if __name__ == "__main__":  
    main()
```

## **3. Site Configuration & Styles**

**File:** `site/hugo.toml`

```text
baseURL = "http://localhost:1313/"  
languageCode = "en-us"  
title = "The Storyteller Portfolio"  
disableKinds = ["taxonomy", "term"] # Disable Tags/Categories

[markup]  
  [markup.goldmark]  
    [markup.goldmark.renderer]  
      unsafe = true

[params]  
  description = "A narrative photography portfolio."  
  author = "Your Name"
```

**File:** `site/package.json`

```json
{  
  "name": "portfolio-site",  
  "version": "1.0.0",  
  "scripts": {  
    "build:css": "tailwindcss -i ./assets/css/input.css -o ./static/css/style.css --minify"  
  },  
  "devDependencies": {  
    "@tailwindcss/aspect-ratio": "^0.4.2",  
    "@tailwindcss/typography": "^0.5.10",  
    "tailwindcss": "^3.4.1"  
  }  
}
```

**File:** `site/tailwind.config.js`

```js
/** @type {import('tailwindcss').Config} */  
module.exports = {  
  content: ["./layouts/**/*.html", "./content/**/*.md"],  
  theme: {  
    extend: {  
      fontFamily: {  
        sans: ['Inter', 'sans-serif'],  
      },  
    },  
  },  
  plugins: [  
    require('@tailwindcss/typography'),  
    require('@tailwindcss/aspect-ratio'),  
  ],  
}
```

**File:** `site/assets/css/input.css`

```css
@tailwind base;  
@tailwind components;  
@tailwind utilities;

.scrollbar-hide::-webkit-scrollbar {  
    display: none;  
}  
.scrollbar-hide {  
    -ms-overflow-style: none;  
    scrollbar-width: none;  
}
```

## **4. Hugo Layouts**

**File:** `site/layouts/_default/baseof.html`

```html
<!DOCTYPE html>  
<html lang="en">  
<head>  
    <meta charset="UTF-8">  
    <meta name="viewport" content="width=device-width, initial-scale=1.0">  
    <title>{{ block "title" . }}{{ .Title }} | {{ .Site.Title }}{{ end }}</title>  
    <script src="//[unpkg.com/alpinejs](https://unpkg.com/alpinejs)" defer></script>  
    <link rel="stylesheet" href="/css/style.css">  
    <link href="[https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap](https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap)" rel="stylesheet">  
    <style>  
        [x-cloak] { display: none !important; }  
        body { font-family: 'Inter', sans-serif; }  
    </style>  
</head>  
<body class="bg-gray-50 text-gray-900 flex flex-col min-h-screen">  
    <nav class="bg-white border-b border-gray-100 sticky top-0 z-40 bg-opacity-90 backdrop-blur-sm">  
        <div class="container mx-auto px-4 h-16 flex items-center justify-between">  
            <a href="/" class="text-lg font-bold tracking-tight hover:text-blue-600 transition-colors">  
                {{ .Site.Title }}  
            </a>  
            <div class="flex gap-6 text-sm font-medium text-gray-500">  
                <a href="/" class="hover:text-black transition-colors">Collections</a>  
            </div>  
        </div>  
    </nav>  
    <main class="flex-grow">  
        {{ block "main" . }}{{ end }}  
    </main>  
    <footer class="bg-white border-t border-gray-100 mt-20 py-12">  
        <div class="container mx-auto px-4 text-center space-y-2">  
            <p class="text-gray-400 text-sm">© {{ now.Year }} {{ .Site.Params.author }}. All rights reserved.</p>  
        </div>  
    </footer>  
</body>  
</html>
```

**File:** `site/layouts/index.html`

```html
{{ define "main" }}  
<div class="container mx-auto px-4 py-12">  
    <header class="text-center mb-16">  
        <h1 class="text-4xl font-bold mb-4 tracking-tight">{{ .Site.Title }}</h1>  
        <p class="text-gray-500 max-w-xl mx-auto">{{ .Site.Params.description }}</p>  
    </header>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">  
        {{ $data := .Site.Data.photos }}  
        {{ if $data }}  
            {{ range $data.galleries }}  
            <a href="/gallery/{{ .id }}" class="group block bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-300 overflow-hidden border border-gray-100">  
                <div class="aspect-w-3 aspect-h-2 relative overflow-hidden bg-gray-100">  
                    {{ if .cover }}  
                    <img src="{{ .cover }}" alt="{{ .title }}" class="object-cover w-full h-full transform group-hover:scale-105 transition-transform duration-700">  
                    {{ else }}  
                    <div class="flex items-center justify-center h-full text-gray-300">No Cover</div>  
                    {{ end }}  
                    {{ if eq .visibility "private" }}  
                    <div class="absolute top-2 right-2 bg-red-500 text-white text-xs font-bold px-2 py-1 rounded">PRIVATE</div>  
                    {{ end }}  
                </div>  
                <div class="p-6">  
                    <h2 class="text-xl font-bold mb-2 text-gray-900 group-hover:text-blue-600 transition-colors">{{ .title }}</h2>  
                    <p class="text-gray-500 line-clamp-3 text-sm leading-relaxed">{{ .story }}</p>  
                </div>  
            </a>  
            {{ end }}  
        {{ else }}  
            <div class="col-span-full text-center text-gray-400 py-12">  
                <p>No galleries found. Check site/data/photos.json</p>  
            </div>  
        {{ end }}  
    </div>  
</div>  
{{ end }}
```

**File:** `site/layouts/_default/single.html`

```html
{{ define "main" }}  
{{ $galleryID := .File.BaseFileName }}  
{{ $allPhotos := .Site.Data.photos.galleries }}  
{{ $gallery := index (where $allPhotos "id" $galleryID) 0 }}

{{ if $gallery }}  
<script src="[https://assets.lemonsqueezy.com/lemon.js](https://assets.lemonsqueezy.com/lemon.js)" defer></script>

<div class="container mx-auto px-4 py-12" x-data="{ activeImage: null, showModal: false }">  
    <div class="mb-12 max-w-3xl">  
        <a href="/" class="text-sm font-medium text-gray-400 hover:text-black mb-6 inline-flex items-center transition-colors">  
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>  
            Back to Collections  
        </a>  
        <h1 class="text-4xl md:text-5xl font-bold mb-6 tracking-tight text-gray-900">{{ $gallery.title }}</h1>  
        <div class="prose prose-lg text-gray-600 leading-relaxed">  
            <p>{{ $gallery.story }}</p>  
        </div>  
    </div>

    <div class="columns-1 md:columns-2 lg:columns-3 gap-6 space-y-6">  
        {{ range $index, $photo := $gallery.photos }}  
        <div class="break-inside-avoid relative group cursor-pointer"   
             @click="activeImage = {{ $photo | jsonify }}; showModal = true">  
            <img src="{{ .thumb }}" alt="{{ .filename }}" loading="lazy" class="w-full rounded-lg shadow-sm group-hover:shadow-md transition-all duration-300">  
            <div class="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-10 transition-all rounded-lg"></div>  
            <div class="absolute bottom-3 right-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">  
                {{ if .product_id }}  
                <span class="bg-emerald-500 text-white text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded shadow-sm">Buy</span>  
                {{ end }}  
                {{ if .licensing }}  
                <span class="bg-blue-500 text-white text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded shadow-sm">License</span>  
                {{ end }}  
            </div>  
        </div>  
        {{ end }}  
    </div>

    <!-- Lightbox Modal -->  
    <div x-show="showModal" x-cloak  
         class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-95 p-0 md:p-8 backdrop-blur-sm"  
         x-transition:enter="transition ease-out duration-300" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100"  
         x-transition:leave="transition ease-in duration-200" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0">  
           
        <div class="relative w-full h-full flex flex-col md:flex-row bg-white md:bg-transparent md:rounded-xl overflow-hidden shadow-2xl" @click.away="showModal = false">  
            <button @click="showModal = false" class="absolute top-4 right-4 z-50 p-2 text-gray-400 hover:text-white transition-colors bg-black bg-opacity-50 rounded-full md:bg-transparent">  
                <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>  
            </button>

            <div class="flex-1 flex items-center justify-center bg-black p-4">  
                <img :src="activeImage?.src" class="max-h-full max-w-full object-contain">  
            </div>

            <div class="w-full md:w-96 bg-white flex flex-col h-[40vh] md:h-full border-l border-gray-100">  
                <div class="flex-1 overflow-y-auto p-8 space-y-8">  
                    <div>  
                        <h3 class="text-2xl font-bold mb-3 text-gray-900" x-text="activeImage?.title || 'Untitled'"></h3>  
                        <p class="text-gray-600 text-sm leading-relaxed" x-show="activeImage?.story" x-text="activeImage?.story"></p>  
                    </div>

                    <div class="space-y-4">  
                        <template x-if="activeImage?.product_id">  
                            <a :href="'[https://store.lemonsqueezy.com/checkout/buy/](https://store.lemonsqueezy.com/checkout/buy/)' + activeImage.product_id"   
                               class="lemonsqueezy-button block w-full bg-gray-900 text-white text-center py-4 rounded-lg hover:bg-black transition-all font-semibold shadow-lg hover:shadow-xl transform hover:-translate-y-0.5">  
                                Purchase Print / Download  
                            </a>  
                        </template>  
                        <template x-if="activeImage?.licensing && Object.keys(activeImage.licensing).length > 0">  
                            <div>  
                                <p class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Available for License</p>  
                                <div class="flex flex-wrap gap-2">  
                                    <template x-for="(url, agency) in activeImage.licensing">  
                                        <a :href="url" target="_blank" class="px-3 py-2 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded text-xs font-medium text-gray-600 uppercase tracking-wide transition-colors" x-text="agency"></a>  
                                    </template>  
                                </div>  
                            </div>  
                        </template>  
                    </div>

                    <div class="pt-8 border-t border-gray-100">  
                        <h4 class="text-xs font-bold text-gray-400 uppercase tracking-widest mb-4">Technical Details</h4>  
                        <template x-if="activeImage?.exif">  
                            <dl class="grid grid-cols-2 gap-4 text-sm">  
                                <div x-show="activeImage.exif.camera"> <dt class="text-gray-400 text-xs">Camera</dt> <dd class="font-medium text-gray-900" x-text="activeImage.exif.camera"></dd> </div>  
                                <div x-show="activeImage.exif.lens"> <dt class="text-gray-400 text-xs">Lens</dt> <dd class="font-medium text-gray-900" x-text="activeImage.exif.lens"></dd> </div>  
                                <div x-show="activeImage.exif.aperture"> <dt class="text-gray-400 text-xs">Aperture</dt> <dd class="font-medium text-gray-900" x-text="activeImage.exif.aperture"></dd> </div>  
                                <div x-show="activeImage.exif.iso"> <dt class="text-gray-400 text-xs">ISO</dt> <dd class="font-medium text-gray-900" x-text="activeImage.exif.iso"></dd> </div>  
                            </dl>  
                        </template>  
                    </div>  
                </div>  
            </div>  
        </div>  
    </div>  
</div>  
{{ else }}  
<div class="container mx-auto py-20 text-center">  
    <h2 class="text-2xl font-bold">Gallery Not Found</h2>  
</div>  
{{ end }}  
{{ end }}
```

## **5. Cloud Function**

**File:** `cloud_function/main.py`

```python
import os  
import requests  
import functions_framework

GITHUB_REPO = os.environ.get("GITHUB_REPO")  
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

@functions_framework.cloud_event  
def trigger_github_build(cloud_event):  
    data = cloud_event.data  
    bucket = data["bucket"]  
    name = data["name"]

    if "thumbnails/" in name:  
        return "Skipped"

    url = f"[https://api.github.com/repos/](https://api.github.com/repos/){GITHUB_REPO}/dispatches"  
    headers = {  
        "Accept": "application/vnd.github.v3+json",  
        "Authorization": f"token {GITHUB_TOKEN}",  
    }  
    payload = {  
        "event_type": "gcs-update",  
        "client_payload": {"file": name, "bucket": bucket}  
    }

    requests.post(url, json=payload, headers=headers)  
    return "Success"
```

**File:** `cloud_function/requirements.txt`

```text
functions-framework==3.*  
requests==2.31.0
```

## **6. Miscellaneous**

**File:** `.gitignore`

```text
__pycache__/  
*.pyc  
env/  
venv/  
site/public/  
site/resources/_gen/  
.hugo_build.lock  
.env  
.DS_Store  
site/data/admin_photos.json  
node_modules/
```
