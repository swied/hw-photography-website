# **Step-by-Step Build Guide**

Since this is a hybrid architecture (Python Logic \+ Hugo Frontend), you need to run things in a specific order.

## **Prerequisites**

1. **Hugo (Extended Version):**  
   * Mac: brew install hugo  
   * Windows: choco install hugo-extended  
   * Verify: Run hugo version (Ensure it says "extended").  
2. **Python 3.9+:**  
   * Verify: Run python \--version or python3 \--version.

## **Phase 1: Install Dependencies**

Open your terminal (Command Prompt or Terminal) and navigate to your project folder.

1. **Install Python Libraries** (for the Sync Engine):  
   pip install google-cloud-storage Pillow

## **Phase 2: Generate Data (The "Chicken and Egg" Step)**

Hugo cannot build the site until site/data/photos.json exists. You have two options:

### **Option A: Use Mock Data (Recommended for first run)**

If you haven't set up your Google Cloud Bucket yet, I have provided a sample site/data/photos.json file below. Ensure this file exists in your folder structure.

### **Option B: Use Real Data (If GCS is ready)**

If you have your Google Cloud Storage bucket set up with images:

1. Authenticate:  
   gcloud auth application-default login

2. Run the Sync Engine:  
   \# Replace with your actual bucket name  
   export GCS\_BUCKET\_NAME="your-actual-bucket-name"  
   python scripts/sync\_engine.py \--mode admin

## **Phase 3: Run the Local Server**

Now that the data exists, start Hugo.

1. Navigate to the site folder:  
   cd site

2. Start the server:  
   hugo server \-D

   * \-D ensures "draft" content is visible if you have any.  
3. Open your browser to: http://localhost:1313/

## **Phase 4: Production Build**

When you are ready to deploy to GitHub Pages manually or check the final output:

1. Run the minify command:  
   hugo \--minify

2. The generated website will be in the public/ folder.