#!/usr/bin/env python3

import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, Radiobutton, IntVar, Label, Button, Entry, StringVar
from PIL import Image, ExifTags
from datetime import datetime, timedelta

# --- HELPER FUNCTIONS ---

def get_date_taken(filepath):
    """
    Extracts DateTimeOriginal from EXIF. Returns datetime object or None.
    """
    try:
        with Image.open(filepath) as img:
            exif_data = img._getexif()
            if not exif_data:
                return None
            
            for tag_id, value in exif_data.items():
                tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                if tag_name == 'DateTimeOriginal':
                    # EXIF date format is usually "YYYY:MM:DD HH:MM:SS"
                    return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
    except (IOError, ValueError, KeyError):
        return None
    return None

def ask_settings_gui():
    """
    Opens a GUI to ask for:
    1. Organization Mode
    2. Time Offset
    3. Session Gap
    Returns: (mode, offset_hours, session_gap)
    """
    root = tk.Tk()
    root.title("Photo Organizer Settings")
    
    # Center window
    w, h = 450, 480
    ws, hs = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = (ws/2) - (w/2), (hs/2) - (h/2)
    root.geometry(f'{int(w)}x{int(h)}+{int(x)}+{int(y)}')

    # --- Section 1: Mode Selection ---
    Label(root, text="1. Select Partition Method:", font=("Arial", 10, "bold")).pack(pady=(15, 5))
    
    selection = IntVar(value=3) # Default to Sessionized

    modes = [
        ("Date + Hour (e.g., 2023-10-27_1400)", 1),
        ("Date Only (e.g., 2023-10-27)", 2),
        ("Sessionized (Group by activity)", 3)
    ]

    for text, mode_val in modes:
        Radiobutton(root, text=text, variable=selection, value=mode_val).pack(anchor="w", padx=40)

    # --- Section 2: Timezone Offset ---
    Label(root, text="2. Timezone Correction (Hours to Add):", font=("Arial", 10, "bold")).pack(pady=(20, 5))
    Label(root, text="(LA to South Africa is usually 9 or 10)", font=("Arial", 8, "italic")).pack()
    
    offset_var = StringVar(value="0") 
    Entry(root, textvariable=offset_var, width=10, justify="center").pack(pady=5)

    # --- Section 3: Session Gap ---
    Label(root, text="3. Session Gap (For Method 3):", font=("Arial", 10, "bold")).pack(pady=(20, 5))
    Label(root, text="Create new folder if gap is greater than (hours):", font=("Arial", 8, "italic")).pack()

    gap_var = StringVar(value="3") # Default to 3 hours
    Entry(root, textvariable=gap_var, width=10, justify="center").pack(pady=5)

    def submit():
        root.quit()

    Button(root, text="Start Organization", command=submit, bg="#DDDDDD", height=2, width=20).pack(pady=30)

    root.mainloop()
    
    mode = selection.get()
    
    # Validation for Offset
    try:
        offset = float(offset_var.get())
    except ValueError:
        offset = 0.0
        
    # Validation for Gap
    try:
        gap = float(gap_var.get())
        if gap < 1: 
            gap = 1.0 # Enforce minimum logic if user types 0 or negative
    except ValueError:
        gap = 3.0 # Default fallback
        
    root.destroy()
    return mode, offset, gap

def select_folders():
    root = tk.Tk()
    root.withdraw()

    messagebox.showinfo("Step 1", "Select the SOURCE folder containing your images.")
    source = filedialog.askdirectory(title="Select Source Folder")
    if not source: return None, None

    messagebox.showinfo("Step 2", "Select the DESTINATION folder.")
    dest = filedialog.askdirectory(title="Select Destination Folder")
    if not dest: return None, None

    return source, dest

# --- CORE LOGIC ---

def process_photos():
    # 1. Get Settings (Mode, Offset, Gap)
    mode, offset_hours, gap_hours = ask_settings_gui()
    
    # 2. Get Folders
    source_folder, destination_folder = select_folders()
    if not source_folder or not destination_folder:
        return

    print(f"Scanning... applying {offset_hours}h offset. Session gap set to {gap_hours}h.")

    # 3. Scan, Shift Time, and Sort
    valid_images = [] 
    no_exif_files = [] 

    for filename in os.listdir(source_folder):
        full_path = os.path.join(source_folder, filename)
        
        if not os.path.isfile(full_path) or not filename.lower().endswith(('.jpg', '.jpeg')):
            continue

        date_taken = get_date_taken(full_path)
        
        if date_taken:
            # Apply Timezone Shift
            local_date_taken = date_taken + timedelta(hours=offset_hours)
            valid_images.append((filename, full_path, local_date_taken))
        else:
            no_exif_files.append((filename, full_path))

    # Sort by the NEW local time
    valid_images.sort(key=lambda x: x[2])

    # 4. Determine Groupings
    copy_operations = []

    if mode == 1: # Date + Hour
        for fname, fpath, date_obj in valid_images:
            folder_name = date_obj.strftime('%Y-%m-%d_%H00')
            copy_operations.append((fpath, os.path.join(destination_folder, folder_name, fname)))

    elif mode == 2: # Date Only
        for fname, fpath, date_obj in valid_images:
            folder_name = date_obj.strftime('%Y-%m-%d')
            copy_operations.append((fpath, os.path.join(destination_folder, folder_name, fname)))

    elif mode == 3: # Sessionized
        if valid_images:
            # Initialize first session
            current_session_start = valid_images[0][2]
            current_folder_name = current_session_start.strftime('Session_%Y-%m-%d_%H:00')
            
            # Add first image
            first_fname, first_path, _ = valid_images[0]
            copy_operations.append((first_path, os.path.join(destination_folder, current_folder_name, first_fname)))
            
            # Loop through rest
            for i in range(1, len(valid_images)):
                prev_date = valid_images[i-1][2]
                curr_date = valid_images[i][2]
                fname = valid_images[i][0]
                fpath = valid_images[i][1]

                # Check gap using user-defined gap_hours
                if (curr_date - prev_date) > timedelta(hours=gap_hours):
                    # Start new session
                    current_folder_name = curr_date.strftime('Session_%Y-%m-%d_%H:00')
                
                copy_operations.append((fpath, os.path.join(destination_folder, current_folder_name, fname)))

    # 5. Handle No EXIF
    for fname, fpath in no_exif_files:
        copy_operations.append((fpath, os.path.join(destination_folder, "No_EXIF_Data", fname)))

    # 6. Execute Copies
    root = tk.Tk()
    root.withdraw()
    
    count_moved = 0
    total = len(copy_operations)
    
    print(f"Copying {total} files...")

    for src, dst in copy_operations:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            count_moved += 1
            if count_moved % 10 == 0: print(f"Processed {count_moved}/{total}...")
    
    msg = (f"Organization Complete!\n\n"
           f"Photos Processed: {count_moved}\n"
           f"Mode: {mode}\n"
           f"Timezone Offset: {offset_hours} hours\n"
           f"Session Gap: {gap_hours} hours")
    
    print(msg)
    messagebox.showinfo("Success", msg)

if __name__ == "__main__":
    process_photos()