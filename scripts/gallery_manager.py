import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# --- Configuration ---
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_CONFIG = {
    "title": "",
    "story": "",
    "visibility": "public",
    "sort_by": "filename",
    "cover": "",
    "photos": {}
}

class GalleryManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gallery Configurator")
        self.root.geometry("900x600")

        self.current_folder = None
        self.config_data = DEFAULT_CONFIG.copy()
        self.image_files = []
        self.current_selection = None # 'gallery' or filename

        self._setup_ui()

    def _setup_ui(self):
        # --- Top Toolbar ---
        toolbar = tk.Frame(self.root, padx=10, pady=10, bg="#f0f0f0")
        toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_load = tk.Button(toolbar, text="📂 Open Gallery Folder", command=self.load_folder)
        btn_load.pack(side=tk.LEFT, padx=5)

        btn_save = tk.Button(toolbar, text="💾 Save config.json", command=self.save_config, bg="#dddddd")
        btn_save.pack(side=tk.LEFT, padx=5)

        self.lbl_path = tk.Label(toolbar, text="No folder selected", fg="gray", bg="#f0f0f0")
        self.lbl_path.pack(side=tk.LEFT, padx=15)

        # --- Main Layout (PanedWindow) ---
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- LEFT SIDE: Navigation ---
        frame_nav = tk.Frame(paned_window, width=250)
        paned_window.add(frame_nav)

        tk.Label(frame_nav, text="Items", font=("Arial", 10, "bold")).pack(anchor="w")
        
        self.listbox = tk.Listbox(frame_nav, selectmode=tk.SINGLE, font=("Arial", 11))
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        # --- RIGHT SIDE: Editor ---
        self.frame_editor = tk.Frame(paned_window, bg="white", padx=20, pady=20)
        paned_window.add(self.frame_editor)

        # We will dynamically clear/rebuild this frame based on selection
        self.lbl_editor_title = tk.Label(self.frame_editor, text="Select an item to edit", font=("Arial", 14, "bold"), bg="white")
        self.lbl_editor_title.pack(anchor="w", pady=(0, 15))

        self.editor_container = tk.Frame(self.frame_editor, bg="white")
        self.editor_container.pack(fill=tk.BOTH, expand=True)

    def load_folder(self):
        folder_path = filedialog.askdirectory()
        if not folder_path:
            return

        self.current_folder = folder_path
        self.lbl_path.config(text=self.current_folder)
        self.config_data = DEFAULT_CONFIG.copy() # Reset
        self.image_files = []

        # 1. Scan for Images
        try:
            for f in os.listdir(folder_path):
                if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                    if not f.endswith("_WM.jpg"): # Optional: skip watermarked if you edit originals
                         self.image_files.append(f)
                    else:
                        # If you ONLY have _WM files locally, include them. 
                        # Adjust logic based on your workflow. 
                        # For now, I'll include everything.
                        self.image_files.append(f)
            self.image_files.sort()
        except Exception as e:
            messagebox.showerror("Error", f"Could not scan folder: {e}")
            return

        # 2. Load existing config.json if exists
        config_path = os.path.join(folder_path, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    loaded = json.load(f)
                    # Merge loaded data into defaults to ensure all keys exist
                    self.config_data.update(loaded)
                    # Ensure photos dict exists
                    if "photos" not in self.config_data:
                        self.config_data["photos"] = {}
            except Exception as e:
                messagebox.showwarning("Warning", f"Corrupt config.json found. Starting fresh.\nError: {e}")

        # 3. Populate Listbox
        self.listbox.delete(0, tk.END)
        self.listbox.insert(tk.END, "Gallery Settings (Global)")
        for img in self.image_files:
            self.listbox.insert(tk.END, img)

        # Select first item
        self.listbox.selection_set(0)
        self.on_select(None)

    def on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        # Save previous input before switching? 
        # For simplicity, we bind inputs to variables that update immediately.
        
        # Clear Editor
        for widget in self.editor_container.winfo_children():
            widget.destroy()

        if index == 0:
            self.current_selection = "gallery"
            self.build_gallery_form()
        else:
            filename = self.listbox.get(index)
            self.current_selection = filename
            self.build_photo_form(filename)

    # --- UI BUILDERS ---

    def build_gallery_form(self):
        self.lbl_editor_title.config(text="Gallery Settings")
        
        # Title
        self.create_label_entry("Gallery Title:", "title", self.config_data)

        # Story (Multiline)
        tk.Label(self.editor_container, text="Story / Description:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        txt_story = tk.Text(self.editor_container, height=4, width=50, font=("Arial", 10))
        txt_story.insert("1.0", self.config_data.get("story", ""))
        txt_story.pack(fill=tk.X, pady=5)
        # Bind text changes
        txt_story.bind("<KeyRelease>", lambda e: self.config_data.update({"story": txt_story.get("1.0", "end-1c")}))

        # Visibility (Radio)
        tk.Label(self.editor_container, text="Visibility:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.var_vis = tk.StringVar(value=self.config_data.get("visibility", "public"))
        
        frame_vis = tk.Frame(self.editor_container, bg="white")
        frame_vis.pack(anchor="w")
        tk.Radiobutton(frame_vis, text="Public", variable=self.var_vis, value="public", bg="white", 
                       command=lambda: self.config_data.update({"visibility": "public"})).pack(side=tk.LEFT)
        tk.Radiobutton(frame_vis, text="Private", variable=self.var_vis, value="private", bg="white",
                       command=lambda: self.config_data.update({"visibility": "private"})).pack(side=tk.LEFT)

        # Sort By (Dropdown)
        tk.Label(self.editor_container, text="Sort Photos By:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        sort_options = ["filename", "date", "random"]
        current_sort = self.config_data.get("sort_by", "filename")
        if current_sort not in sort_options: current_sort = "filename"
        
        self.var_sort = tk.StringVar(value=current_sort)
        dropdown = tk.OptionMenu(self.editor_container, self.var_sort, *sort_options, 
                                 command=lambda val: self.config_data.update({"sort_by": val}))
        dropdown.config(bg="white")
        dropdown.pack(anchor="w")

        # Cover
        self.create_label_entry("Cover Image URL (Optional):", "cover", self.config_data)

    def build_photo_form(self, filename):
        self.lbl_editor_title.config(text=f"Photo: {filename}")
        
        # Ensure dict exists for this photo
        if filename not in self.config_data["photos"]:
            self.config_data["photos"][filename] = {
                "title": "", "story": "", "product_id": "", "licensing": {"adobe": "", "getty": ""}
            }
        
        photo_data = self.config_data["photos"][filename]

        # Title
        self.create_label_entry("Photo Title:", "title", photo_data)

        # Story
        self.create_label_entry("Story / Caption:", "story", photo_data)

        # Product ID
        self.create_label_entry("Lemon Squeezy Product ID:", "product_id", photo_data)

        # Licensing Section
        tk.Label(self.editor_container, text="Licensing URLs:", bg="white", font=("Arial", 10, "bold")).pack(anchor="w", pady=(15, 5))
        
        frame_license = tk.Frame(self.editor_container, bg="#f9f9f9", padx=10, pady=10, relief=tk.RIDGE, bd=1)
        frame_license.pack(fill=tk.X)

        if "licensing" not in photo_data: photo_data["licensing"] = {}

        # Adobe Helper
        self.create_license_row(frame_license, "Adobe Stock", "adobe", photo_data["licensing"])
        # Getty Helper
        self.create_license_row(frame_license, "Getty Images", "getty", photo_data["licensing"])
        # Alamy Helper
        self