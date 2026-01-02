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
THUMB_SIZE = (800, 800)
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

def process_gallery(bucket, prefix, mode="public"):
    raw_name = prefix.strip("/").split("/")[-1]
    safe_id = slugify(raw_name)
    human_title = raw_name.replace("-", " ").replace("_", " ").title()

    logging.info(f"Processing Gallery: {raw_name} (ID: {safe_id})")

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
        except Exception as e:
            logging.error(f"Error reading config.json for {raw_name}: {e}")

    if mode == "public" and gallery_meta["visibility"] != "public":
        return None

    photos = []
    blobs = bucket.list_blobs(prefix=f"originals/{raw_name}/")
    cache_buster = f"?v={int(time.time())}"

    for blob in blobs:
        if blob.name.lower().endswith(('.jpg', '.jpeg', '.png')):
            # Calculate Relative Path (e.g. "SubFolder/Image.jpg")
            # prefix is "originals/GalleryName/"
            # blob.name is "originals/GalleryName/SubFolder/Image.jpg"
            rel_path = blob.name[len(prefix):] 
            
            # Determine Sub-Album from folder structure
            sub_album = os.path.dirname(rel_path) # "SubFolder" or "" if root
            filename = os.path.basename(rel_path) # "Image.jpg"

            # Create distinct thumbnail path mirroring structure to avoid collisions
            thumb_path = f"thumbnails/{raw_name}/{os.path.splitext(rel_path)[0]}.webp"
            
            if mode == "admin":
                img_url = blob.generate_signed_url(expiration=timedelta(hours=1))
                thumb_blob = bucket.blob(thumb_path)
                thumb_url = thumb_blob.generate_signed_url(expiration=timedelta(hours=1)) if thumb_blob.exists() else None
            else:
                img_url = blob.public_url
                thumb_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{thumb_path}"
                
                # Encode and Cache Bust
                thumb_url = thumb_url.replace(" ", "%20") + cache_buster
                if img_url:
                    img_url = img_url.replace(" ", "%20") + cache_buster

            thumb_blob = bucket.blob(thumb_path)
            if not thumb_blob.exists() and mode != "read_only":
                logging.info(f"Generating thumbnail for {rel_path}")
                img_bytes = blob.download_as_bytes()
                exif = get_exif_data(img_bytes)
                
                with Image.open(BytesIO(img_bytes)) as img:
                    icc_profile = img.info.get('icc_profile')
                    if icc_profile:
                        try:
                            src = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
                            dst = ImageCms.createProfile('sRGB')
                            img = ImageCms.profileToProfile(img, src, dst)
                        except: pass
                    if img.mode != 'RGB': img = img.convert('RGB')
                    img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
                    thumb_buffer = BytesIO()
                    img.save(thumb_buffer, format="WEBP", quality=85, method=6)
                    thumb_blob.upload_from_string(thumb_buffer.getvalue(), content_type="image/webp")
            else:
                 exif = {} 

            clean_name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")

            photo_data = {
                "id": rel_path, # Use relative path as unique ID
                "filename": filename,
                "sub_album": sub_album, # New Field
                "src": img_url,
                "thumb": thumb_url,
                "exif": exif,
                "title": clean_name,
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
    
    output_data = {"galleries": []}
    for prefix in iterator.prefixes:
        gallery_data = process_gallery(bucket, prefix, mode=args.mode)
        if gallery_data: output_data["galleries"].append(gallery_data)

    target_file = ADMIN_DATA_FILE_PATH if args.mode == "admin" else DATA_FILE_PATH
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    with open(target_file, "w") as f: json.dump(output_data, f, indent=2)
    logging.info(f"Manifest generated at {target_file}")

if __name__ == "__main__":
    main()