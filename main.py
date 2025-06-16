import socket
import threading
import json
import random
from datetime import datetime
import os
import time

HOST = '127.0.0.1'

class BattleshipServer:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        ports_to_try = [12345, 12346, 12347]
        bound_successfully = False
        for port in ports_to_try:
            try:
                self.server.bind((HOST, port))
                print(f"[Server] Started server on {HOST}:{port}")
                bound_successfully = True
                break
            except OSError as e:
                print(f"[Server] Port {port} is already in use: {e}. Trying next port...")
                time.sleep(0.5)
        
        if not bound_successfully:
            print("[Server] Could not bind to any available port. Exiting.")
            exit()

        self.server.listen(2)
        
        self.clients = []  # Lista obiektów socket dla klientów
        self.players = {}  # Słownik przechowujący dane graczy: {player_id: {name, ships, all_ship_coords, hits, client, my_shots}}
        self.lock = threading.Lock()  # Blokada do synchronizacji dostępu do współdzielonych zasobów
        self.current_turn = 0 # Id gracza, który ma turę
        self.game_started = False # Flaga informująca, czy gra się rozpoczęła
        self.difficulty = None  # Ustawiony poziom trudności
        self.board_size = 10 # Rozmiar planszy (domyślny)
        self.ship_configs = { # Konfiguracje statków dla różnych poziomów trudności
            'easy': {'board_size': 10, 'ships': [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]},
            'medium': {'board_size': 14, 'ships': [5, 4, 4, 3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1]},
            'hard': {'board_size': 20, 'ships': [6, 5, 5, 4, 4, 4, 3, 3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1]}
        }
        self.scores = self.load_scores()  # Załadowane wyniki gier
        self.start_server()

    def load_scores(self):
        """Ładuje wyniki gier z pliku scores.json."""
        if os.path.exists('scores.json'):
            with open('scores.json', 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    print("[Server] Error decoding scores.json. Starting with empty scores.")
                    return []
        return []

    def save_scores(self):
        """Zapisuje bieżące wyniki gier do pliku scores.json."""
        with open('scores.json', 'w') as f:
            json.dump(self.scores, f, indent=4) # Użyj indent dla czytelniejszego formatu JSON

    def start_server(self):
        """Akceptuje przychodzące połączenia klientów."""
        while True:
            client, addr = self.server.accept()
            print(f"[Server] Connected to {addr}")
            
            with self.lock:
                # Jeśli jest już 2 graczy, odrzuć połączenie
                if len([c for c in self.clients if c is not None]) >= 2:
                    print(f"[Server] Rejected connection - already 2 players")
                    client.sendall("SERVER_FULL\n".encode())
                    client.close()
                    continue
                
                # Przypisz player_id do klienta (0 lub 1)
                player_id = 0 if not self.clients or self.clients[0] is None else 1
                if player_id >= len(self.clients):
                    self.clients.append(client)
                else:
                    self.clients[player_id] = client # Zastąp None nowym klientem
                
                threading.Thread(target=self.handle_client, args=(client, player_id)).start()

    def handle_client(self, client, player_id):
        """Obsługuje komunikację z podłączonym klientem."""
        player_name = None

        while True:
            try:
                data = client.recv(1024).decode().strip()
                if not data:
                    break # Klient się rozłączył

                if ":" in data:
                    command, payload = data.split(":", 1)
                else:
                    command = data
                    payload = None

                if command == "SET_NAME":
                    player_name = payload
                    with self.lock:
                        self.players[player_id] = {
                            "name": player_name,
                            "ships": [], # Lista list krotek (statek jako lista koordynatów)
                            "all_ship_coords": set(), # Zbiór wszystkich koordynatów zajmowanych przez statki
                            "hits": set(), # Koordynaty trafione na planszy tego gracza
                            "client": client,
                            "my_shots": set() # Koordynaty strzelone przez tego gracza
                        }
                    print(f"[Server] Player {player_id} set name: {player_name}")

                elif command == "SET_DIFFICULTY":
                    with self.lock:
                        if self.difficulty is None:
                            self.difficulty = payload
                            self.board_size = self.ship_configs[self.difficulty]['board_size']
                            client.sendall(f"DIFFICULTY_ACCEPTED:{self.board_size},{sum(self.ship_configs[self.difficulty]['ships'])}\n".encode())
                        else:
                            client.sendall(f"DIFFICULTY_FORCED:{self.difficulty}:{self.board_size},{sum(self.ship_configs[self.difficulty]['ships'])}\n".encode())

                elif command == "SET_SHIPS":
                    try:
                        ships_data = json.loads(payload)
                        # Konwertujemy listy koordynatów na krotki koordynatów i krotki statków
                        ships_as_tuples = [tuple(tuple(c) for c in ship) for ship in ships_data]
                        all_coords_set = set(coord for ship in ships_as_tuples for coord in ship)
                        
                        with self.lock:
                            self.players[player_id]["ships"] = ships_as_tuples
                            self.players[player_id]["all_ship_coords"] = all_coords_set

                        print(f"[Server] Player {player_id} set ships: {len(ships_as_tuples)} ships. Total cells: {len(all_coords_set)}")

                        # Sprawdź, czy obaj gracze ustawili statki i czy ich liczba pól jest zgodna z konfiguracją
                        expected_total_ship_cells = sum(self.ship_configs[self.difficulty]['ships'])
                        
                        players_ready_for_game = 0
                        for p_id, p_data in self.players.items():
                            if "all_ship_coords" in p_data and len(p_data["all_ship_coords"]) == expected_total_ship_cells:
                                players_ready_for_game += 1

                        if players_ready_for_game == 2 and not self.game_started:
                            self.start_game()
                    except (json.JSONDecodeError, KeyError) as e:
                        print(f"[Server] Error parsing ships from player {player_id}: {e}")

                elif command == "SHOT":
                    if self.game_started and player_id == self.current_turn:
                        x, y = map(int, payload.split(","))
                        # Walidacja, czy strzał w ogóle jest na planszy
                        if not (0 <= x < self.board_size and 0 <= y < self.board_size):
                            client.sendall("INVALID_SHOT\n".encode())
                            print(f"[Server] Player {player_id} - Invalid shot coords: {x},{y}")
                            continue

                        # Walidacja, czy strzał nie był już wcześniej oddany w tym miejscu
                        if (x, y) in self.players[player_id].get('my_shots', set()):
                            client.sendall("DUPLICATE_SHOT\n".encode())
                            print(f"[Server] Player {player_id} - Duplicate shot: {x},{y}")
                            continue

                        self.process_shot(player_id, x, y)
                    else:
                        print(f"[Server] Player {player_id} tried to shoot out of turn or before game started.")

                elif command == "REMATCH_REQUEST":
                    target_id = 1 - player_id
                    if target_id in self.players and self.players[target_id]["client"]:
                        self.players[target_id]["client"].sendall(f"REMATCH_REQUEST:{player_name}\n".encode())
                    else:
                        print(f"[Server] Opponent for player {player_id} not found for rematch request.")

                elif command == "REMATCH_RESPONSE":
                    target_id = 1 - player_id
                    if target_id in self.players and self.players[target_id]["client"]:
                        self.players[target_id]["client"].sendall(f"REMATCH_RESPONSE:{payload}\n".encode())
                        if payload == "ACCEPT":
                            # Czekamy na drugiego gracza, jeśli obaj zaakceptują, nastąpi reset
                            self.players[player_id]['rematch_accepted'] = True
                            if 'rematch_accepted' in self.players.get(target_id, {}) and self.players[target_id]['rematch_accepted']:
                                time.sleep(1) 
                                self.reset_game()
                            else:
                                print(f"[Server] Player {player_name} accepted rematch. Waiting for {self.players[target_id]['name']}.")
                        else:
                            # Jeśli odrzucono, zresetuj stan serwera i poinformuj drugiego gracza
                            print(f"[Server] Player {player_name} declined rematch.")
                            if 'rematch_accepted' in self.players.get(target_id, {}):
                                del self.players[target_id]['rematch_accepted'] # Wyczyść flagę zaakceptowania u drugiego gracza
                            
                            # Jeśli jest drugi gracz, poinformuj go, że rewanż został odrzucony
                            if target_id in self.players and self.players[target_id]["client"]:
                                self.players[target_id]["client"].sendall("REMATCH_RESPONSE:DECLINE\n".encode())
                            self.reset_server_state_for_new_game() # Reset serwera do stanu początkowego

            except (ConnectionResetError, BrokenPipeError) as e:
                print(f"[Server] Connection error with player {player_id} ({player_name}): {e}")
                break
            except Exception as e:
                print(f"[Server] Other error with player {player_id} ({player_name}): {e}")
                break

        # Obsługa rozłączenia klienta
        with self.lock:
            if player_id in self.players:
                disconnected_player_name = self.players[player_id]['name']
                del self.players[player_id]
                # Ustaw klienta na None w liście, zamiast usuwać, żeby nie zmieniać indeksów podczas gry
                if player_id < len(self.clients):
                    self.clients[player_id] = None 
                
                print(f"[Server] Player {disconnected_player_name} ({player_id}) disconnected.")
                
                # Jeśli gra była w trakcie i jeden z graczy się rozłączył, zakończ grę dla pozostałego
                if self.game_started and any(c is not None for c in self.clients):
                    remaining_player_id = None
                    for i, client_obj in enumerate(self.clients):
                        if client_obj is not None and i in self.players: # Sprawdź, czy klient jest aktywny i czy są jego dane
                            remaining_player_id = i
                            break
                    
                    if remaining_player_id is not None:
                        try:
                            # Poinformuj pozostałego gracza o rozłączeniu przeciwnika i zakończeniu gry z wygraną
                            self.clients[remaining_player_id].sendall("GAME_OVER:WIN_DISCONNECT\n".encode())
                            print(f"[Server] Player {self.players[remaining_player_id]['name']} won due to opponent disconnect.")
                        except (ConnectionResetError, BrokenPipeError):
                            print(f"[Server] Remaining client also disconnected before receiving game over message.")
                    self.game_started = False
                    self.reset_server_state_for_new_game() # Reset serwera po rozłączeniu podczas gry
                elif not self.game_started and len([c for c in self.clients if c is not None]) == 0:
                    # Jeśli nie ma już żadnych podłączonych klientów, zresetuj serwer całkowicie
                    self.reset_server_state_for_new_game()

        client.close()


    def reset_server_state_for_new_game(self):
        """Resetuje stan serwera dla zupełnie nowej gry (np. po rozłączeniu obu graczy)."""
        self.players.clear()
        self.clients = []
        self.game_started = False
        self.current_turn = 0
        self.difficulty = None
        self.board_size = 10
        print("[Server] Server state completely reset. Waiting for new players.")


    def reset_game(self):
        """Resetuje stan gry dla rewanżu (zachowuje graczy)."""
        print("[Server] Resetting game state for rematch...")
        self.game_started = False
        self.current_turn = random.randint(0, 1) # Losuj, kto zaczyna rewanż

        # Wyczyść dane graczy związane z bieżącą grą
        for player_id in self.players:
            self.players[player_id]['ships'] = []
            self.players[player_id]['hits'] = set()
            self.players[player_id]['all_ship_coords'] = set()
            self.players[player_id]['my_shots'].clear()
            if 'rematch_accepted' in self.players[player_id]:
                del self.players[player_id]['rematch_accepted'] # Usuń flagę akceptacji rewanżu

        # Poinformuj klientów o resecie i nowej turze
        for i, client in enumerate(self.clients):
            if client:
                try:
                    client.sendall("RESET\n".encode()) # Informuj klienta o resecie
                    time.sleep(0.5) 
                    if i == self.current_turn:
                        client.sendall("YOUR_TURN\n".encode())
                    else:
                        client.sendall("WAIT\n".encode())
                except (ConnectionResetError, BrokenPipeError):
                    print(f"[Server] Client {i} disconnected during reset.")
                    self.clients[i] = None 
                    continue
        print("[Server] Game state reset. Clients notified for new ship placement.")


    def start_game(self):
        """Rozpoczyna grę, gdy obaj gracze są gotowi."""
        print("[Server] Starting game!")
        self.game_started = True
        self.current_turn = random.randint(0, 1) # Losuj, kto zaczyna

        for i, client in enumerate(self.clients):
            if client:
                try:
                    client.sendall("START\n".encode())
                    if i == self.current_turn:
                        client.sendall("YOUR_TURN\n".encode())
                    else:
                        client.sendall("WAIT\n".encode())
                except (ConnectionResetError, BrokenPipeError):
                    print(f"[Server] Client {i} disconnected during game start.")
                    self.clients[i] = None 
                    continue

    def process_shot(self, shooter_id, x, y):
        """Przetwarza strzał gracza i aktualizuje stan gry."""
        target_id = 1 - shooter_id
        # Sprawdź, czy cel istnieje i jest aktywny
        if target_id not in self.players or not self.players[target_id]["client"]:
            print(f"[Server] Target player {target_id} not found or disconnected during shot processing.")
            return

        target = self.players[target_id]

        self.players[shooter_id]['my_shots'].add((x, y)) # Dodaj strzał do historii strzałów strzelającego

        is_hit = False
        # Sprawdzamy, czy trafiono którekolwiek pole statku przeciwnika
        if (x, y) in target["all_ship_coords"]:
            is_hit = True

        if is_hit:
            self.clients[shooter_id].sendall(f"SHOT_RESULT:{x},{y}:HIT\n".encode())
            self.clients[target_id].sendall(f"ENEMY_SHOT:{x},{y}:HIT\n".encode())

            self.players[target_id]["hits"].add((x, y)) # Dodaj trafione pole do zbioru trafień na planszy celu

            # Sprawdź, czy statek został zatopiony
            sunk_any_ship = False
            for ship in target["ships"]: # "ships" zawiera listę krotek (części statku)
                if all(part in self.players[target_id]["hits"] for part in ship):
                    sunk_any_ship = True
                    break
            
            if sunk_any_ship:
                self.clients[shooter_id].sendall("SHIP_SUNK\n".encode()) 
                self.clients[target_id].sendall("YOUR_SHIP_SUNK\n".encode())

            # Sprawdź, czy wszystkie statki przeciwnika zostały zatopione
            all_ships_sunk = True
            for ship_coord in target["all_ship_coords"]:
                if ship_coord not in self.players[target_id]["hits"]:
                    all_ships_sunk = False
                    break

            if all_ships_sunk:
                self.end_game(shooter_id)
                return 
            
            # Po trafieniu, strzelający ma kolejny ruch (nie zmieniamy tury)
            self.clients[shooter_id].sendall("YOUR_TURN\n".encode())
            self.clients[target_id].sendall("WAIT\n".encode())
        else:
            self.clients[shooter_id].sendall(f"SHOT_RESULT:{x},{y}:MISS\n".encode())
            self.clients[target_id].sendall(f"ENEMY_SHOT:{x},{y}:MISS\n".encode())
            time.sleep(0.1) # Krótka pauza przed zmianą tury
            self.switch_turn() # Zmień turę tylko po pudle

    def switch_turn(self):
        """Zmienia turę na drugiego gracza."""
        self.current_turn = 1 - self.current_turn
        for i, client in enumerate(self.clients):
            if client:
                try:
                    if i == self.current_turn:
                        client.sendall("YOUR_TURN\n".encode())
                    else:
                        client.sendall("WAIT\n".encode())
                except (ConnectionResetError, BrokenPipeError):
                    print(f"[Server] Client {i} disconnected during turn switch.")
                    self.clients[i] = None 
                    continue

    def end_game(self, winner_id):
        """Kończy grę i zapisuje wynik."""
        winner_name = self.players[winner_id]['name']
        loser_id = 1 - winner_id
        loser_name = self.players[loser_id]['name']
        print(f"[Server] Game over! Winner: {winner_name}")
        
        self.scores.append({
            'winner': winner_name,
            'loser': loser_name,
            'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
            'difficulty': self.difficulty
        })
        self.save_scores()
        
        score_data = json.dumps(self.scores)
        for i, client in enumerate(self.clients):
            if client:
                try:
                    if i == winner_id:
                        client.sendall(f"GAME_OVER:WIN:{score_data}\n".encode())
                    else:
                        client.sendall(f"GAME_OVER:LOSE:{score_data}\n".encode())
                except (ConnectionResetError, BrokenPipeError):
                    print(f"[Server] Client {i} disconnected during game over.")
                    self.clients[i] = None 
                    continue
        
        self.game_started = False

if __name__ == "__main__":
    BattleshipServer()

    #sprawdzenie portów 
    #scoreboard 
    #zakonczenie 