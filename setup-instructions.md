# **The Storyteller Portfolio (Commerce Edition)**

An automated photography portfolio with built-in support for Lemon Squeezy sales and stock agency licensing.

## **1\. Cloud Storage Structure (GCS)**

Your GCS bucket now serves two purposes: hosting watermarked assets for the site and storing the configuration.

**Folder: originals/japan-trip/**

* DSC001\_WM.jpg (Watermarked image for display)  
* DSC002\_WM.jpg (Watermarked image for display)  
* config.json (The Master Manifest)

## **2\. The Configuration File (config.json)**

To enable sales, titles, or licensing links for specific photos, upload a config.json into the gallery folder.

**Example config.json:**

{  
  "title": "Japan 2024",  
  "story": "A journey through the neon streets of Tokyo.",  
  "visibility": "public",  
  "photos": {  
    "DSC001\_WM.jpg": {  
      "title": "Neon Rain",  
      "story": "Captured at 2 AM in Shinjuku.",  
      "product\_id": "89324-variant-id",   
      "licensing": {  
        "adobe": "\[https://stock.adobe.com/image/\](https://stock.adobe.com/image/)...",  
        "getty": "\[https://www.gettyimages.com/detail/\](https://www.gettyimages.com/detail/)..."  
      }  
    },  
    "DSC002\_WM.jpg": {  
      "title": "Quiet Temple",  
      "product\_id": "89325-variant-id"  
    }  
  }  
}

* **product\_id**: The Variant ID from Lemon Squeezy. The site will automatically render a "Purchase" button.  
* **licensing**: A dictionary of agency names and URLs. The site will render referral buttons.

## **3\. Automation Logic**

1. **Sync Engine**: The script reads the config.json.  
2. **Merger**: It merges your manual data (Titles, Commerce IDs) with the automatic data (EXIF, Thumbnails).  
3. **Deploy**: Hugo builds the site. The gallery modal will automatically show "Purchase" or "License" buttons if the data exists for that specific image.

## **4\. Local Testing**

To test the commerce links:

1. Ensure you have a config.json uploaded to GCS.  
2. Run the sync engine locally: python scripts/sync\_engine.py \--mode public  
3. Run Hugo: hugo server