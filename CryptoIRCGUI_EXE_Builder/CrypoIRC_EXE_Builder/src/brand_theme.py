"""NOCTURNE visual assets. Branding imagery is never a network-status indicator."""
from pathlib import Path
from tkinter import PhotoImage
try:
    from PIL import Image,ImageTk
except ImportError:
    Image=ImageTk=None

ASSET_DIR=Path(__file__).resolve().parent/'brand_assets'
PURPLE='#b363ff'
GREEN='#47fca3'
RED='#ff707a'

def load_image(filename, size):
    """Return a Tk PhotoImage, or None if Pillow/assets are unavailable."""
    path=ASSET_DIR/filename
    if Image is None or not path.is_file():
        return None
    with Image.open(path) as picture:
        resized=picture.convert('RGBA').resize(size,Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(resized)
