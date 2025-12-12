import os
import sys
import shutil
import unicodedata

# For "press any key" functionality
try:
    import msvcrt
except ImportError:
    msvcrt = None

# === CONFIG ===
DRY_RUN = False

def wait_for_key():
    """Wait for any key press"""
    if msvcrt:
        msvcrt.getch()
    else:
        input()

def normalize_name(name):
    """Normalize unicode and lowercase for comparison."""
    name = unicodedata.normalize('NFKD', name)
    return ''.join(c for c in name if not unicodedata.combining(c)).lower()

def extract_primary_artist(artist_string):
    """Extract the primary artist from collaborations (before &, feat, Vs, +, x, etc)."""
    # Split on common collaboration separators (ordered by specificity to avoid false matches)
    separators = [
        ' feat. ', ' feat ', ' featuring ', ' Featuring ',
        ' ft. ', ' Ft. ', ' ft ', ' Ft ',
        ' vs. ', ' vs ', ' Vs. ', ' Vs ', ' VS ',
        ' with ', ' With ',
        ' and ', ' And ',
        ' & ',
        ' · ',
        ' x ',
        ' X ',
        ' + ',
        ', '
    ]
    
    for sep in separators:
        if sep in artist_string:
            return artist_string.split(sep)[0].strip()
    
    return artist_string.strip()

def sanitize(name):
    """Replace forbidden Windows characters."""
    for c in r'<>:"/\|?*':
        name = name.replace(c, "_")
    # Don't use strip() as it removes trailing dots which are valid in folder names
    # Just strip spaces
    return name.strip(' ')

def get_unique_path(path):
    """Add (N) suffix if path exists."""
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return path
    
    base_dir = os.path.dirname(path)
    base_name = os.path.basename(path)
    
    counter = 1
    while True:
        new_name = f"{base_name} ({counter})"
        new_path = os.path.join(base_dir, new_name)
        if not os.path.exists(new_path):
            return new_path
        counter += 1

def find_all_folders(root):
    """Recursively find all folders at any depth that match 'Artist - Album' pattern."""
    matching_folders = []
    
    for dirpath, dirnames, filenames in os.walk(root):
        for dirname in dirnames:
            if " - " in dirname:
                full_path = os.path.join(dirpath, dirname)
                matching_folders.append(full_path)
    
    return matching_folders

def preview_moves(all_folders, artists, artist_albums, move_single_albums, root):
    """Show preview of which folders will be moved and return the moves list."""
    moves = []
    skipped = []
    
    for folder_path in all_folders:
        folder = os.path.basename(folder_path)
        parts = folder.split(" - ", 1)
        if len(parts) != 2:
            skipped.append((folder, "no artist separator"))
            continue
        
        artist = parts[0].strip()
        primary_artist = extract_primary_artist(artist)
        norm = normalize_name(primary_artist)
        target_artist = artists[norm]
        
        # Skip single-album artists if option 2 was chosen
        if not move_single_albums and len(artist_albums[norm]) == 1:
            skipped.append((folder, "single album - keeping as-is"))
            continue
        
        target_folder = os.path.join(root, sanitize(target_artist))
        src = folder_path
        dst = os.path.join(target_folder, sanitize(folder))
        
        # Get the current parent folder name
        current_parent = os.path.basename(os.path.dirname(src))
        
        # Normalize paths for comparison - Windows treats trailing dots specially
        # "E.L.I." and "E.L.I" are the same folder in Windows
        src_parent = os.path.normpath(os.path.dirname(src)).rstrip('.')
        target_folder_norm = os.path.normpath(target_folder).rstrip('.')
        
        # Also check if source parent folder name matches target artist (handles dots, etc)
        src_parent_name = os.path.basename(os.path.dirname(src)).rstrip('.')
        target_artist_sanitized = sanitize(target_artist).rstrip('.')
        
        # Check if the album artist matches the current parent folder name
        # This handles cases like "Artist & Collab" albums already in "Artist & Collab" folder
        album_artist_norm = normalize_name(artist)
        parent_norm = normalize_name(current_parent)
        
        # Skip if already in correct location OR if album artist matches parent folder
        if (src_parent == target_folder_norm or 
            src_parent_name == target_artist_sanitized or
            album_artist_norm == parent_norm):
            skipped.append((folder, "already organized"))
            continue
        
        # Relative paths for display
        src_rel = os.path.relpath(src, root)
        dst_rel = os.path.relpath(dst, root)
        
        moves.append((src, dst, target_artist, folder, src_rel, dst_rel))
    
    # Only show preview if there are folders to move
    if moves:
        print("\n" + "="*60)
        print("FOLDERS THAT WILL BE MOVED:")
        print("="*60 + "\n")
        
        for src, dst, target_artist, folder, src_rel, dst_rel in moves:
            print(f"  {src_rel}")
            print(f"  -> {dst_rel}\n")
    
    print(f"\n{'='*60}")
    print(f"Total folders to move: {len(moves)}")
    if skipped:
        already_organized = sum(1 for _, reason in skipped if reason == "already organized")
        if already_organized > 0:
            print(f"Already organized (will skip): {already_organized}")
    print(f"{'='*60}\n")
    
    return moves

# --- Main Logic ---
if len(sys.argv) < 2:
    print("Drag and drop a folder onto this script.")
    print("Press any key to exit...")
    wait_for_key()
    exit(1)

ROOT = sys.argv[1]

if not os.path.isdir(ROOT):
    print(f"Not a valid directory: {ROOT}")
    print("Press any key to exit...")
    wait_for_key()
    exit(1)

print(f"Scanning: {ROOT}\n")
print("Finding folders with 'Artist - Album' pattern at all depths...\n")

# Find all matching folders at any depth
all_folders = find_all_folders(ROOT)

if not all_folders:
    print("No folders found matching 'Artist - Album' pattern.")
    print("Press any key to exit...")
    wait_for_key()
    exit(0)

print(f"Found {len(all_folders)} folders to organize\n")

# Collect canonical artist names and count albums per artist
artists = {}
artist_albums = {}

for folder_path in all_folders:
    folder = os.path.basename(folder_path)
    parts = folder.split(" - ", 1)
    if len(parts) != 2:
        continue
    
    artist = parts[0].strip()
    primary_artist = extract_primary_artist(artist)
    norm = normalize_name(primary_artist)
    
    # Keep version with most uppercase (likely "proper" casing)
    if norm not in artists or sum(c.isupper() for c in primary_artist) > sum(c.isupper() for c in artists[norm]):
        artists[norm] = primary_artist
    
    # Count albums per artist
    if norm not in artist_albums:
        artist_albums[norm] = []
    artist_albums[norm].append(folder_path)

# Count single-album artists
single_album_count = sum(1 for albums in artist_albums.values() if len(albums) == 1)

if single_album_count > 0:
    print(f"{single_album_count} artist(s) have only one album\n")
    print("Choose an option:")
    print("1. Move all folders to artist subfolders")
    print("2. Move only artists with multiple albums (keep single-album artists as-is)")
    print()
    
    while True:
        choice = input("Enter your choice (1 or 2): ").strip()
        if choice in ["1", "2"]:
            break
        print("\nInvalid choice. Please enter 1 or 2.\n")
    
    move_single_albums = (choice == "1")
else:
    move_single_albums = True

# Show preview of moves
moves = preview_moves(all_folders, artists, artist_albums, move_single_albums, ROOT)

if not moves:
    print("Nothing to move! All folders are already organized.")
    print("Press any key to exit...")
    wait_for_key()
    exit(0)

# Confirm before proceeding
confirm = input("Proceed with moving folders? (y/n): ").strip().lower()
if confirm != 'y':
    print("Operation cancelled.")
    print("Press any key to exit...")
    wait_for_key()
    exit(0)

# Process folders
print("\nProcessing...\n")
success_count = 0
error_count = 0

for src, dst, target_artist, folder, src_rel, dst_rel in moves:
    target_folder = os.path.dirname(dst)
    
    # Create artist folder
    if not os.path.exists(target_folder):
        print(f"Creating: {sanitize(target_artist)}/")
        try:
            os.makedirs(target_folder, exist_ok=True)
        except Exception as e:
            print(f"  Error creating folder: {e}\n")
            error_count += 1
            continue
    
    # Move folder
    print(f"Moving: {src_rel}")
    try:
        dst_unique = get_unique_path(dst)
        shutil.move(src, dst_unique)
        print(f"  -> {os.path.relpath(dst_unique, ROOT)}")
        print(f"  Success!\n")
        success_count += 1
    except Exception as e:
        print(f"  Error: {e}\n")
        error_count += 1

print(f"\n{'='*60}")
print(f"Successfully moved: {success_count}")
print(f"Errors: {error_count}")
print(f"{'='*60}\n")

print("Done!")
print("Press any key to exit...")
wait_for_key()
