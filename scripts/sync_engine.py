import os
import json
import logging
import argparse
import re
import time
from io import BytesIO
from datetime import timedelta
from google.cloud import storage
from PIL import Image, ExifTags, ImageCms

# Configuration
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "my-photo-portfolio-bucket")
DISPLAY_SIZE = (2048, 2048) # Max dimension for Lightbox view
THUMB_SIZE = (800, 800)     # Max dimension for Grid view
DATA_FILE_PATH = "site/data/photos.json"
ADMIN_DATA_FILE_PATH = "site/data/admin_photos.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_exif_data(image_bytes):
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

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text

def process_image_variant(img, target_size, quality=85):
    """Resizes and converts image to WebP bytes with sRGB profile."""
    # Work on a copy to avoid affecting the original object
    img_copy = img.copy()
    
    # 1. Color Management (Already handled in main loop, but safety check)
    if img_copy.mode != 'RGB': 
        img_copy = img_copy.convert('RGB')
        
    # 2. Resize
    img_copy.thumbnail(target_size, Image.Resampling.LANCZOS)
    
    buffer = BytesIO()
    # 3. Save as WebP
    img_copy.save(buffer, format="WEBP", quality=quality, method=6)
    return buffer.getvalue()

def load_existing_exif(file_path):
    """Loads previous JSON to preserve EXIF data if we skip processing."""
    exif_cache = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                for gallery in data.get('galleries', []):
                    for photo in gallery.get('photos', []):
                        # Key by unique ID (filename or relative path)
                        key = photo.get('id') or photo.get('filename')
                        exif_cache[key] = photo.get('exif', {})
        except Exception: pass
    return exif_cache

def process_gallery(bucket, prefix, exif_cache, mode="public"):
    raw_name = prefix.strip("/").split("/")[-1]
    safe_id = slugify(raw_name)
    human_title = raw_name.replace("-", " ").replace("_", " ").title()

    logging.info(f"Processing Gallery: {raw_name}")

    config_blob = bucket.get_blob(f"{prefix}config.json")
    gallery_meta = {
        "id": safe_id,
        "title": human_title,
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
        except Exception: pass

    if mode == "public" and gallery_meta["visibility"] != "public":
        return None

    photos = []
    blobs = bucket.list_blobs(prefix=f"originals/{raw_name}/")
    cache_buster = f"?v={int(time.time())}"

    for blob in blobs:
        if blob.name.lower().endswith(('.jpg', '.jpeg', '.png')):
            # Paths
            rel_path = blob.name[len(prefix):] # e.g. "SubFolder/Img.jpg"
            sub_album = os.path.dirname(rel_path)
            filename = os.path.basename(rel_path)
            clean_name = os.path.splitext(filename)[0]

            # Define destination paths (Mirroring folder structure)
            thumb_path = f"thumbnails/{raw_name}/{os.path.splitext(rel_path)[0]}.webp"
            display_path = f"display/{raw_name}/{os.path.splitext(rel_path)[0]}.webp"
            
            # Check existence
            thumb_blob = bucket.blob(thumb_path)
            display_blob = bucket.blob(display_path)
            
            thumb_exists = thumb_blob.exists()
            display_exists = display_blob.exists()
            
            exif = {}

            # PROCESS IMAGES (Download Only If Needed)
            if (not thumb_exists or not display_exists) and mode != "read_only":
                logging.info(f"Optimizing: {rel_path}")
                img_bytes = blob.download_as_bytes()
                exif = get_exif_data(img_bytes)
                
                with Image.open(BytesIO(img_bytes)) as img:
                    # Color Management (sRGB Conversion)
                    icc_profile = img.info.get('icc_profile')
                    if icc_profile:
                        try:
                            src = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                            dst = ImageCms.createProfile('sRGB')
                            img = ImageCms.profileToProfile(img, src, dst)
                        except: pass
                    
                    # Generate Display Version (Large, Quality 90)
                    if not display_exists:
                        disp_data = process_image_variant(img, DISPLAY_SIZE, quality=90)
                        display_blob.upload_from_string(disp_data, content_type="image/webp")
                        display_blob.make_public()

                    # Generate Thumbnail Version (Small, Quality 85)
                    if not thumb_exists:
                        thumb_data = process_image_variant(img, THUMB_SIZE, quality=85)
                        thumb_blob.upload_from_string(thumb_data, content_type="image/webp")
                        thumb_blob.make_public()
            else:
                # If we skipped download, try to retrieve EXIF from cache (previous run)
                # Use rel_path as key since it's unique within gallery
                exif = exif_cache.get(rel_path, {})

            # URL GENERATION
            if mode == "admin":
                # For admin, we generate signed URLs for the optimized assets
                disp_url = display_blob.generate_signed_url(expiration=timedelta(hours=1)) if display_exists else None
                thumb_url = thumb_blob.generate_signed_url(expiration=timedelta(hours=1)) if thumb_exists else None
            else:
                # Public URLs
                disp_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{display_path}"
                thumb_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{thumb_path}"
                
                # Encoding & Cache Busting
                disp_url = disp_url.replace(" ", "%20") + cache_buster
                thumb_url = thumb_url.replace(" ", "%20") + cache_buster

            clean_title = clean_name.replace("_", " ").replace("-", " ")

            photo_data = {
                "id": rel_path,
                "filename": filename,
                "sub_album": sub_album,
                "src": disp_url,    # Now points to the Optimized Display version
                "thumb": thumb_url, # Points to Thumbnail
                "exif": exif,
                "title": clean_title,
                "story": "", 
                "product_id": None,
                "licensing": {}
            }

            if filename in gallery_meta["photos_meta"]:
                photo_data.update(gallery_meta["photos_meta"][filename])

            photos.append(photo_data)

    gallery_meta["photos"] = photos
    if "photos_meta" in gallery_meta: del gallery_meta["photos_meta"]
    if photos and "cover" not in gallery_meta: gallery_meta["cover"] = photos[0]["thumb"]
    
    return gallery_meta

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["public", "admin"], default="public")
    args = parser.parse_args()

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    iterator = bucket.list_blobs(prefix="originals/", delimiter="/")
    list(iterator)
    
    # Load previous data to preserve EXIF
    target_file = ADMIN_DATA_FILE_PATH if args.mode == "admin" else DATA_FILE_PATH
    exif_cache = load_existing_exif(target_file)

    output_data = {"galleries": []}
    for prefix in iterator.prefixes:
        gallery_data = process_gallery(bucket, prefix, exif_cache, mode=args.mode)
        if gallery_data: output_data["galleries"].append(gallery_data)

    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    with open(target_file, "w") as f: json.dump(output_data, f, indent=2)
    logging.info(f"Manifest generated at {target_file}")

if __name__ == "__main__":
    main()