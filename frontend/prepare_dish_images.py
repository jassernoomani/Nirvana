"""Optimize generated assets and create a review sheet, using Pillow."""
import json
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).parent
manifest = json.loads((root / 'dish-image-manifest.json').read_text())
output = root / 'public/assets/dishes'
output.mkdir(parents=True, exist_ok=True)
sheet = Image.new('RGB', (1200, 5 * 170), '#fffaf0')
draw = ImageDraw.Draw(sheet)
for index, entry in enumerate(manifest):
    with Image.open(entry['source']) as source:
        image = source.convert('RGB')
    image.thumbnail((960, 640), Image.Resampling.LANCZOS)
    image.save(output / f"dish-{entry['id']}.webp", 'WEBP', quality=86)
    thumb = image.copy()
    thumb.thumbnail((190, 135), Image.Resampling.LANCZOS)
    x, y = (index % 6) * 200, (index // 6) * 170
    sheet.paste(thumb, (x, y))
    draw.text((x + 5, y + 139), f"{entry['id']}: {entry['name'][:26]}", fill='#29462f')
sheet.save(root / 'dish-images-review.jpg')
print(f"Prepared {len(manifest)} local WebP assets.")
