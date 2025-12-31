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

def process_gallery(bucket, prefix, mode="public"):
    """Scans a gallery folder, generates thumbnails, and builds metadata."""
    
    gallery_name = prefix.strip("/").split("/")[-1]
    logging.info(f"Processing Gallery: {gallery_name}")

    # 1. Load Manual Configuration (The 'Brain' of the gallery)
    config_blob = bucket.get_blob(f"{prefix}config.json")
    gallery_meta = {
        "id": gallery_name,
        "title": gallery_name.replace("-", " ").title(),
        "story": "",
        "visibility": "public",
        "photos_meta": {} # Dictionary keyed by filename for manual overrides
    }
    
    if config_blob:
        try:
            loaded_meta = json.loads(config_blob.download_as_text())
            # We separate top-level keys from the 'photos' dictionary
            if "photos" in loaded_meta:
                gallery_meta["photos_meta"] = loaded_meta.pop("photos")
            gallery_meta.update(loaded_meta)
        except Exception as e:
            logging.error(f"Error reading config.json for {gallery_name}: {e}")

    # Access Control Logic
    if mode == "public" and gallery_meta["visibility"] != "public":
        logging.info(f"Skipping private gallery: {gallery_name}")
        return None

    photos = []
    blobs = bucket.list_blobs(prefix=f"originals/{gallery_name}/")

    for blob in blobs:
        if blob.name.lower().endswith(('.jpg', '.jpeg', '.png')):
            filename = os.path.basename(blob.name)
            thumb_path = f"thumbnails/{gallery_name}/{os.path.splitext(filename)[0]}.webp"
            
            # 2. URL Generation
            if mode == "admin":
                img_url = blob.generate_signed_url(expiration=timedelta(hours=1))
                thumb_blob = bucket.blob(thumb_path)
                thumb_url = thumb_blob.generate_signed_url(expiration=timedelta(hours=1)) if thumb_blob.exists() else None
            else:
                img_url = blob.public_url
                thumb_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{thumb_path}"

            # 3. Thumbnail & EXIF
            thumb_blob = bucket.blob(thumb_path)
            # Regenerate if missing or if we are forced to
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
                 # In a real production run, you might want to cache EXIF in GCS to avoid re-downloading
                 exif = {} 

            # 4. Merge Manual Metadata (Commerce & Story)
            # Default values
            photo_data = {
                "filename": filename,
                "src": img_url,
                "thumb": thumb_url,
                "exif": exif,
                "title": "",
                "story": "",
                "product_id": None,     # Lemon Squeezy Product ID
                "licensing": {}         # Dict: { "adobe": "url", "getty": "url" }
            }

            # Overlay config.json data if it exists for this file
            if filename in gallery_meta["photos_meta"]:
                manual_data = gallery_meta["photos_meta"][filename]
                photo_data.update(manual_data)

            photos.append(photo_data)

    gallery_meta["photos"] = photos
    
    # Cleanup internal meta key before output
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