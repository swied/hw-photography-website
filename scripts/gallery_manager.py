#!/usr/bin/env python3
import os
import json
import sys

# --- CROSS-PLATFORM COMPATIBILITY CHECK ---
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    print("\n❌ CRITICAL ERROR: 'tkinter' library not found.")
    print("------------------------------------------------")
    print("To fix this on Ubuntu/Debian, open Terminal and run:")
    print("    sudo apt-get install python3-tk")
    print("------------------------------------------------\n")
    sys.exit(1)

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
        self.current_selection = None 

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

        # --- Main Layout ---
        paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- LEFT SIDE: Navigation ---
        frame_nav = tk.Frame(paned_window, width=250)
        paned_window.add(frame_nav)

        tk.Label(frame_nav, text="Items", font=("Helvetica", 10, "bold")).pack(anchor="w")
        
        self.listbox = tk.Listbox(frame_nav, selectmode=tk.SINGLE, font=("Helvetica", 11))
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        # --- RIGHT SIDE: Editor ---
        self.frame_editor = tk.Frame(paned_window, bg="white", padx=20, pady=20)
        paned_window.add(self.frame_editor)

        self.lbl_editor_title = tk.Label(self.frame_editor, text="Select an item to edit", font=("Helvetica", 14, "bold"), bg="white")
        self.lbl_editor_title.pack(anchor="w", pady=(0, 15))

        self.editor_container = tk.Frame(self.frame_editor, bg="white")
        self.editor_container.pack(fill=tk.BOTH, expand=True)

    def load_folder(self):
# 1. Construct the cross-platform path to ~/Pictures
        home_dir = os.path.expanduser("~")
        pictures_path = os.path.join(home_dir, "Pictures")

        # 2. Open the dialog starting at Pictures (if it exists, otherwise defaults to home)
        if not os.path.exists(pictures_path):
            pictures_path = home_dir

        folder_path = filedialog.askdirectory(initialdir=pictures_path)
        
        if not folder_path:
            return

        self.current_folder = folder_path
        self.lbl_path.config(text=self.current_folder)
        self.config_data = DEFAULT_CONFIG.copy()
        self.image_files = []

        try:
            for f in os.listdir(folder_path):
                if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                    self.image_files.append(f)
            self.image_files.sort()
        except Exception as e:
            messagebox.showerror("Error", f"Could not scan folder: {e}")
            return

        # Load existing config
        config_path = os.path.join(folder_path, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    loaded = json.load(f)
                    self.config_data.update(loaded)
                    if "photos" not in self.config_data:
                        self.config_data["photos"] = {}
            except Exception as e:
                messagebox.showwarning("Warning", f"Corrupt config.json found.\nError: {e}")

        # Populate Listbox
        self.listbox.delete(0, tk.END)
        self.listbox.insert(tk.END, "Gallery Settings (Global)")
        for img in self.image_files:
            self.listbox.insert(tk.END, img)

        self.listbox.selection_set(0)
        self.on_select(None)

    def on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return

        index = selection[0]
        for widget in self.editor_container.winfo_children():
            widget.destroy()

        if index == 0:
            self.current_selection = "gallery"
            self.build_gallery_form()
        else:
            filename = self.listbox.get(index)
            self.current_selection = filename
            self.build_photo_form(filename)

    def build_gallery_form(self):
        self.lbl_editor_title.config(text="Gallery Settings")
        
        self.create_label_entry("Gallery Title:", "title", self.config_data)

        tk.Label(self.editor_container, text="Story / Description:", bg="white", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(10, 0))
        txt_story = tk.Text(self.editor_container, height=4, width=50, font=("Helvetica", 10))
        txt_story.insert("1.0", self.config_data.get("story", ""))
        txt_story.pack(fill=tk.X, pady=5)
        txt_story.bind("<KeyRelease>", lambda e: self.config_data.update({"story": txt_story.get("1.0", "end-1c")}))

        tk.Label(self.editor_container, text="Visibility:", bg="white", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.var_vis = tk.StringVar(value=self.config_data.get("visibility", "public"))
        
        frame_vis = tk.Frame(self.editor_container, bg="white")
        frame_vis.pack(anchor="w")
        tk.Radiobutton(frame_vis, text="Public", variable=self.var_vis, value="public", bg="white", 
                       command=lambda: self.config_data.update({"visibility": "public"})).pack(side=tk.LEFT)
        tk.Radiobutton(frame_vis, text="Private", variable=self.var_vis, value="private", bg="white",
                       command=lambda: self.config_data.update({"visibility": "private"})).pack(side=tk.LEFT)

        tk.Label(self.editor_container, text="Sort Photos By:", bg="white", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(10, 0))
        sort_options = ["date", "filename", "random"]
        current_sort = self.config_data.get("sort_by", "date")
        if current_sort not in sort_options: current_sort = "filename"
        
        self.var_sort = tk.StringVar(value=current_sort)
        dropdown = tk.OptionMenu(self.editor_container, self.var_sort, *sort_options, 
                                 command=lambda val: self.config_data.update({"sort_by": val}))
        dropdown.config(bg="white")
        dropdown.pack(anchor="w")

        self.create_label_entry("Cover Image URL (Optional):", "cover", self.config_data)

    def build_photo_form(self, filename):
        self.lbl_editor_title.config(text=f"Photo: {filename}")
        
        if filename not in self.config_data["photos"]:
            self.config_data["photos"][filename] = {
                "title": "", "story": "", "product_id": "", "licensing": {"adobe": "", "getty": ""}
            }
        
        photo_data = self.config_data["photos"][filename]

        self.create_label_entry("Photo Title:", "title", photo_data)
        self.create_label_entry("Story / Caption:", "story", photo_data)
        self.create_label_entry("Lemon Squeezy Product ID:", "product_id", photo_data)

        tk.Label(self.editor_container, text="Licensing URLs:", bg="white", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(15, 5))
        
        frame_license = tk.Frame(self.editor_container, bg="#f9f9f9", padx=10, pady=10, relief=tk.RIDGE, bd=1)
        frame_license.pack(fill=tk.X)

        if "licensing" not in photo_data: photo_data["licensing"] = {}

        self.create_license_row(frame_license, "Adobe Stock", "adobe", photo_data["licensing"])
        self.create_license_row(frame_license, "Getty Images", "getty", photo_data["licensing"])
        self.create_license_row(frame_license, "Alamy", "alamy", photo_data["licensing"])
        self.create_license_row(frame_license, "Shutter Stock", "shutterstock", photo_data["licensing"])

    def create_label_entry(self, label_text, key, data_dict):
        tk.Label(self.editor_container, text=label_text, bg="white", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(10, 0))
        var = tk.StringVar(value=data_dict.get(key, ""))
        entry = tk.Entry(self.editor_container, textvariable=var, font=("Helvetica", 10))
        entry.pack(fill=tk.X, pady=2)
        var.trace_add("write", lambda *args: data_dict.update({key: var.get()}))

    def create_license_row(self, parent, label, key, license_dict):
        f = tk.Frame(parent, bg="#f9f9f9")
        f.pack(fill=tk.X, pady=2)
        tk.Label(f, text=label, width=12, anchor="w", bg="#f9f9f9").pack(side=tk.LEFT)
        
        var = tk.StringVar(value=license_dict.get(key, ""))
        entry = tk.Entry(f, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def update_license(*args):
            val = var.get().strip()
            if val:
                license_dict[key] = val
            else:
                if key in license_dict: del license_dict[key]
        
        var.trace_add("write", update_license)

    def save_config(self):
        if not self.current_folder:
            messagebox.showwarning("Warning", "Please open a folder first.")
            return

        out_path = os.path.join(self.current_folder, "config.json")
        try:
            with open(out_path, "w") as f:
                json.dump(self.config_data, f, indent=4)
            messagebox.showinfo("Success", f"Saved config.json to\n{self.current_folder}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = GalleryManagerApp(root)
    root.mainloop()