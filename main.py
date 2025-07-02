import socket
import threading
import pickle
import time
import random

HOST = '127.0.0.1'
DEFAULT_PORT = 65432
PORT_RANGE_START = 65432
PORT_RANGE_END = 65535
BUFFER_SIZE = 4096

GAME_CONFIG = {
    'easy': {'board_size': 8, 'ships': [5, 4, 3, 3, 2]},
    'medium': {'board_size': 10, 'ships': [5, 4, 3, 3, 2, 2]},
    'hard': {'board_size': 12, 'ships': [5, 4, 4, 3, 3, 2, 2]}
}

class GameState:
    def __init__(self):
        self.players = {}
        self.player_boards = {}
        self.player_board_states = {}
        self.player_ships = {}
        self.current_player_turn = None
        self.game_started = False
        self.game_over = False
        self.winner = None
        self.message_to_player = {}
        self.scoreboard = []
        self.game_id_counter = 0
        self.player_ready_for_placement = {}
        self.player_placed_ships = {}

        self.load_scoreboard()

    def load_scoreboard(self):
        try:
            with open('scoreboard.pkl', 'rb') as f:
                self.scoreboard = pickle.load(f)
        except FileNotFoundError:
            self.scoreboard = []
        except Exception as e:
            print(f"Error loading scoreboard: {e}")
            self.scoreboard = []

    def save_scoreboard(self):
        try:
            with open('scoreboard.pkl', 'wb') as f:
                pickle.dump(self.scoreboard, f)
        except Exception as e:
            print(f"Error saving scoreboard: {e}")

    def add_win_to_scoreboard(self, player_name):
        found = False
        for entry in self.scoreboard:
            if entry['name'] == player_name:
                entry['wins'] += 1
                found = True
                break
        if not found:
            self.scoreboard.append({'name': player_name, 'wins': 1})
        self.scoreboard.sort(key=lambda x: x['wins'], reverse=True)
        self.save_scoreboard()

    def get_opponent_id(self, player_id):
        player_ids = list(self.players.keys())
        if len(player_ids) != 2:
            return None
        return player_ids[0] if player_ids[1] == player_id else player_ids[1]

    def reset_game(self):
        print("Resetting game state...")
        self.player_boards = {}
        self.player_board_states = {}
        self.player_ships = {}
        self.current_player_turn = None
        self.game_started = False
        self.game_over = False
        self.winner = None
        self.message_to_player = {}
        self.player_ready_for_placement = {}
        self.player_placed_ships = {}
        self.game_id_counter += 1

        for player_id in self.players:
            self.players[player_id]['board_size'] = 0
            self.players[player_id]['difficulty'] = 'easy'
            self.players[player_id]['my_initial_board'] = []
            self.players[player_id]['ready_to_play'] = False
            self.players[player_id]['restart_requested'] = False


    def prepare_new_game(self):
        if len(self.players) == 2:
            p1_id, p2_id = list(self.players.keys())
            p1_diff = self.players[p1_id]['difficulty']
            p2_diff = self.players[p2_id]['difficulty']

            board_size = max(GAME_CONFIG[p1_diff]['board_size'], GAME_CONFIG[p2_diff]['board_size'])
            ships = list(set(GAME_CONFIG[p1_diff]['ships'] + GAME_CONFIG[p2_diff]['ships']))
            ships.sort(reverse=True)

            for player_id in self.players:
                self.players[player_id]['board_size'] = board_size
                self.players[player_id]['ships_to_place'] = list(GAME_CONFIG[self.players[player_id]['difficulty']]['ships'])
                self.player_ready_for_placement[player_id] = False
                self.player_placed_ships[player_id] = []

            print(f"Game configured: Board Size {board_size}, Ships {ships}")
            return True
        return False

    def place_ship(self, player_id, ship_coords):
        board_size = self.players[player_id]['board_size']
        board = [['.' for _ in range(board_size)] for _ in range(board_size)]
        ships_list = []

        temp_board_for_validation = [['.' for _ in range(board_size)] for _ in range(board_size)]

        for ship_data in ship_coords:
            ship_len = ship_data['size']
            orientation = ship_data['orientation']
            start_row, start_col = ship_data['start_pos']
            
            current_ship_cells = []
            valid_placement = True

            for i in range(ship_len):
                r, c = (start_row + i, start_col) if orientation == 'vertical' else (start_row, start_col + i)
                if not (0 <= r < board_size and 0 <= c < board_size):
                    valid_placement = False
                    break
                
                if temp_board_for_validation[r][c] == 'S':
                    valid_placement = False
                    break

                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < board_size and 0 <= nc < board_size and temp_board_for_validation[nr][nc] == 'S':
                            valid_placement = False
                            break
                    if not valid_placement:
                        break
                if not valid_placement:
                    break
                current_ship_cells.append((r, c))

            if not valid_placement:
                return False
            
            for r, c in current_ship_cells:
                temp_board_for_validation[r][c] = 'S'
            ships_list.append({'coords': current_ship_cells, 'size': ship_len, 'hits': 0, 'sunk': False})

        self.player_boards[player_id] = temp_board_for_validation
        self.player_ships[player_id] = ships_list
        self.player_board_states[player_id] = [['.' for _ in range(board_size)] for _ in range(board_size)]
        
        self.player_ready_for_placement[player_id] = True
        return True


    def check_all_players_ready_for_placement(self):
        if len(self.players) < 2:
            return False
        return all(self.player_ready_for_placement.get(pid, False) for pid in self.players)


    def process_shot(self, player_id, row, col):
        opponent_id = self.get_opponent_id(player_id)
        if not opponent_id:
            return {'status': 'error', 'message': 'No opponent found.'}

        opponent_board = self.player_boards[opponent_id]
        opponent_board_view_for_player = self.player_board_states[opponent_id]
        
        board_size = self.players[player_id]['board_size']

        if not (0 <= row < board_size and 0 <= col < board_size):
            return {'status': 'invalid_shot', 'message': 'Shot out of bounds.'}

        if opponent_board_view_for_player[row][col] in ['H', 'M']:
            return {'status': 'invalid_shot', 'message': 'Already shot there.'}

        result = 'miss'
        ship_sunk = False
        your_turn_continues = False

        if opponent_board[row][col] == 'S':
            result = 'hit'
            opponent_board[row][col] = 'X'
            opponent_board_view_for_player[row][col] = 'H'
            for ship in self.player_ships[opponent_id]:
                if (row, col) in ship['coords']:
                    ship['hits'] += 1
                    if ship['hits'] == ship['size']:
                        ship['sunk'] = True
                        ship_sunk = True
            if all(ship['sunk'] for ship in self.player_ships[opponent_id]):
                self.game_over = True
                self.winner = self.players[player_id]['name']
                self.add_win_to_scoreboard(self.winner)
            else:
                your_turn_continues = True
        else:
            opponent_board[row][col] = 'O'
            opponent_board_view_for_player[row][col] = 'M'
            your_turn_continues = False
        return {
            'status': 'shot_result',
            'result': result,
            'row': row,
            'col': col,
            'ship_sunk': ship_sunk,
            'your_turn_continues': your_turn_continues,
            'game_over': self.game_over,
            'winner': self.winner,
            'your_board_state': self.player_boards[opponent_id]
        }

game_state = GameState()
player_counter = 0
lock = threading.Lock()

def send_response(conn, response):
    try:
        serialized_response = pickle.dumps(response)
        conn.sendall(serialized_response)
    except Exception as e:
        print(f"Error sending response: {e}")

def handle_client(conn, addr, player_id):
    global player_counter
    print(f"Connected by {addr}, assigned ID: {player_id}")
    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                break
            request = pickle.loads(data)
            action = request.get('action')

            with lock:
                if action == 'set_player_info':
                    name = request.get('name')
                    difficulty = request.get('difficulty')

                    game_state.players[player_id] = {
                        'conn': conn,
                        'addr': addr,
                        'name': name,
                        'difficulty': difficulty,
                        'ready_to_play': False,
                        'restart_requested': False
                    }
                    print(f"Player {name} ({player_id}) set difficulty to {difficulty}")

                    if len(game_state.players) == 2:
                        p_ids = list(game_state.players.keys())
                        other_player_id = p_ids[0] if p_ids[1] == player_id else p_ids[1]
                        
                        if game_state.players[other_player_id]['difficulty'] == 'easy':
                            game_state.players[player_id]['difficulty'] = 'easy'
                            print(f"Player {name} difficulty set to 'easy' to match opponent.")
                        elif game_state.players[player_id]['difficulty'] == 'easy':
                            game_state.players[other_player_id]['difficulty'] = 'easy'
                            print(f"Player {game_state.players[other_player_id]['name']} difficulty set to 'easy' to match new player.")


                    if len(game_state.players) == 1:
                        send_response(conn, {'status': 'waiting_for_other_player', 'message': 'Oczekiwanie na drugiego gracza...'})
                    elif len(game_state.players) == 2:
                        if game_state.prepare_new_game():
                            for pid, player_info in game_state.players.items():
                                opponent_id = game_state.get_opponent_id(pid)
                                send_response(player_info['conn'], {
                                    'status': 'start_placement',
                                    'your_name': player_info['name'],
                                    'opponent_name': game_state.players[opponent_id]['name'],
                                    'board_size': player_info['board_size'],
                                    'ships_to_place': player_info['ships_to_place']
                                })
                        else:
                            print("Error preparing new game state.")

                elif action == 'place_ships':
                    ships_data = request.get('ships')
                    if game_state.place_ship(player_id, ships_data):
                        print(f"Player {player_id} successfully placed ships.")
                        if game_state.check_all_players_ready_for_placement():
                            print("Both players ready for placement. Starting game!")
                            player_ids = list(game_state.players.keys())
                            game_state.current_player_turn = random.choice(player_ids)
                            game_state.game_started = True

                            for pid, player_info in game_state.players.items():
                                opponent_id = game_state.get_opponent_id(pid)
                                send_response(player_info['conn'], {
                                    'status': 'game_start',
                                    'your_turn': (pid == game_state.current_player_turn),
                                    'my_initial_board': game_state.player_boards[pid]
                                })
                        else:
                            send_response(conn, {'status': 'waiting_for_other_player', 'message': 'Czekanie na przeciwnika...'})
                    else:
                        send_response(conn, {'status': 'error', 'message': 'Nieprawidłowe rozmieszczenie statków. Spróbuj ponownie.'})

                elif action == 'shoot':
                    row = request.get('row')
                    col = request.get('col')
                    if player_id == game_state.current_player_turn and not game_state.game_over:
                        shot_response = game_state.process_shot(player_id, row, col)
                        send_response(conn, shot_response)
                        
                        opponent_id = game_state.get_opponent_id(player_id)
                        if opponent_id:
                            opponent_shot_info = {
                                'status': 'opponent_shot',
                                'row': row,
                                'col': col,
                                'result': shot_response['result'],
                                'ship_sunk': shot_response['ship_sunk'],
                                'your_board_state': game_state.player_boards[opponent_id]
                            }
                            send_response(game_state.players[opponent_id]['conn'], opponent_shot_info)
                            
                            if not shot_response['your_turn_continues'] and not game_state.game_over:
                                game_state.current_player_turn = opponent_id
                                send_response(conn, {'status': 'turn_update', 'your_turn': False})
                                send_response(game_state.players[opponent_id]['conn'], {'status': 'turn_update', 'your_turn': True})
                            elif game_state.game_over:
                                for pid, player_info in game_state.players.items():
                                    send_response(player_info['conn'], {
                                        'status': 'game_over',
                                        'winner': game_state.winner,
                                        'scoreboard': game_state.scoreboard
                                    })
                    else:
                        send_response(conn, {'status': 'error', 'message': 'To nie Twoja tura lub gra się zakończyła.'})

                elif action == 'request_restart':
                    game_state.players[player_id]['restart_requested'] = True
                    opponent_id = game_state.get_opponent_id(player_id)
                    if opponent_id:
                        if game_state.players[opponent_id]['restart_requested']:
                            print("Both players requested restart. Resetting game.")
                            game_state.reset_game()
                            if game_state.prepare_new_game():
                                for pid, player_info in game_state.players.items():
                                    opponent_of_pid = game_state.get_opponent_id(pid)
                                    send_response(player_info['conn'], {
                                        'status': 'start_placement',
                                        'your_name': player_info['name'],
                                        'opponent_name': game_state.players[opponent_of_pid]['name'],
                                        'board_size': player_info['board_size'],
                                        'ships_to_place': player_info['ships_to_place']
                                    })
                            else:
                                print("Error preparing new game after restart request.")
                        else:
                            send_response(game_state.players[opponent_id]['conn'], {
                                'status': 'restart_request',
                                'from': game_state.players[player_id]['name']
                            })
                            send_response(conn, {'status': 'message', 'message': 'Oczekiwanie na odpowiedź przeciwnika...'})
                    else:
                        send_response(conn, {'status': 'error', 'message': 'Nie ma przeciwnika do zrestartowania gry.'})
                
                elif action == 'accept_restart':
                    game_state.players[player_id]['restart_requested'] = True
                    opponent_id = game_state.get_opponent_id(player_id)
                    if opponent_id and game_state.players[opponent_id]['restart_requested']:
                        print("Both players accepted restart. Resetting game.")
                        game_state.reset_game()
                        if game_state.prepare_new_game():
                            for pid, player_info in game_state.players.items():
                                opponent_of_pid = game_state.get_opponent_id(pid)
                                send_response(player_info['conn'], {
                                    'status': 'start_placement',
                                    'your_name': player_info['name'],
                                    'opponent_name': game_state.players[opponent_of_pid]['name'],
                                    'board_size': player_info['board_size'],
                                    'ships_to_place': player_info['ships_to_place']
                                })
                        else:
                            print("Error preparing new game after restart acceptance.")
                    else:
                         send_response(conn, {'status': 'message', 'message': 'Czekam na akceptację przeciwnika...'})

                elif action == 'decline_restart':
                    opponent_id = game_state.get_opponent_id(player_id)
                    if opponent_id:
                        game_state.players[player_id]['restart_requested'] = False
                        send_response(game_state.players[opponent_id]['conn'], {
                            'status': 'restart_declined',
                            'from': game_state.players[player_id]['name']
                        })
                        send_response(conn, {'status': 'message', 'message': 'Odrzuciłeś prośbę o restart.'})
                    else:
                        send_response(conn, {'status': 'error', 'message': 'Brak przeciwnika.'})

                elif action == 'disconnect':
                    print(f"Player {player_id} disconnected gracefully.")
                    if player_id in game_state.players:
                        del game_state.players[player_id]
                    opponent_id = game_state.get_opponent_id(player_id)
                    if opponent_id and opponent_id in game_state.players:
                        send_response(game_state.players[opponent_id]['conn'], {'status': 'opponent_disconnected'})
                        game_state.players[opponent_id]['restart_requested'] = False
                    break
    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        with lock:
            if player_id in game_state.players:
                print(f"Client {addr} ({player_id}) disconnected unexpectedly.")
                del game_state.players[player_id]
                opponent_id = game_state.get_opponent_id(player_id)
                if opponent_id and opponent_id in game_state.players:
                    send_response(game_state.players[opponent_id]['conn'], {'status': 'opponent_disconnected'})
                    game_state.players[opponent_id]['restart_requested'] = False
        try:
            conn.close()
        except OSError as e:
            print(f"Error closing connection for {addr}: {e}")

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    found_port = None
    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        try:
            server_socket.bind((HOST, port))
            found_port = port
            print(f"Successfully bound to port {found_port}")
            break
        except socket.error as e:
            if e.errno == 98:
                print(f"Port {port} is already in use, trying next...")
                continue
            else:
                print(f"Socket error on port {port}: {e}")
                raise e
        except Exception as e:
            print(f"An unexpected error occurred trying to bind to port {port}: {e}")
            raise

    if not found_port:
        print(f"ERROR: Could not find an available port in range {PORT_RANGE_START}-{PORT_RANGE_END}. Exiting.")
        return

    server_socket.listen(2)
    print(f"Server listening on {HOST}:{found_port}")

    global player_counter
    while True:
        try:
            conn, addr = server_socket.accept()
            with lock:
                if len(game_state.players) < 2:
                    player_id = f"player_{player_counter}"
                    player_counter += 1
                    
                    client_thread = threading.Thread(target=handle_client, args=(conn, addr, player_id))
                    client_thread.daemon = True
                    client_thread.start()
                else:
                    print(f"Connection from {addr} rejected. Server is full.")
                    send_response(conn, {'status': 'server_full', 'message': 'Serwer jest pełny. Spróbuj ponownie później.'})
                    conn.close()
        except socket.timeout:
            pass
        except Exception as e:
            print(f"Error accepting connection: {e}")
            break

    server_socket.close()
    print("Server shut down.")

if __name__ == "__main__":
    start_server()