import pygame
import os

# Nowa, bardziej estetyczna paleta kolorów
DEEP_OCEAN = (10, 40, 70)       # Ciemny, głęboki błękit - tło
SKY_BLUE = (135, 206, 235)      # Jasny błękit - woda/niebo
FOREST_GREEN = (34, 139, 34)    # Ciemniejsza zieleń - statki
CRIMSON_RED = (220, 20, 60)     # Czerwień - trafienia
SUN_YELLOW = (255, 215, 0)      # Złoty żółty - zaznaczenia/akcenty
CLOUD_WHITE = (240, 248, 255)   # Prawie biały - tekst, czyste tło
NIGHT_BLACK = (25, 25, 25)      # Bardzo ciemny szary/czarny - cienie, linie
SILVER_GRAY = (192, 192, 192)   # Szary - siatka, nieaktywne elementy
NAVY_BLUE = (0, 0, 128)         # Ciemny granat - aktywny input box
LIGHT_GRAY_ACCENT = (160, 160, 160) # Lżejszy szary dla akcentów

def load_image(name, colorkey=None):
    """
    Ładuje obraz z katalogu 'assets'.
    Jeśli chcesz grafikę na miarę 2025 roku, tutaj ładowałbyś swoje zaawansowane tekstury.
    """
    fullname = os.path.join('assets', name)
    try:
        image = pygame.image.load(fullname)
        if image.get_alpha():
            image = image.convert_alpha()
        else:
            image = image.convert()
        if colorkey is not None:
            if colorkey == -1:
                colorkey = image.get_at((0, 0))
            image.set_colorkey(colorkey, pygame.RLEACCEL)
        return image
    except pygame.error as message:
        print(f"Cannot load image: {fullname}")
        print("Using a placeholder surface instead.")
        return pygame.Surface((50, 50)) # Zwróć pustą powierzchnię jako placeholder

def create_simple_button_surface(width, height, text, font_size=30, button_color=SKY_BLUE, text_color=NIGHT_BLACK):
    """
    Tworzy prostą powierzchnię dla przycisku.
    """
    font = pygame.font.Font(None, font_size)
    text_surface = font.render(text, True, text_color)
    
    button_surface = pygame.Surface((width, height))
    button_surface.fill(button_color)
    
    text_rect = text_surface.get_rect(center=(width // 2, height // 2))
    button_surface.blit(text_surface, text_rect)
    return button_surface

def create_board_surface(size_pixels, cell_size_pixels, board_color=SKY_BLUE, line_color=LIGHT_GRAY_ACCENT):
    """
    Tworzy powierzchnię planszy gry.
    """
    board_surface = pygame.Surface((size_pixels, size_pixels))
    board_surface.fill(board_color)

    # Rysowanie siatki
    for i in range(0, size_pixels + 1, cell_size_pixels):
        pygame.draw.line(board_surface, line_color, (i, 0), (i, size_pixels))
        pygame.draw.line(board_surface, line_color, (0, i), (size_pixels, i))
    
    return board_surface

def get_assets():
    """
    Zwraca słownik z zasobami graficznymi.
    Zmieniona lambda dla board_template, aby prawidłowo przekazywała kolory.
    """
    assets = {
        'colors': {
            'deep_ocean': DEEP_OCEAN,
            'sky_blue': SKY_BLUE,
            'forest_green': FOREST_GREEN,
            'crimson_red': CRIMSON_RED,
            'sun_yellow': SUN_YELLOW,
            'cloud_white': CLOUD_WHITE,
            'night_black': NIGHT_BLACK,
            'silver_gray': SILVER_GRAY,
            'navy_blue': NAVY_BLUE,
            'light_gray_accent': LIGHT_GRAY_ACCENT,
        },
        'button_template': lambda w, h, t, fs, bc, tc: create_simple_button_surface(w, h, t, fs, bc, tc),
        'board_template': lambda s_px, c_px, b_color, l_color: create_board_surface(s_px, c_px, b_color, l_color)
    }
    return assets

# Upewnij się, że katalog 'assets' istnieje
if not os.path.exists('assets'):
    os.makedirs('assets')