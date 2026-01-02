import os
import json
import logging
import argparse
import re
import time  # Added time for cache busting
from io import BytesIO
from datetime import timedelta
from google.cloud import storage
from PIL import Image, ExifTags, ImageCms

# Configuration
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "my-photo-portfolio-bucket")
THUMB_SIZE = (800, 800)
DATA_FILE_PATH = "site/data/photos.json"
ADMIN_DATA_FILE_PATH = "site/data/admin_photos.json"

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_exif_data(image_bytes):
    """Extracts basic EXIF data from image bytes."""
    exif_data = {
        "iso": "N/A",
        "aperture": "N/A",
        "shutter": "N/A",
        "focal_length": "N/A",
        "camera": "N/A",
        "lens": "N/A",
        "date": "N/A"
    }
    try:
        img = Image.open(BytesIO(image_bytes))
        exif = img.getexif()
        if not exif:
            return exif_data

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
    """Converts 'My Folder Name' to 'my-folder-name' for URL safety."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text

def process_gallery(bucket, prefix, mode="public"):
    """Scans a gallery folder, generates thumbnails, and builds metadata."""
    
    # Raw folder name (e.g., "Japan Trip 2024")
    raw_name = prefix.strip("/").split("/")[-1]
    
    # 1. Generate robust defaults in case config.json is missing
    safe_id = slugify(raw_name) # "japan-trip-2024"
    human_title = raw_name.replace("-", " ").replace("_", " ").title() # "Japan Trip 2024"

    logging.info(f"Processing Gallery: {raw_name} (ID: {safe_id})")

    config_blob = bucket.get_blob(f"{prefix}config.json")
    gallery_meta = {
        "id": safe_id,
        "title": human_title,
        "story": "",
        "visibility": "public",
        "photos_meta": {} 
    }
    
    # 2. Load Config if it exists (Overrides defaults)
    if config_blob:
        try:
            loaded_meta = json.loads(config_blob.download_as_text())
            if "photos" in loaded_meta:
                gallery_meta["photos_meta"] = loaded_meta.pop("photos")
            gallery_meta.update(loaded_meta)
        except Exception as e:
            logging.error(f"Error reading config.json for {raw_name}: {e}")

    # Access Control Logic
    if mode == "public" and gallery_meta["visibility"] != "public":
        logging.info(f"Skipping private gallery: {safe_id}")
        return None

    photos = []
    blobs = bucket.list_blobs(prefix=f"originals/{raw_name}/")

    # Generate a timestamp once per run to bust cache
    cache_buster = f"?v={int(time.time())}"

    for blob in blobs:
        if blob.name.lower().endswith(('.jpg', '.jpeg', '.png')):
            filename = os.path.basename(blob.name)
            thumb_path = f"thumbnails/{raw_name}/{os.path.splitext(filename)[0]}.webp"
            
            # 3. URL Generation
            if mode == "admin":
                img_url = blob.generate_signed_url(expiration=timedelta(hours=1))
                thumb_blob = bucket.blob(thumb_path)
                thumb_url = thumb_blob.generate_signed_url(expiration=timedelta(hours=1)) if thumb_blob.exists() else None
            else:
                img_url = blob.public_url
                # We need to ensure the thumbnail URL uses the correct path encoding
                thumb_url = f"https://storage.googleapis.com/{BUCKET_NAME}/thumbnails/{raw_name}/{os.path.splitext(filename)[0]}.webp"
                
                # Encode spaces
                thumb_url = thumb_url.replace(" ", "%20")
                if img_url:
                    img_url = img_url.replace(" ", "%20")

                # Append Cache Buster
                thumb_url += cache_buster
                if img_url:
                    img_url += cache_buster

            # 4. Thumbnail Generation
            thumb_blob = bucket.blob(thumb_path)
            if not thumb_blob.exists() and mode != "read_only":
                logging.info(f"Generating thumbnail for {filename}")
                img_bytes = blob.download_as_bytes()
                exif = get_exif_data(img_bytes)
                
                with Image.open(BytesIO(img_bytes)) as img:
                    # A. COLOR MANAGEMENT (Convert to sRGB)
                    icc_profile = img.info.get('icc_profile')
                    
                    if icc_profile:
                        try:
                            # 1. Load source profile from image
                            src_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                            # 2. Create destination sRGB profile
                            dst_profile = ImageCms.createProfile('sRGB')
                            # 3. Perform the conversion
                            # This mathematically shifts pixel values to look correct in sRGB
                            img = ImageCms.profileToProfile(img, src_profile, dst_profile)
                        except Exception as e:
                            logging.warning(f"Color profile conversion failed for {filename}: {e}")
                            # Fallback: Just convert to RGB mode if transformation failed

                    # B. Ensure RGB mode (handling CMYK, RGBA, etc.)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                        
                    # C. High Quality Resize
                    img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    
                    thumb_buffer = BytesIO()
                    
                    # D. Save as WebP
                    img.save(thumb_buffer, format="WEBP", quality=85, method=6)
                    
                    thumb_blob.upload_from_string(thumb_buffer.getvalue(), content_type="image/webp")
            else:
                 exif = {} 

            # 5. Default Photo Metadata
            clean_name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")

            photo_data = {
                "filename": filename,
                "src": img_url,
                "thumb": thumb_url,
                "exif": exif,
                "title": clean_name,
                "story": "", 
                "product_id": None,
                "licensing": {}
            }

            if filename in gallery_meta["photos_meta"]:
                manual_data = gallery_meta["photos_meta"][filename]
                photo_data.update(manual_data)

            photos.append(photo_data)

    gallery_meta["photos"] = photos
    
    if "photos_meta" in gallery_meta:
        del gallery_meta["photos_meta"]
    
    if photos and "cover" not in gallery_meta:
        gallery_meta["cover"] = photos[0]["thumb"]
    
    return gallery_meta

def main():
    parser = argparse.ArgumentParser(description="Sync GCS Photos to Hugo Data")
    parser.add_argument("--mode", choices=["public", "admin"], default="public", help="Generation mode")
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