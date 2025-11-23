# CODE GENERATION TASK: HUGO STATIC SITE FOR WRITING PROJECTS



**GOAL:** Generate all necessary files and content for a Hugo Static Site Generator (SSG) project. The site must be optimized for writing articles, managing associated photo collections, and deploying as static files to a Google Cloud Storage (GCS) bucket.



**TECHNOLOGY CONSTRAINTS:**

1.  **SSG:** Hugo (v0.120+ or newer assumed).

2.  **Language/Styling:** Plain HTML, CSS, and Go Templates (Hugo's template language). Use Tailwind CSS utility classes within the HTML templates for modern, responsive styling.

3.  **Image Optimization:** MUST use **Hugo Pipes** within a custom Shortcode to handle image resizing, quality compression, and conversion (e.g., to WebP) for performance.



---



## 1. PROJECT STRUCTURE & CONFIGURATION



### A. File Structure



Create the following essential directories and configuration file:



* `config.toml`

* `layouts/_default/`

* `layouts/shortcodes/`

* `content/projects/`

* `static/`

* `assets/`



### B. `config.toml` (Configuration)



Generate a complete `config.toml` file.



* **Base URL:** Set a placeholder (e.g., `baseURL = "http://example.com/"`).

* **Title:** "My Writing & Photography Portfolio"

* **Taxonomies:** Define a `projects` taxonomy (for the main project collection).

* **Hugo Settings:** Include settings to enable `markup.goldmark.renderer.unsafe = true` to allow necessary HTML rendering (like the gallery).



---



## 2. TEMPLATES AND LAYOUTS



### A. `baseof.html` (Main Layout)



Create the main layout file.



* Include the standard HTML5 structure, a `<head>` section, and the necessary `<script src="https://cdn.tailwindcss.com"></script>` link for styling.

* Use `block` directives for `main` content, `title`, and `css`.

* Ensure the site is fully responsive using Tailwind classes.



### B. `single.html` (Article Layout)



Create the default single page layout (`layouts/_default/single.html`). This will be used for displaying individual articles.



* Display the article title, publication date, and main content (`{{ .Content }}`).

* Ensure the layout is clean, readable, and centers the text content for a good writing experience.

* The content area must be prepared to seamlessly display the embedded gallery shortcode.



---



## 3. CORE FEATURE: THE GALLERY SHORTCODE



Create the custom shortcode file to handle the image collection and optimization.



### A. `gallery.html` (Shortcode)



Generate a complete shortcode file (`layouts/shortcodes/gallery.html`) that performs the following steps:



1.  **Access Resources:** Get all page resources (images) within the article's "Page Bundle" folder.

2.  **Image Processing (Hugo Pipes):** For each image:

    * Resize the image to a consistent thumbnail size (e.g., 300x300 pixels, smart cropped).

    * Compress the image quality.

    * The processed image should be linked to the full-size original.

3.  **HTML Output:** Render the images in a responsive grid using Tailwind CSS (e.g., `grid grid-cols-2 md:grid-cols-3 gap-4`).

4.  **Interactive Elements:** Use simple HTML/CSS (no external JS libraries needed) to provide a light-box-like effect when the thumbnail is clicked, showing the full-size image in a modal overlay.



---



## 4. EXAMPLE CONTENT (FOR DEMONSTRATION)



Create an example "Project" and "Article" using the mandatory Page Bundle structure.



### A. Project Structure



Create the following file path (this represents a new Project landing page):



* `content/projects/_index.md` (List of all projects)

    * **Content:** Add a simple header and list the example project below.



### B. Article Page Bundle



Create a specific directory structure for a sample article with photos:



* `content/projects/south-america-trip/the-andes-ascent/`

    * `index.md` (The article content)

    * `andes-01.jpg` (Placeholder image)

    * `andes-02.jpg` (Placeholder image)

    * `andes-03.jpg` (Placeholder image)



### C. Example Article Content (`index.md`)



Generate the content for the sample article:



* **Front Matter:** Include `title`, `date`, and a simple `description`.

* **Body Content:** Write 2-3 paragraphs of example text.

* **Gallery Inclusion:** Embed the custom gallery shortcode within the body content, ensuring it targets the local images.

    * **Placeholder Images:** Use simple, accessible placeholder URLs for the images (e.g., from `placehold.co`). The Shortcode MUST still process these as if they were local image resources for the purpose of the template logic.



---



## 5. DEPLOYMENT INSTRUCTIONS (GCS)



The final generated output is the `public/` directory after running `hugo build`.



**Instruction to User:** Explain briefly that the final step for the user is to upload the entire contents of the `public/` folder to their Google Cloud Storage bucket using the `gsutil` command:



`gsutil -m rsync -r public/ gs://your-bucket-name`



---



**FINAL OUTPUT REQUIREMENT:** Generate the code for the following files:



1.  `config.toml`

2.  `layouts/_default/baseof.html`

3.  `layouts/_default/single.html`

4.  `layouts/shortcodes/gallery.html`

5.  `content/projects/_index.md`

6.  `content/projects/south-america-trip/the-andes-ascent/index.md`
