import os
import json
import logging
import argparse
import re
import time
import random
from io import BytesIO
from datetime import datetime, timedelta
from google.cloud import storage
from PIL import Image, ExifTags, ImageCms

# Configuration
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "my-photo-portfolio-bucket")
DISPLAY_SIZE = (2048, 2048) 
THUMB_SIZE = (800, 800)     
DATA_FILE_PATH = "site/data/photos.json"
ADMIN_DATA_FILE_PATH = "site/data/admin_photos.json"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_exif_data(image_bytes):
    exif_data = {"iso": "N/A", "aperture": "N/A", "shutter": "N/A", "focal_length": "N/A", "camera": "N/A", "lens": "N/A", "date": "N/A"}
    try:
        img = Image.open(BytesIO(image_bytes))
        exif = img.getexif()
        exif["blank"] = ""
        if not exif: return exif_data
        for key, val in exif.items():
            if key in ExifTags.TAGS:
                tag_name = ExifTags.TAGS[key]
                if tag_name == "ISOSpeedRatings": exif_data["iso"] = val
                if tag_name == "Model": exif_data["camera"] = str(val)
                if (tag_name == "DateTime") and (exif_data["date"]=="N/A"): 
                    exif_data["date"] = str(val)
                if tag_name == "ExifOffset":
                    sub_ifd = img.getexif().get_ifd(key)
                    for sub_key, sub_val in sub_ifd.items():
                        sub_tag = ExifTags.TAGS.get(sub_key)
                        if sub_key == "DateTimeOriginal": exif_data["date"] = str(val)
                        if sub_tag == "FNumber": exif_data["aperture"] = f"f/{float(sub_val):.1f}"
                        if sub_tag == "ExposureTime": exif_data["shutter"] = f"{sub_val}s"
                        if sub_tag == "FocalLength": exif_data["focal_length"] = f"{int(sub_val)}mm"
                        if sub_tag == "LensModel": exif_data["lens"] = str(sub_val)
    except Exception as e:
        logging.warning(f"Could not extract EXIF: {e}")
    return exif_data

def has_valid_exif(exif_dict):
    """Checks if the EXIF dict has actual data (not just N/A)."""
    if not exif_dict: return False
    # If aperture is present, we consider it valid.
    return exif_dict.get("aperture", "N/A")

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text

def process_image_variant(img, target_size, quality=85):
    img_copy = img.copy()
    if img_copy.mode != 'RGB': img_copy = img_copy.convert('RGB')
    img_copy.thumbnail(target_size, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    img_copy.save(buffer, format="WEBP", quality=quality, method=6)
    return buffer.getvalue()

def load_existing_exif(file_path):
    exif_cache = {}
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                for gallery in data.get('galleries', []):
                    for photo in gallery.get('photos', []):
                        key = photo.get('id') or photo.get('filename')
                        exif_cache[key] = photo.get('exif', {})
        except Exception: pass
    return exif_cache

def sort_photos(photos, method):
    def parse_date(date_str):
        try: return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
        except (ValueError, TypeError): return datetime.min

    if method == 'random':
        random.shuffle(photos)
        photos.sort(key=lambda x: x.get('sub_album', ''))
    elif method == 'date':
        photos.sort(key=lambda x: (x.get('sub_album', ''), parse_date(x['exif'].get('date'))))
    else:
        photos.sort(key=lambda x: (x.get('sub_album', ''), x.get('filename', '')))
    return photos

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
        "sort_by": "filename",
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
            rel_path = blob.name[len(prefix):]
            sub_album = os.path.dirname(rel_path)
            filename = os.path.basename(rel_path)
            
            thumb_path = f"thumbnails/{raw_name}/{os.path.splitext(rel_path)[0]}.webp"
            display_path = f"display/{raw_name}/{os.path.splitext(rel_path)[0]}.webp"
            
            thumb_blob = bucket.blob(thumb_path)
            display_blob = bucket.blob(display_path)
            
            thumb_exists = thumb_blob.exists()
            display_exists = display_blob.exists()
            
            # --- SELF-HEALING LOGIC ---
            # 1. Check Cache
            cached_exif = exif_cache.get(rel_path, {})
            
            # 2. Determine if we need to download (Missing Files OR Missing Data)
            needs_files = (not thumb_exists or not display_exists)
            needs_data = not has_valid_exif(cached_exif)
            
            should_download = (needs_files or needs_data) and mode != "read_only"
            
            exif = cached_exif # Default to cache
            
            if should_download:
                logging.info(f"Processing {rel_path} (Files: {needs_files}, Data Missing: {needs_data})")
                img_bytes = blob.download_as_bytes()
                
                # Extract EXIF (Always refresh this if we downloaded)
                exif = get_exif_data(img_bytes)
                
                # Only process images if files are missing
                if needs_files:
                    with Image.open(BytesIO(img_bytes)) as img:
                        icc_profile = img.info.get('icc_profile')
                        if icc_profile:
                            try:
                                src = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                                dst = ImageCms.createProfile('sRGB')
                                img = ImageCms.profileToProfile(img, src, dst)
                            except: pass
                        
                        if not display_exists:
                            disp_data = process_image_variant(img, DISPLAY_SIZE, quality=90)
                            display_blob.upload_from_string(disp_data, content_type="image/webp")
                            try: display_blob.make_public()
                            except: pass

                        if not thumb_exists:
                            thumb_data = process_image_variant(img, THUMB_SIZE, quality=85)
                            thumb_blob.upload_from_string(thumb_data, content_type="image/webp")
                            try: thumb_blob.make_public()
                            except: pass
            
            # URL Generation
            if mode == "admin":
                disp_url = display_blob.generate_signed_url(expiration=timedelta(hours=1)) if display_exists else None
                thumb_url = thumb_blob.generate_signed_url(expiration=timedelta(hours=1)) if thumb_exists else None
            else:
                disp_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{display_path}"
                thumb_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{thumb_path}"
                disp_url = disp_url.replace(" ", "%20") + cache_buster
                thumb_url = thumb_url.replace(" ", "%20") + cache_buster

            clean_name = os.path.splitext(filename)[0]
            clean_title = clean_name.replace("_", " ").replace("-", " ")

            photo_data = {
                "id": rel_path,
                "filename": filename,
                "sub_album": sub_album,
                "src": disp_url,
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

    photos = sort_photos(photos, gallery_meta.get("sort_by", "filename"))

    gallery_meta["photos"] = photos
    if "photos_meta" in gallery_meta: del gallery_meta["photos_meta"]
    
    # Updated Default Cover Logic: Check if cover is missing OR empty string
    current_cover = gallery_meta.get("cover")
    if photos and not current_cover: 
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
    
    target_file = ADMIN_DATA_FILE_PATH if args.mode == "admin" else DATA_FILE_PATH
    exif_cache = load_existing_exif(target_file)

    output_data = {"galleries": []}
    for prefix in iterator.prefixes:
        gallery_data = process_gallery(bucket, prefix, exif_cache, mode=args.mode)
        if gallery_data: output_data["galleries"].append(gallery_data)

    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    
    # ATOMIC WRITE
    temp_file = target_file + ".tmp"
    with open(temp_file, "w") as f: json.dump(output_data, f, indent=2)
    os.replace(temp_file, target_file)
    
    logging.info(f"Manifest generated at {target_file}")

if __name__ == "__main__":
    main()