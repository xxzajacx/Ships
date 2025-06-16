from PIL import Image, ImageDraw
import os
import random

def generate_image(size, color, filename):
    """Generuje jednokolorowy obrazek PNG."""
    img = Image.new('RGB', size, color)
    img.save(filename)

def generate_ship_part(size, color, filename):
    """Generuje część statku (prostokąt)."""
    img = Image.new('RGB', size, (255, 255, 255)) # Białe tło
    draw = ImageDraw.Draw(img)
    # Rysujemy wypełniony prostokąt, który będzie częścią statku
    # Używamy marginesów, aby był widoczny jako "część" komórki
    margin = 3
    draw.rectangle([margin, margin, size[0]-margin-1, size[1]-margin-1], fill=color, outline=(0, 0, 0))
    img.save(filename)

def generate_hit_mark(size, filename):
    """Generuje obrazek trafienia (czerwone tło z białym 'X')."""
    img = Image.new('RGB', size, (200, 0, 0)) # Czerwone tło
    draw = ImageDraw.Draw(img)
    draw.line((5, 5, size[0]-5, size[1]-5), fill=(255, 255, 255), width=3)
    draw.line((size[0]-5, 5, 5, size[1]-5), fill=(255, 255, 255), width=3)
    img.save(filename)

def generate_miss_mark(size, filename):
    """Generuje obrazek pudła (szare tło z białym 'O')."""
    img = Image.new('RGB', size, (100, 100, 100)) # Szare tło
    draw = ImageDraw.Draw(img)
    draw.ellipse((5, 5, size[0]-5, size[1]-5), outline=(255, 255, 255), width=3)
    img.save(filename)

def generate_explosion(size, filename):
    """Generuje obrazek eksplozji (pomarańczowo-czerwona kula ognia)."""
    img = Image.new('RGBA', size, (0, 0, 0, 0)) # Przezroczyste tło
    draw = ImageDraw.Draw(img)

    center_x, center_y = size[0] // 2, size[1] // 2
    radius = min(size) // 3

    # Główne kolory eksplozji
    colors = [(255, 100, 0, 255), (255, 50, 0, 255), (200, 0, 0, 255)]

    # Rysowanie rozbłysków
    for _ in range(5):
        splash_radius = random.randint(radius // 2, radius)
        fill_color = random.choice(colors)
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

def generate_water_splash(size, filename):
    """Generuje obrazek rozbryzgu wody (niebieskie kółka)."""
    img = Image.new('RGBA', size, (0, 0, 0, 0))  # Przezroczyste tło
    draw = ImageDraw.Draw(img)

    center_x, center_y = size[0] // 2, size[1] // 2
    base_radius = min(size) // 4

    colors = [(0, 150, 255, 200), (50, 180, 255, 150), (100, 200, 255, 100)] # Odcienie niebieskiego z przezroczystością

    # Rysowanie kilku kółek imitujących rozbryzg
    for i in range(3):
        current_radius = base_radius + i * (base_radius // 4)
        fill_color = colors[i]
        
        # Lekko losowe położenie dla każdego kółka
        offset_x = random.randint(-base_radius // 4, base_radius // 4)
        offset_y = random.randint(-base_radius // 4, base_radius // 4)
        
        draw.ellipse((center_x - current_radius + offset_x, center_y - current_radius + offset_y,
                      center_x + current_radius + offset_x, center_y + current_radius + offset_y),
                     fill=fill_color)
    img.save(filename)


assets_dir = "assets"
if not os.path.exists(assets_dir):
    os.makedirs(assets_dir)
    print(f"Utworzono katalog: {assets_dir}")

image_size = (40, 40) # Zwiększono rozmiar, aby pasował do cell_size w kliencie

print("Generowanie grafik...")

# Generowanie podstawowych obrazków
generate_image(image_size, (100, 150, 255), os.path.join(assets_dir, "sea.png")) # Jasny niebieski
generate_ship_part(image_size, (70, 70, 70), os.path.join(assets_dir, "ship_part_horizontal.png")) # Ciemnoszary
generate_ship_part(image_size, (70, 70, 70), os.path.join(assets_dir, "ship_part_vertical.png")) # Ciemnoszary (dla pionowych)
generate_hit_mark(image_size, os.path.join(assets_dir, "hit_mark.png")) # Czerwony X
generate_miss_mark(image_size, os.path.join(assets_dir, "miss_mark.png")) # Szare kółko
generate_explosion(image_size, os.path.join(assets_dir, "explosion.png")) # Eksplozja
generate_water_splash(image_size, os.path.join(assets_dir, "water_splash.png")) # Rozbryzg wody

print("Generowanie zakończone.")