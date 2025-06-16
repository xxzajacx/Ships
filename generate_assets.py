from PIL import Image, ImageDraw
import os

def generate_image(size, color, filename):
    """Generuje jednokolorowy obrazek PNG."""
    img = Image.new('RGB', size, color)
    img.save(filename)

def generate_ship_part(size, color, filename, orientation="horizontal"):
    """Generuje część statku (prostokąt)."""
    img = Image.new('RGB', size, (255, 255, 255)) # Białe tło
    draw = ImageDraw.Draw(img)
    # Rysujemy prostokąt, który będzie częścią statku
    draw.rectangle([2, 2, size[0]-3, size[1]-3], fill=color, outline=(0, 0, 0))
    img.save(filename)

def generate_hit_mark(size, filename):
    """Generuje obrazek trafienia (czerwone tło z białym 'X')."""
    img = Image.new('RGB', size, (200, 0, 0)) # Czerwone tło
    draw = ImageDraw.Draw(img)
    draw.line((5, 5, size[0]-5, size[1]-5), fill=(255, 255, 255), width=3)
    draw.line((size[0]-5, 5, 5, size[1]-5), fill=(255, 255, 255), width=3)
    img.save(filename)

def generate_miss_mark(size, filename):
    """Generuje obrazek pudła (białe tło z niebieskim 'O')."""
    img = Image.new('RGB', size, (255, 255, 255)) # Białe tło
    draw = ImageDraw.Draw(img)
    draw.ellipse((5, 5, size[0]-5, size[1]-5), fill=(0, 0, 150), outline=(0, 0, 0))
    img.save(filename)

def generate_explosion_frame(size, frame_number, total_frames, filename):
    """Generuje pojedynczą ramkę animacji wybuchu."""
    img = Image.new('RGBA', size, (0, 0, 0, 0)) # Przezroczyste tło
    draw = ImageDraw.Draw(img)

    # Stopniowe powiększanie "ognia"
    max_radius = min(size) // 2 - 2
    radius = int(max_radius * (frame_number / total_frames))

    # Kolory od żółtego do czerwonego
    r = min(255, int(255 * (frame_number / total_frames)))
    g = max(0, 255 - int(255 * (frame_number / total_frames)))
    b = 0
    fill_color = (r, g, b, 255)

    center_x, center_y = size[0] // 2, size[1] // 2

    # Rysuj "plamy" dla efektu ognia
    num_splashes = 5 # Liczba losowych plam
    for _ in range(num_splashes):
        splash_radius = radius * 0.7 + random.randint(0, radius // 2)
        splash_center_x = center_x + random.randint(-radius // 2, radius // 2)
        splash_center_y = center_y + random.randint(-radius // 2, radius // 2)
        draw.ellipse((splash_center_x - splash_radius, splash_center_y - splash_radius,
                      splash_center_x + splash_radius, splash_center_y + splash_radius),
                     fill=fill_color)

    # Główna kula ognia
    draw.ellipse((center_x - radius, center_y - radius,
                  center_x + radius, center_y + radius),
                 fill=fill_color)

    img.save(filename)

import random # Dodaj import random na początku pliku

assets_dir = "assets"
if not os.path.exists(assets_dir):
    os.makedirs(assets_dir)
    print(f"Utworzono katalog: {assets_dir}")

image_size = (30, 30)

print("Generowanie grafik...")

# Generowanie podstawowych obrazków
generate_image(image_size, (100, 150, 255), os.path.join(assets_dir, "sea.png")) # Jasny niebieski
generate_ship_part(image_size, (70, 70, 70), os.path.join(assets_dir, "ship_part_horizontal.png")) # Ciemnoszary
generate_ship_part(image_size, (70, 70, 70), os.path.join(assets_dir, "ship_part_vertical.png")) # Ciemnoszary (dla pionowych)
generate_hit_mark(image_size, os.path.join(assets_dir, "hit.png"))
generate_miss_mark(image_size, os.path.join(assets_dir, "miss.png"))

# Generowanie ramek wybuchu
num_explosion_frames = 9
for i in range(1, num_explosion_frames + 1):
    generate_explosion_frame(image_size, i, num_explosion_frames, os.path.join(assets_dir, f"explosion_frame_{i:02d}.png"))

print("Generowanie zakończone! Pliki są w folderze 'assets'.")