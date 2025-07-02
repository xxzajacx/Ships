import pygame
import socket
import threading
import pickle
import sys
import time
import os
import math 

from generate_assets import get_assets 


pygame.init()
pygame.font.init()


SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 700
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Battleship - Client")


assets = get_assets()
COLORS = assets['colors']
create_button_surface = assets['button_template']
create_board_surface = assets['board_template']



HOST = '127.00.1' 
PORT = 65432       
BUFFER_SIZE = 4096


client_game_state = {
    'player_name': '',
    'difficulty': 'easy',
    'board_size': 0,
    'my_board': [],    
    'opponent_board_view': [],
    'ships_to_place': [], 
    'placed_ships_on_temp_board': [], 
    'current_placing_ship_index': 0,
    'current_placing_ship_orientation': 'horizontal', 
    'placement_temp_board': [],
    'my_hits_on_opponent': set(), 
    'my_misses_on_opponent': set(),
    'opponent_hits_on_my_board': set(), 
    'opponent_misses_on_my_board': set(), 
    'current_screen': 'main_menu',
    'message': '',
    'your_turn': False,
    'game_started': False,
    'game_over': False,
    'winner': None,
    'scoreboard': [],
    'restart_requested_by_opponent': False,
    'server_connection': None,
    'input_active': False,
    'input_text': '', 
    'opponent_name': '',
    'your_name': ''
}

class Button:
    def __init__(self, x, y, width, height, text, action, font_size=30, button_color=COLORS['sky_blue'], text_color=COLORS['night_black']):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.action = action
        self.font_size = font_size
        self.original_button_color = button_color 
        self.current_button_color = button_color
        self.text_color = text_color
        self.surface = self._create_surface()

    def _create_surface(self):
        return create_button_surface(self.rect.width, self.rect.height, self.text, self.font_size, self.current_button_color, self.text_color)

    def draw(self, screen):
        screen.blit(self.surface, self.rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                return self.action
        return None
    
    def set_color(self, color):
        self.current_button_color = color
        self.surface = self._create_surface()

    def update(self, mouse_pos):
        if self.rect.collidepoint(mouse_pos):
            if client_game_state['current_screen'] == 'main_menu' and \
               self.action.startswith("set_difficulty") and \
               self.current_button_color == COLORS['sun_yellow']:
                pass 
            else:
                self.set_color(COLORS['light_gray_accent']) 
        else:
            if client_game_state['current_screen'] == 'main_menu' and \
               self.action.startswith("set_difficulty"):
                difficulty_value_map = {
                    "set_difficulty_easy": "easy",
                    "set_difficulty_medium": "medium",
                    "set_difficulty_hard": "hard"
                }
                if difficulty_value_map.get(self.action) == client_game_state['difficulty']:
                    self.set_color(COLORS['sun_yellow']) 
                else:
                    self.set_color(self.original_button_color) 
            else:
                self.set_color(self.original_button_color)


class TextInputBox:
    def __init__(self, x, y, width, height, font_size=30, border_color=COLORS['night_black'], active_color=COLORS['navy_blue'], inactive_color=COLORS['silver_gray']):
        self.rect = pygame.Rect(x, y, width, height)
        self.font = pygame.font.Font(None, font_size)
        self.color = inactive_color
        self.active = False
        self.text = ''
        self.border_color = border_color
        self.active_color = active_color
        self.inactive_color = inactive_color
        self.text_color = COLORS['cloud_white'] 

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = not self.active
                client_game_state['input_active'] = self.active 
            else:
                self.active = False
                client_game_state['input_active'] = False
            self.color = self.active_color if self.active else self.inactive_color
        if event.type == pygame.KEYDOWN:
            if self.active:
                if event.key == pygame.K_RETURN:
                    self.active = False 
                    self.color = self.inactive_color
                    client_game_state['input_active'] = False
                    return None 
                elif event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                else:
                    self.text += event.unicode
                client_game_state['player_name'] = self.text
        return None 

    def draw(self, screen): 
        pygame.draw.rect(screen, self.color, self.rect)
        pygame.draw.rect(screen, self.border_color, self.rect, 2)
        text_surface = self.font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)

    def update(self, mouse_pos):
        pass

def send_to_server(sock, data):
    try:
        serialized_data = pickle.dumps(data)
        sock.sendall(serialized_data)
    except Exception as e:
        print(f"Error sending data to server: {e}")
        client_game_state['current_screen'] = 'disconnected'
        if sock: sock.close()

def receive_from_server(sock):
    try:
        data = sock.recv(BUFFER_SIZE)
        if not data:
            return None
        return pickle.loads(data)
    except (EOFError, pickle.UnpicklingError) as e:
        print(f"Error unpickling data or connection closed by server: {e}")
        return None
    except Exception as e:
        print(f"Error receiving data from server: {e}")
        return None

def server_listener(sock):
    while client_game_state['current_screen'] != 'disconnected':
        response = receive_from_server(sock)
        if response is None:
            print("Server disconnected or sent empty data.")
            client_game_state['current_screen'] = 'disconnected'
            break

        status = response.get('status')

        if status == 'waiting_for_other_player':
            client_game_state['message'] = "Oczekiwanie na drugiego gracza..."
            client_game_state['current_screen'] = 'waiting_screen'

        elif status == 'start_placement':
            client_game_state['game_started'] = False 
            client_game_state['game_over'] = False
            client_game_state['your_turn'] = False 
            client_game_state['message'] = "Rozmieść swoje statki!"
            client_game_state['your_name'] = response.get('your_name')
            client_game_state['opponent_name'] = response.get('opponent_name')
            client_game_state['board_size'] = response.get('board_size')
            client_game_state['ships_to_place'] = response.get('ships_to_place', [])
            
    
            client_game_state['placed_ships_on_temp_board'] = []
            client_game_state['current_placing_ship_index'] = 0
            client_game_state['current_placing_ship_orientation'] = 'horizontal'
            client_game_state['placement_temp_board'] = [['.' for _ in range(client_game_state['board_size'])] for _ in range(client_game_state['board_size'])]

            client_game_state['my_board'] = [['.' for _ in range(client_game_state['board_size'])] for _ in range(client_game_state['board_size'])]
            client_game_state['opponent_board_view'] = [['.' for _ in range(client_game_state['board_size'])] for _ in range(client_game_state['board_size'])]

            client_game_state['my_hits_on_opponent'] = set()
            client_game_state['my_misses_on_opponent'] = set()
            client_game_state['opponent_hits_on_my_board'] = set()
            client_game_state['opponent_misses_on_my_board'] = set()
            
            client_game_state['current_screen'] = 'placement_screen'

        elif status == 'game_start':
            client_game_state['game_started'] = True
            client_game_state['game_over'] = False
            client_game_state['your_turn'] = response.get('your_turn')
            client_game_state['message'] = "Gra rozpoczęta!"
            client_game_state['my_board'] = response.get('my_initial_board', [])

            client_game_state['current_screen'] = 'game_screen'

        elif status == 'turn_update':
            client_game_state['your_turn'] = response.get('your_turn')
            if client_game_state['your_turn']:
                client_game_state['message'] = "Twoja tura!"
            else:
                client_game_state['message'] = "Tura przeciwnika..."

        elif status == 'shot_result':
            result = response.get('result')
            row, col = response.get('row'), response.get('col')
            ship_sunk = response.get('ship_sunk')
            client_game_state['your_turn'] = response.get('your_turn_continues') 
            
            if result == 'hit':
                client_game_state['my_hits_on_opponent'].add((row, col))
                client_game_state['opponent_board_view'][row][col] = 'H' 
                client_game_state['message'] = f"Trafiłeś! ({row},{col})"
                if ship_sunk:
                    client_game_state['message'] += " Statek zatopiony!"
            else:
                client_game_state['my_misses_on_opponent'].add((row, col))
                client_game_state['opponent_board_view'][row][col] = 'M' 
                client_game_state['message'] = f"Pudło! ({row},{col})"
            
            if client_game_state['your_turn']:
                client_game_state['message'] += " Twoja tura kontynuuje."
            else:
                 client_game_state['message'] += " Tura przeciwnika."


        elif status == 'opponent_shot':
            result = response.get('result')
            row, col = response.get('row'), response.get('col')
            ship_sunk = response.get('ship_sunk')
            if response.get('your_board_state'):
                 client_game_state['my_board'] = response.get('your_board_state')
            
            if result == 'hit':
                client_game_state['opponent_hits_on_my_board'].add((row, col))
                client_game_state['message'] = f"Przeciwnik trafił Twój statek! ({row},{col})"
                if ship_sunk:
                    client_game_state['message'] += " Twój statek zatopiony!"
            else:
                client_game_state['opponent_misses_on_my_board'].add((row, col))
                client_game_state['message'] = f"Przeciwnik spudłował! ({row},{col})"

        elif status == 'invalid_shot' or status == 'error':
            client_game_state['message'] = response.get('message')

        elif status == 'game_over':
            client_game_state['game_over'] = True
            client_game_state['winner'] = response.get('winner')
            client_game_state['scoreboard'] = response.get('scoreboard')
            client_game_state['current_screen'] = 'scoreboard'
            client_game_state['message'] = f"Gra zakończona! Zwycięzca: {client_game_state['winner']}"

        elif status == 'restart_request':
            client_game_state['restart_requested_by_opponent'] = True
            client_game_state['message'] = f"Gracz {response.get('from')} prosi o ponowną rozgrywkę. Akceptujesz?"
            client_game_state['current_screen'] = 'scoreboard'

        elif status == 'restart_declined':
            client_game_state['restart_requested_by_opponent'] = False
            client_game_state['message'] = f"Gracz {response.get('from')} odrzucił prośbę o restart."

        elif status == 'game_restarted':
            pass 

        elif status == 'opponent_disconnected':
            client_game_state['message'] = "Przeciwnik rozłączył się. Powrót do menu głównego."
            client_game_state['current_screen'] = 'main_menu'
            if client_game_state['server_connection']:
                try:
                    client_game_state['server_connection'].close()
                except:
                    pass
                client_game_state['server_connection'] = None
            reset_client_state_for_new_game()

        elif status == 'restart_cancelled_opponent_left':
            client_game_state['message'] = "Przeciwnik opuścił grę, prośba o restart anulowana."
            client_game_state['restart_requested_by_opponent'] = False 
            client_game_state['current_screen'] = 'scoreboard' 

        elif status == 'server_full':
            client_game_state['message'] = "Serwer jest pełny. Spróbuj ponownie później."
            client_game_state['current_screen'] = 'main_menu'
            if sock: 
                try:
                    sock.close()
                except:
                    pass
            client_game_state['server_connection'] = None
            reset_client_state_for_new_game() 


def reset_client_state_for_new_game():
    client_game_state['player_name'] = ''
    client_game_state['difficulty'] = 'easy'
    client_game_state['board_size'] = 0
    client_game_state['my_board'] = []
    client_game_state['opponent_board_view'] = []
    client_game_state['ships_to_place'] = []
    client_game_state['placed_ships_on_temp_board'] = []
    client_game_state['current_placing_ship_index'] = 0
    client_game_state['current_placing_ship_orientation'] = 'horizontal'
    client_game_state['placement_temp_board'] = []
    client_game_state['my_hits_on_opponent'] = set()
    client_game_state['my_misses_on_opponent'] = set()
    client_game_state['opponent_hits_on_my_board'] = set()
    client_game_state['opponent_misses_on_my_board'] = set()
    client_game_state['your_turn'] = False
    client_game_state['game_started'] = False
    client_game_state['game_over'] = False
    client_game_state['winner'] = None
    client_game_state['restart_requested_by_opponent'] = False
    client_game_state['input_active'] = False
    client_game_state['input_text'] = ''
    client_game_state['opponent_name'] = ''
    client_game_state['your_name'] = ''
    client_game_state['message'] = ''



def draw_background(screen, time_elapsed):
    for y in range(SCREEN_HEIGHT):
        r = COLORS['deep_ocean'][0] + int(10 * math.sin(y * 0.02 + time_elapsed * 0.002))
        g = COLORS['deep_ocean'][1] + int(10 * math.sin(y * 0.02 + time_elapsed * 0.002))
        b = COLORS['deep_ocean'][2] + int(10 * math.sin(y * 0.02 + time_elapsed * 0.002))
        
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        
        pygame.draw.line(screen, (r, g, b), (0, y), (SCREEN_WIDTH, y))

def draw_main_menu(name_input_box, difficulty_buttons, play_button, time_elapsed):
    draw_background(screen, time_elapsed)
    
    font_large = pygame.font.Font(None, 74)
    font_medium = pygame.font.Font(None, 48)
    
    title_text = font_large.render("BATTLESHIPS", True, COLORS['cloud_white'])
    screen.blit(title_text, title_text.get_rect(center=(SCREEN_WIDTH // 2, 100)))

    name_label = font_medium.render("Enter Your Player Name:", True, COLORS['cloud_white'])
    screen.blit(name_label, name_label.get_rect(center=(SCREEN_WIDTH // 2, 200)))
    name_input_box.draw(screen)

    difficulty_label = font_medium.render("Choose Difficulty:", True, COLORS['cloud_white'])
    screen.blit(difficulty_label, difficulty_label.get_rect(center=(SCREEN_WIDTH // 2, 350)))

    for button in difficulty_buttons:
        button.draw(screen)
    
    play_button.draw(screen)

    if client_game_state['message']:
        message_text = pygame.font.Font(None, 30).render(client_game_state['message'], True, COLORS['crimson_red'])
        screen.blit(message_text, message_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50)))

def draw_waiting_screen(time_elapsed):
    draw_background(screen, time_elapsed)
    font_large = pygame.font.Font(None, 74)
    font_medium = pygame.font.Font(None, 48)

    waiting_text = font_large.render("Waiting for opponent...", True, COLORS['cloud_white'])
    screen.blit(waiting_text, waiting_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50)))

    message_text = font_medium.render(client_game_state['message'], True, COLORS['sun_yellow'])
    screen.blit(message_text, message_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50)))

def draw_placement_screen(mouse_pos, time_elapsed, place_button):
    draw_background(screen, time_elapsed)

    font_large = pygame.font.Font(None, 60)
    font_medium = pygame.font.Font(None, 36)
    font_small = pygame.font.Font(None, 24)

    title_text = font_large.render("Place Your Ships", True, COLORS['cloud_white'])
    screen.blit(title_text, title_text.get_rect(center=(SCREEN_WIDTH // 2, 50)))

    message_text = font_medium.render(client_game_state['message'], True, COLORS['sun_yellow'])
    screen.blit(message_text, message_text.get_rect(center=(SCREEN_WIDTH // 2, 100)))

    board_padding = 50
    board_size_pixels = min(SCREEN_WIDTH - 2 * board_padding, SCREEN_HEIGHT - 200) 
    
    if client_game_state['board_size'] > 0:
        cell_size = board_size_pixels // client_game_state['board_size']
        board_size_pixels = cell_size * client_game_state['board_size'] 
    else: 
        cell_size = 30
        board_size_pixels = 300 

    board_x = (SCREEN_WIDTH - board_size_pixels) // 2
    board_y = 150 

    board_surface = create_board_surface(board_size_pixels, cell_size, COLORS['sky_blue'], COLORS['light_gray_accent'])
    screen.blit(board_surface, (board_x, board_y))

    for ship in client_game_state['placed_ships_on_temp_board']:
        ship_color = COLORS['forest_green']
        for r, c in ship['coords']:
            rect = pygame.Rect(board_x + c * cell_size, board_y + r * cell_size, cell_size, cell_size)
            pygame.draw.rect(screen, ship_color, rect)
            pygame.draw.rect(screen, COLORS['night_black'], rect, 1) 

    if client_game_state['current_placing_ship_index'] < len(client_game_state['ships_to_place']):
        current_ship_size = client_game_state['ships_to_place'][client_game_state['current_placing_ship_index']]
        orientation = client_game_state['current_placing_ship_orientation']
        
        mouse_grid_x = (mouse_pos[0] - board_x) // cell_size
        mouse_grid_y = (mouse_pos[1] - board_y) // cell_size

        temp_ship_coords = []
        is_valid_placement = True
        temp_board = [['.' for _ in range(client_game_state['board_size'])] for _ in range(client_game_state['board_size'])]

        for ship in client_game_state['placed_ships_on_temp_board']:
            for r, c in ship['coords']:
                if 0 <= r < client_game_state['board_size'] and 0 <= c < client_game_state['board_size']:
                    temp_board[r][c] = 'S'

        for i in range(current_ship_size):
            r, c = (mouse_grid_y + i, mouse_grid_x) if orientation == 'vertical' else (mouse_grid_y, mouse_grid_x + i)
            
            if not (0 <= r < client_game_state['board_size'] and 0 <= c < client_game_state['board_size']):
                is_valid_placement = False
                break

            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < client_game_state['board_size'] and 0 <= nc < client_game_state['board_size'] and temp_board[nr][nc] == 'S':
                        is_valid_placement = False
                        break
                if not is_valid_placement:
                    break
            
            if not is_valid_placement:
                break
            
            temp_ship_coords.append((r, c))

        hover_color = COLORS['sun_yellow'] if is_valid_placement else COLORS['crimson_red']
        for r, c in temp_ship_coords:
            rect = pygame.Rect(board_x + c * cell_size, board_y + r * cell_size, cell_size, cell_size)
            pygame.draw.rect(screen, hover_color, rect)
            pygame.draw.rect(screen, COLORS['night_black'], rect, 2) 


    ships_to_place_text = "Ships to place: "
    for i, ship_size in enumerate(client_game_state['ships_to_place']):
        color = COLORS['cloud_white']
        if i == client_game_state['current_placing_ship_index']:
            color = COLORS['sun_yellow'] 
        ships_to_place_text += f"{ship_size} "
        font_ship_size = font_small.render(str(ship_size), True, color)
        screen.blit(font_ship_size, (board_x + board_size_pixels + 20 + i * 30, board_y + 50))

    rotate_text = font_small.render("Press R to rotate ship", True, COLORS['silver_gray'])
    screen.blit(rotate_text, rotate_text.get_rect(midbottom=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 80)))

    if client_game_state['current_placing_ship_index'] == len(client_game_state['ships_to_place']):
        place_button.draw(screen)


def draw_game_screen(mouse_pos, time_elapsed):
    draw_background(screen, time_elapsed)

    font_small = pygame.font.Font(None, 24)
    font_medium = pygame.font.Font(None, 36)

    player1_label = font_medium.render(f"Your Board ({client_game_state['your_name']})", True, COLORS['cloud_white'])
    screen.blit(player1_label, (50, 20))

    player2_label = font_medium.render(f"Opponent's Board ({client_game_state['opponent_name']})", True, COLORS['cloud_white'])
    screen.blit(player2_label, (SCREEN_WIDTH // 2 + 50, 20))

    board_padding = 50
    max_board_area_width = (SCREEN_WIDTH // 2) - board_padding * 2
    max_board_area_height = SCREEN_HEIGHT - 150
    board_size_pixels = min(max_board_area_width, max_board_area_height)
    
    if client_game_state['board_size'] > 0:
        cell_size = board_size_pixels // client_game_state['board_size']
        board_size_pixels = cell_size * client_game_state['board_size'] 
    else: 
        cell_size = 30
        board_size_pixels = 300 


    player_board_x = board_padding
    player_board_y = 70
    

    player_board_surface = create_board_surface(board_size_pixels, cell_size, COLORS['sky_blue'], COLORS['light_gray_accent'])
    screen.blit(player_board_surface, (player_board_x, player_board_y))

    if client_game_state['my_board'] and client_game_state['board_size'] > 0:
        for r in range(client_game_state['board_size']):
            for c in range(client_game_state['board_size']):
                rect = pygame.Rect(player_board_x + c * cell_size, player_board_y + r * cell_size, cell_size, cell_size)
                
               
                if client_game_state['my_board'][r][c] == 'S':
                    pygame.draw.rect(screen, COLORS['forest_green'], rect) 
                elif client_game_state['my_board'][r][c] == 'X':
                    pygame.draw.rect(screen, COLORS['crimson_red'], rect) 
                    pygame.draw.line(screen, COLORS['night_black'], rect.topleft, rect.bottomright, 3)
                    pygame.draw.line(screen, COLORS['night_black'], rect.bottomleft, rect.topright, 3)
                elif client_game_state['my_board'][r][c] == 'O':
                    pygame.draw.circle(screen, COLORS['night_black'], rect.center, cell_size // 4, 2) 
                
                pygame.draw.rect(screen, COLORS['light_gray_accent'], rect, 1) 

    
    opponent_board_x = SCREEN_WIDTH // 2 + board_padding
    opponent_board_y = 70

   
    opponent_board_surface = create_board_surface(board_size_pixels, cell_size, COLORS['sky_blue'], COLORS['light_gray_accent'])
    screen.blit(opponent_board_surface, (opponent_board_x, opponent_board_y))

    
    if client_game_state['opponent_board_view'] and client_game_state['board_size'] > 0:
        for r in range(client_game_state['board_size']):
            for c in range(client_game_state['board_size']):
                rect = pygame.Rect(opponent_board_x + c * cell_size, opponent_board_y + r * cell_size, cell_size, cell_size)
                
                if client_game_state['opponent_board_view'][r][c] == 'H':
                    pygame.draw.rect(screen, COLORS['crimson_red'], rect) 
                    pygame.draw.line(screen, COLORS['night_black'], rect.topleft, rect.bottomright, 3)
                    pygame.draw.line(screen, COLORS['night_black'], rect.bottomleft, rect.topright, 3)
                elif client_game_state['opponent_board_view'][r][c] == 'M':
                    pygame.draw.circle(screen, COLORS['night_black'], rect.center, cell_size // 4, 2) 
                
            
                if client_game_state['your_turn'] and rect.collidepoint(mouse_pos) and \
                   client_game_state['opponent_board_view'][r][c] == '.': 
                    pygame.draw.rect(screen, COLORS['sun_yellow'], rect, 3) 
                
                pygame.draw.rect(screen, COLORS['light_gray_accent'], rect, 1)


    message_text = font_medium.render(client_game_state['message'], True, COLORS['sun_yellow'])
    screen.blit(message_text, message_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50)))

    turn_indicator_color = COLORS['forest_green'] if client_game_state['your_turn'] else COLORS['crimson_red']
    turn_text = font_medium.render("YOUR TURN" if client_game_state['your_turn'] else "OPPONENT'S TURN", True, turn_indicator_color)
    screen.blit(turn_text, turn_text.get_rect(midtop=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 100)))

def draw_scoreboard_screen(restart_button, exit_button, accept_restart_button, decline_restart_button, time_elapsed):
    draw_background(screen, time_elapsed)
    
    font_large = pygame.font.Font(None, 74)
    font_medium = pygame.font.Font(None, 48)
    font_small = pygame.font.Font(None, 36)

    title_text = font_large.render("Game Results", True, COLORS['cloud_white'])
    screen.blit(title_text, title_text.get_rect(center=(SCREEN_WIDTH // 2, 80)))

    winner_text = font_medium.render(f"Winner: {client_game_state['winner']}", True, COLORS['forest_green'])
    screen.blit(winner_text, winner_text.get_rect(center=(SCREEN_WIDTH // 2, 150)))

    scoreboard_label = font_medium.render("Top Players:", True, COLORS['cloud_white'])
    screen.blit(scoreboard_label, scoreboard_label.get_rect(center=(SCREEN_WIDTH // 2, 220)))

    y_offset = 270
    if client_game_state['scoreboard']:
        for i, entry in enumerate(client_game_state['scoreboard']):
            score_text = font_small.render(f"{i+1}. {entry['name']}: {entry['wins']} wins", True, COLORS['silver_gray'])
            screen.blit(score_text, score_text.get_rect(center=(SCREEN_WIDTH // 2, y_offset)))
            y_offset += 40
    else:
        no_score_text = font_small.render("No scores to display yet.", True, COLORS['silver_gray'])
        screen.blit(no_score_text, no_score_text.get_rect(center=(SCREEN_WIDTH // 2, y_offset)))

    button_y_pos = SCREEN_HEIGHT - 100 
    message_y_pos = SCREEN_HEIGHT - 180 

    if not client_game_state['restart_requested_by_opponent']:
        restart_button.rect.centery = button_y_pos
        exit_button.rect.centery = button_y_pos
        restart_button.draw(screen)
        exit_button.draw(screen)
        if client_game_state['message']:
            message_text = pygame.font.Font(None, 30).render(client_game_state['message'], True, COLORS['crimson_red'])
            screen.blit(message_text, message_text.get_rect(center=(SCREEN_WIDTH // 2, message_y_pos)))
    else:
        message_text = font_medium.render(client_game_state['message'], True, COLORS['sun_yellow'])
        screen.blit(message_text, message_text.get_rect(center=(SCREEN_WIDTH // 2, message_y_pos)))
        
        accept_restart_button.rect.centery = button_y_pos
        decline_restart_button.rect.centery = button_y_pos
        accept_restart_button.draw(screen)
        decline_restart_button.draw(screen)


def draw_disconnected_screen(time_elapsed):
    draw_background(screen, time_elapsed)
    font_large = pygame.font.Font(None, 74)
    message_text = font_large.render("Disconnected from server!", True, COLORS['crimson_red'])
    screen.blit(message_text, message_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

    instruction_text = pygame.font.Font(None, 36).render("Check the server and restart the client.", True, COLORS['cloud_white'])
    screen.blit(instruction_text, instruction_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 80)))

def get_ship_coords(start_row, start_col, ship_size, orientation, board_size):
    coords = []
    is_valid = True
    for i in range(ship_size):
        r, c = (start_row + i, start_col) if orientation == 'vertical' else (start_row, start_col + i)
        if not (0 <= r < board_size and 0 <= c < board_size):
            is_valid = False
            break
        coords.append((r, c))
    return coords, is_valid

def check_collision_and_buffer(coords, placed_ships, board_size):
    temp_board_check = [['.' for _ in range(board_size)] for _ in range(board_size)]

    for ship in placed_ships:
        for r, c in ship['coords']:
            temp_board_check[r][c] = 'S' 
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < board_size and 0 <= nc < board_size and temp_board_check[nr][nc] == '.':
                        temp_board_check[nr][nc] = 'B' 

    for r, c in coords:
        if not (0 <= r < board_size and 0 <= c < board_size):
            return False 
        if temp_board_check[r][c] in ['S', 'B']: 
            return False
        

        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                nr, nc = r + dr, c + dc

                if (nr, nc) in sum([s['coords'] for s in placed_ships], []):
                    return False

    return True


def main():
    running = True
    clock = pygame.time.Clock()
    time_elapsed = 0 


    name_input_box = TextInputBox(SCREEN_WIDTH // 2 - 150, 250, 300, 50)
    
    difficulty_buttons_config = [
        {"text": "Easy", "action": "set_difficulty_easy", "difficulty_value": "easy", "x_offset": -200},
        {"text": "Medium", "action": "set_difficulty_medium", "difficulty_value": "medium", "x_offset": -50},
        {"text": "Hard", "action": "set_difficulty_hard", "difficulty_value": "hard", "x_offset": 100}
    ]

    difficulty_buttons = []

    for config in difficulty_buttons_config:
        btn = Button(
            SCREEN_WIDTH // 2 + config["x_offset"], 400, 100, 50, 
            config["text"], config["action"], 
            button_color=COLORS['sky_blue'], text_color=COLORS['night_black']
        )
        difficulty_buttons.append(btn)
        if config["difficulty_value"] == client_game_state['difficulty']:
            btn.set_color(COLORS['sun_yellow']) 

    play_button = Button(SCREEN_WIDTH // 2 - 100, 500, 200, 60, "PLAY!", "start_game_request")

    restart_button = Button(SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT - 100, 150, 60, "Restart", "request_restart", button_color=COLORS['forest_green'], text_color=COLORS['cloud_white'])
    exit_button = Button(SCREEN_WIDTH // 2 + 50, SCREEN_HEIGHT - 100, 150, 60, "Exit", "exit_game", button_color=COLORS['crimson_red'], text_color=COLORS['cloud_white'])
    accept_restart_button = Button(SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT - 100, 180, 60, "Accept Restart", "accept_restart", button_color=COLORS['forest_green'], text_color=COLORS['cloud_white'])
    decline_restart_button = Button(SCREEN_WIDTH // 2 + 20, SCREEN_HEIGHT - 100, 180, 60, "Decline Restart", "decline_restart", button_color=COLORS['crimson_red'], text_color=COLORS['cloud_white'])
    place_ships_button = Button(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT - 70, 200, 60, "Confirm Placement", "confirm_placement", button_color=COLORS['forest_green'], text_color=COLORS['cloud_white'])


    conn = None
    listener_thread = None

    while running:
        dt = clock.tick(60) 
        time_elapsed += dt

        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                if conn:
                    try:
                        send_to_server(conn, {'action': 'exit_game'})
                    except Exception as e:
                        print(f"Error sending exit message: {e}")
                break

            if client_game_state['current_screen'] == 'main_menu':
                name_input_box.handle_event(event) 
                
                for button in difficulty_buttons:
                    action_result = button.handle_event(event)
                    if action_result:
                        selected_difficulty_value = None
                        for config in difficulty_buttons_config:
                            if config["action"] == action_result:
                                selected_difficulty_value = config["difficulty_value"]
                                break
                        
                        if selected_difficulty_value:
                            client_game_state['difficulty'] = selected_difficulty_value
                            for other_button in difficulty_buttons:
                                if other_button.action == action_result:
                                    other_button.set_color(COLORS['sun_yellow'])
                                else:
                                    other_button.set_color(COLORS['sky_blue'])

                action = play_button.handle_event(event)
                if action == "start_game_request":
                    if name_input_box.text.strip(): 
                        client_game_state['player_name'] = name_input_box.text.strip() 
                        client_game_state['message'] = "Connecting to server..."
                        try:
                            if conn:
                                try: conn.close() 
                                except: pass
                            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            conn.connect((HOST, PORT))
                            client_game_state['server_connection'] = conn
                            listener_thread = threading.Thread(target=server_listener, args=(conn,))
                            listener_thread.daemon = True
                            listener_thread.start()
                            send_to_server(conn, {
                                'action': 'set_player_info',
                                'name': client_game_state['player_name'],
                                'difficulty': client_game_state['difficulty']
                            })
                            client_game_state['current_screen'] = 'waiting_screen'
                        except ConnectionRefusedError:
                            client_game_state['message'] = "Could not connect to server. Ensure server is running."
                        except Exception as e:
                            client_game_state['message'] = f"Connection error: {e}"
                    else:
                        client_game_state['message'] = "Please enter your player name."

            elif client_game_state['current_screen'] == 'placement_screen':
                board_padding = 50
                board_size_pixels = min(SCREEN_WIDTH - 2 * board_padding, SCREEN_HEIGHT - 200)
                if client_game_state['board_size'] > 0:
                    cell_size = board_size_pixels // client_game_state['board_size']
                    board_size_pixels = cell_size * client_game_state['board_size']
                else:
                    cell_size = 30
                    board_size_pixels = 300
                board_x = (SCREEN_WIDTH - board_size_pixels) // 2
                board_y = 150

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: 
                    mouse_grid_x = (mouse_pos[0] - board_x) // cell_size
                    mouse_grid_y = (mouse_pos[1] - board_y) // cell_size

                    current_ship_index = client_game_state['current_placing_ship_index']
                    if current_ship_index < len(client_game_state['ships_to_place']):
                        ship_size = client_game_state['ships_to_place'][current_ship_index]
                        orientation = client_game_state['current_placing_ship_orientation']

                        proposed_coords, in_bounds = get_ship_coords(mouse_grid_y, mouse_grid_x, ship_size, orientation, client_game_state['board_size'])

                        if in_bounds and check_collision_and_buffer(proposed_coords, client_game_state['placed_ships_on_temp_board'], client_game_state['board_size']):
                         
                            client_game_state['placed_ships_on_temp_board'].append({
                                'coords': proposed_coords,
                                'size': ship_size,
                                'orientation': orientation, 
                                'start_pos': (mouse_grid_y, mouse_grid_x) 
                            })
                            client_game_state['current_placing_ship_index'] += 1
                            client_game_state['message'] = "Statek umieszczony!" if client_game_state['current_placing_ship_index'] < len(client_game_state['ships_to_place']) else "Wszystkie statki umieszczone. Potwierdź."
                        else:
                            client_game_state['message'] = "Nie można tu umieścić statku (kolizja lub poza planszą)."
                    
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r: 
                        current_orientation = client_game_state['current_placing_ship_orientation']
                        client_game_state['current_placing_ship_orientation'] = 'vertical' if current_orientation == 'horizontal' else 'horizontal'
                        client_game_state['message'] = f"Orientacja: {client_game_state['current_placing_ship_orientation']}"

                if client_game_state['current_placing_ship_index'] == len(client_game_state['ships_to_place']):
                    action = place_ships_button.handle_event(event)
                    if action == "confirm_placement":
                        if client_game_state['server_connection']:
                            send_to_server(client_game_state['server_connection'], {
                                'action': 'place_ships',
                                'ships': client_game_state['placed_ships_on_temp_board']
                            })
                            client_game_state['message'] = "Wysyłam rozmieszczenie statków... Oczekiwanie na przeciwnika."
                        else:
                            client_game_state['message'] = "Brak połączenia z serwerem."

            elif client_game_state['current_screen'] == 'game_screen':
                if event.type == pygame.MOUSEBUTTONDOWN and client_game_state['your_turn'] and event.button == 1:
                    board_padding = 50
                    max_board_area_width = (SCREEN_WIDTH // 2) - board_padding * 2
                    max_board_area_height = SCREEN_HEIGHT - 150
                    board_size_pixels = min(max_board_area_width, max_board_area_height)
                    
                    if client_game_state['board_size'] > 0:
                        cell_size = board_size_pixels // client_game_state['board_size']
                        board_size_pixels = cell_size * client_game_state['board_size']
                    else:
                        cell_size = 30 
                        board_size_pixels = 300

                    opponent_board_x = SCREEN_WIDTH // 2 + board_padding
                    opponent_board_y = 70

                    click_x, click_y = event.pos
                    if opponent_board_x <= click_x < opponent_board_x + board_size_pixels and \
                       opponent_board_y <= click_y < opponent_board_y + board_size_pixels:
                        
                        col = (click_x - opponent_board_x) // cell_size
                        row = (click_y - opponent_board_y) // cell_size
                        
                        if (row, col) not in client_game_state['my_hits_on_opponent'] and \
                           (row, col) not in client_game_state['my_misses_on_opponent']:
                            send_to_server(conn, {'action': 'shoot', 'row': row, 'col': col})
                        else:
                            client_game_state['message'] = "You already shot at this location!"

            elif client_game_state['current_screen'] == 'scoreboard':
                action = restart_button.handle_event(event)
                if action == "request_restart":
                    if conn:
                        send_to_server(conn, {'action': 'request_restart'})
                        client_game_state['message'] = "Restart request sent. Waiting for opponent..."
                      
                    else:
                        client_game_state['message'] = "No server connection."

                action = exit_button.handle_event(event)
                if action == "exit_game":
                    if conn:
                        send_to_server(conn, {'action': 'exit_game'})
                    running = False
                    break 

                if client_game_state['restart_requested_by_opponent']:
                    action = accept_restart_button.handle_event(event)
                    if action == "accept_restart":
                        if conn:
                            send_to_server(conn, {'action': 'accept_restart'})
                            client_game_state['message'] = "Restart accepted. Waiting for server setup."
                            
                        else:
                            client_game_state['message'] = "No server connection."
                    
                    action = decline_restart_button.handle_event(event)
                    if action == "decline_restart":
                        if conn:
                            send_to_server(conn, {'action': 'decline_restart'})
                            client_game_state['message'] = "Restart declined."
                            client_game_state['restart_requested_by_opponent'] = False 
                        else:
                            client_game_state['message'] = "No server connection."

 
        if client_game_state['current_screen'] == 'main_menu':
            name_input_box.update(mouse_pos)
            for button in difficulty_buttons:
                button.update(mouse_pos)
            play_button.update(mouse_pos)
        elif client_game_state['current_screen'] == 'scoreboard':
            restart_button.update(mouse_pos)
            exit_button.update(mouse_pos)
            if client_game_state['restart_requested_by_opponent']:
                accept_restart_button.update(mouse_pos)
                decline_restart_button.update(mouse_pos)
        elif client_game_state['current_screen'] == 'placement_screen':
            if client_game_state['current_placing_ship_index'] == len(client_game_state['ships_to_place']):
                place_ships_button.update(mouse_pos)


        if client_game_state['current_screen'] == 'main_menu':
            draw_main_menu(name_input_box, difficulty_buttons, play_button, time_elapsed)
        elif client_game_state['current_screen'] == 'waiting_screen':
            draw_waiting_screen(time_elapsed)
        elif client_game_state['current_screen'] == 'placement_screen':
            draw_placement_screen(mouse_pos, time_elapsed, place_ships_button)
        elif client_game_state['current_screen'] == 'game_screen':
            draw_game_screen(mouse_pos, time_elapsed)
        elif client_game_state['current_screen'] == 'scoreboard':
            draw_scoreboard_screen(restart_button, exit_button, accept_restart_button, decline_restart_button, time_elapsed)
        elif client_game_state['current_screen'] == 'disconnected':
            draw_disconnected_screen(time_elapsed)

        pygame.display.flip()

    if conn and client_game_state['server_connection']: 
        try:
            client_game_state['server_connection'].shutdown(socket.SHUT_RDWR)
            client_game_state['server_connection'].close()
        except OSError as e:
            print(f"Error during socket shutdown/close: {e}")
    if listener_thread and listener_thread.is_alive():
        time.sleep(0.1) 
    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    main()