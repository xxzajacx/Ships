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
        
        # Zmieniono sposób zarządzania klientami, aby uniknąć pomyłek z `self.clients` jako listą
        # Teraz `self.players` będzie głównym źródłem prawdy o połączonych graczach.
        self.players = { 
            0: {'client_conn': None, 'name': 'Gracz 1', 'ships': [], 'all_ship_coords': set(), 'hits_on_me': set(), 'my_shots_on_enemy': set(), 'my_shots_confirmed_hits': set(), 'difficulty': None},
            1: {'client_conn': None, 'name': 'Gracz 2', 'ships': [], 'all_ship_coords': set(), 'hits_on_me': set(), 'my_shots_on_enemy': set(), 'my_shots_confirmed_hits': set(), 'difficulty': None}
        }
        self.lock = threading.Lock()  # Blokada do synchronizacji dostępu do współdzielonych zasobów
        
        self.game_started = False
        self.current_player_turn = 0 # 0 lub 1
        self.players_ready = [False, False] # Czy gracze rozmiescili statki
        
        self.difficulty_settings = {
            'easy': {'ships': [4, 3, 3, 2, 2, 2, 1, 1, 1, 1], 'board_size': 10},
            'medium': {'ships': [5, 4, 4, 3, 3, 2, 2, 1, 1], 'board_size': 12},
            'hard': {'ships': [6, 5, 4, 3, 3, 2, 2, 1, 1], 'board_size': 15}
        }
        self.game_difficulty = None # Ustawiane po połączeniu pierwszego gracza i będzie używane dla obu graczy
        self.board_size = 0 # Ustawiane na podstawie game_difficulty

        self.scores_file = "scores.json"
        self.scores = self.load_scores()

        self.accept_connections()

    def load_scores(self):
        if os.path.exists(self.scores_file):
            with open(self.scores_file, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    print("[Server] Błąd odczytu pliku scores.json, tworzę nowy pusty.")
                    return []
        return []

    def save_scores(self):
        with open(self.scores_file, 'w') as f:
            json.dump(self.scores, f, indent=4)

    def accept_connections(self):
        while True:
            # Akceptuj połączenia tylko, jeśli jest mniej niż 2 graczy z aktywnym socketem
            active_player_slots = sum(1 for p_id in [0, 1] if self.players[p_id]['client_conn'] and self.players[p_id]['client_conn'].fileno() != -1)
            
            if active_player_slots < 2:
                conn, addr = self.server.accept()
                print(f"[Server] Połączono z {addr}")
                
                with self.lock:
                    player_id = -1 
                    # Znajdź wolne ID gracza (0 lub 1)
                    if not self.players[0]['client_conn'] or self.players[0]['client_conn'].fileno() == -1:
                        player_id = 0
                    elif not self.players[1]['client_conn'] or self.players[1]['client_conn'].fileno() == -1:
                        player_id = 1
                    else:
                        print("[Server] Błąd logiczny: Próba przypisania ID gracza, gdy oba sloty są zajęte.")
                        self.send_message_direct(conn, "ERROR:Internal server error. Please try again.\n")
                        conn.close()
                        continue
                    
                    # Resetuj stan dla tego gracza przed ponownym przypisaniem połączenia
                    self.players[player_id] = {
                        'name': f"Gracz {player_id+1}",
                        'ships': [],
                        'all_ship_coords': set(),
                        'hits_on_me': set(),
                        'my_shots_on_enemy': set(), # KLUCZOWE: RESETOWANIE
                        'my_shots_confirmed_hits': set(), # KLUCZOWE: RESETOWANIE
                        'client_conn': conn,
                        'difficulty': None 
                    }
                    
                thread = threading.Thread(target=self.handle_client, args=(conn, player_id))
                thread.daemon = True
                thread.start()
            else:
                # Ogranicz liczbę połączeń do 2
                conn, addr = self.server.accept() 
                print(f"[Server] Odrzucono połączenie z {addr} - serwer pełny.")
                self.send_message_direct(conn, "ERROR:Server is full. Try again later.\n")
                conn.close() 
                time.sleep(1) 


    def handle_client(self, conn, player_id):
        buffer = "" # Bufor do przechowywania niepełnych wiadomości
        try:
            while True:
                data = conn.recv(4096).decode()
                if not data:
                    print(f"[Server] Klient {player_id} rozłączył się (pusta wiadomość).")
                    self.root.after(0, self.handle_disconnection)
                    break
                
                buffer += data
                while "\n" in buffer:
                    message, buffer = buffer.split("\n", 1)
                    if not message:
                        continue
                    print(f"[Server] Otrzymano od gracza {player_id}: {message}")
                    self.process_client_message(player_id, message)

        except (ConnectionResetError, BrokenPipeError):
            print(f"[Server] Klient {player_id} nagle rozłączył się (ConnectionResetError/BrokenPipeError).")
            self.handle_disconnection(player_id)
        except Exception as e:
            print(f"[Server] Błąd obsługi klienta {player_id}: {e}")
            self.handle_disconnection(player_id)

    def process_client_message(self, player_id, message):
        with self.lock:
            try:
                # Try to parse as JSON first
                parsed_json = None
                try:
                    parsed_json = json.loads(message)
                except json.JSONDecodeError:
                    pass # Not a JSON message

                msg_type = ""
                # If successfully parsed as JSON and has a 'type' key
                if isinstance(parsed_json, dict) and "type" in parsed_json:
                    msg_type = parsed_json["type"]
                else:
                    # Otherwise, it's a plain string message (e.g., CONNECT:...)
                    parts = message.split(":", 1)
                    msg_type = parts[0]
                    # For CONNECT message, msg_data will be extracted directly from 'message' in the 'if' block below.


                if msg_type == "CONNECT":
                    # This is a string message, so use the original split logic
                    parts = message.split(":")
                    name = parts[1]
                    difficulty_chosen_by_client = parts[2]
                    self.players[player_id]['name'] = name
                    self.players[player_id]['difficulty'] = difficulty_chosen_by_client
                    
                    if self.game_difficulty is None:
                        self.game_difficulty = difficulty_chosen_by_client
                        self.board_size = self.difficulty_settings[self.game_difficulty]['board_size']
                        print(f"[Server] Ustawiono poziom trudności gry na: {self.game_difficulty} (rozmiar planszy: {self.board_size})")
                    elif self.game_difficulty != difficulty_chosen_by_client:
                        print(f"[Server] Ostrzeżenie: Gracz {name} wybrał trudność '{difficulty_chosen_by_client}', ale gra jest ustawiona na '{self.game_difficulty}'. Narzucam trudność gry.")
                        self.players[player_id]['difficulty'] = self.game_difficulty
                    
                    connected_and_configured_players = 0
                    for p_id in [0, 1]:
                        if p_id in self.players and self.players[p_id]['client_conn'] and self.players[p_id]['client_conn'].fileno() != -1 and self.players[p_id]['difficulty'] is not None:
                            connected_and_configured_players += 1

                    if connected_and_configured_players == 2:
                        ships_for_setup = self.difficulty_settings[self.game_difficulty]['ships']
                        for p_id in [0, 1]:
                            if self.players[p_id]['client_conn'] and self.players[p_id]['client_conn'].fileno() != -1:
                                self.send_message(p_id, f"START_SETUP:{self.board_size}:{json.dumps(ships_for_setup)}")
                                self.players_ready[p_id] = False 
                        print("[Server] Obydwa klienty podłączone i gotowe do ustawiania statków.")
                    else:
                        self.send_message(player_id, "WAITING_FOR_OPPONENT:")


                elif msg_type == "SHIPS_PLACED":
                    # This is a JSON message, so 'parsed_json' contains the data
                    if parsed_json is None: # Should not happen if msg_type was correctly identified
                        self.send_message(player_id, "ERROR:Nieprawidłowy format wiadomości (oczekiwano JSON).")
                        return

                    data = parsed_json # The entire parsed JSON is the data for SHIPS_PLACED
                    
                    received_ship_lengths = sorted([s['length'] for s in data['ships']], reverse=True)
                    expected_ship_lengths = sorted(self.difficulty_settings[self.game_difficulty]['ships'], reverse=True)

                    if received_ship_lengths != expected_ship_lengths:
                        print(f"[Server] Błąd: gracz {player_id} wysłał nieprawidłowy zestaw statków.")
                        self.send_message(player_id, "ERROR:Nieprawidłowe statki lub ich liczba.")
                        return

                    all_coords = set()
                    self.players[player_id]['ships'] = [] 
                    for ship_data in data['ships']:
                        coords = [tuple(c) for c in ship_data['coords']]
                        self.players[player_id]['ships'].append({
                            'coords': coords,
                            'hits': set(), 
                            'length': ship_data['length'],
                            'orientation': ship_data['orientation']
                        })
                        for r, c in coords:
                            all_coords.add((r, c))

                    self.players[player_id]['all_ship_coords'] = all_coords
                    self.players_ready[player_id] = True
                    print(f"[Server] Gracz {self.players[player_id]['name']} rozmieścił statki.")
                    
                    if all(self.players_ready) and \
                       self.players[0]['client_conn'] and self.players[0]['client_conn'].fileno() != -1 and \
                       self.players[1]['client_conn'] and self.players[1]['client_conn'].fileno() != -1:
                        print("[Server] Obaj gracze gotowi. Rozpoczynamy grę!")
                        self.start_game()
                    else:
                        self.send_message(player_id, "WAITING_FOR_OPPONENT:")


                elif msg_type == "SHOT":
                    # This is a JSON message, so 'parsed_json' contains the data
                    if parsed_json is None: # Should not happen if msg_type was correctly identified
                        self.send_message(player_id, "ERROR:Nieprawidłowy format wiadomości (oczekiwano JSON).")
                        return
                    
                    if not self.game_started or player_id != self.current_player_turn:
                        print(f"[Server] Gracz {player_id} próbował strzelać poza swoją turą lub przed startem gry.")
                        self.send_message(player_id, "ERROR:Nie twoja kolej lub gra nie wystartowała.")
                        return

                    coords = parsed_json["coords"] # Extract coords from parsed JSON
                    r, c = tuple(coords)
                    
                    opponent_id = 1 - player_id
                    
                    if not (0 <= r < self.board_size and 0 <= c < self.board_size):
                        self.send_message(player_id, "ERROR:Strzał poza planszę.")
                        return

                    if (r, c) in self.players[player_id]['my_shots_on_enemy']:
                        self.send_message(player_id, "ERROR:Już strzelałeś w to pole.")
                        return

                    self.players[player_id]['my_shots_on_enemy'].add((r, c)) 

                    hit = False
                    sunk_ship = None
                    
                    if (r, c) in self.players[opponent_id]['all_ship_coords']:
                        hit = True
                        self.players[opponent_id]['hits_on_me'].add((r, c)) 
                        self.players[player_id]['my_shots_confirmed_hits'].add((r, c)) 

                        for ship in self.players[opponent_id]['ships']:
                            if (r, c) in ship['coords']:
                                ship['hits'].add((r, c))
                                if len(ship['hits']) == ship['length']:
                                    sunk_ship = ship
                                    print(f"[Server] Statek gracza {self.players[opponent_id]['name']} ({ship['length']} pól) zatonął!")
                                break
                    
                    if not hit:
                        self.current_player_turn = opponent_id
                    
                    print(f"[Server] Strzał ({r},{c}) gracza {self.players[player_id]['name']}: {'TRAFIENIE!' if hit else 'PUDŁO.'}. Nowa tura gracza {self.players[self.current_player_turn]['name']}.")
                    
                    self.send_game_state()
                    self.check_game_over()


                elif msg_type == "DISCONNECT": 
                    print(f"[Server] Klient {player_id} wysłał DISCONNECT.")
                    self.handle_disconnection(player_id)
                
                else:
                    print(f"[Server] Nieznana wiadomość od gracza {player_id}: {message}")

            except Exception as e:
                print(f"[Server] Nieoczekiwany błąd podczas przetwarzania wiadomości od gracza {player_id}: {e}. Wiadomość: '{message}'")
                self.send_message(player_id, "ERROR:Wewnętrzny błąd serwera.")


    def send_message(self, player_id, message):
        try:
            if player_id in self.players and \
               self.players[player_id]['client_conn'] and \
               self.players[player_id]['client_conn'].fileno() != -1: 
                self.players[player_id]['client_conn'].sendall((message + "\n").encode())
            else:
                print(f"[Server] Próba wysłania wiadomości do nieistniejącego lub rozłączonego klienta {player_id}.")
        except (ConnectionResetError, BrokenPipeError):
            print(f"[Server] Błąd wysyłania do klienta {player_id}, prawdopodobnie rozłączony.")
            self.handle_disconnection(player_id)
        except Exception as e:
            print(f"[Server] Nieoczekiwany błąd wysyłania do klienta {player_id}: {e}")
            self.handle_disconnection(player_id)
    
    def send_message_direct(self, conn, message):
        """Wysyła wiadomość do podanego obiektu socket, bez sprawdzania player_id."""
        try:
            if conn and conn.fileno() != -1:
                conn.sendall(message.encode())
        except (ConnectionResetError, BrokenPipeError):
            print(f"[Server] Błąd wysyłania do klienta (bez ID), prawdopodobnie rozłączony.")
        except Exception as e:
            print(f"[Server] Nieoczekiwany błąd wysyłania (bez ID): {e}")


    def start_game(self):
        self.game_started = True
        self.current_player_turn = random.choice([0, 1]) # Losuj, kto zaczyna
        print(f"[Server] Gra rozpoczęta! Zaczyna gracz: {self.players[self.current_player_turn]['name']}")
        
        for i in [0, 1]:
            if self.players[i]['client_conn'] and self.players[i]['client_conn'].fileno() != -1:
                self.send_message(i, f"GAME_START:{self.current_player_turn == i}")
        
        self.send_game_state()

    def send_game_state(self):
        # Wysyłaj aktualny stan planszy do obu graczy
        for i in [0, 1]:
            player = self.players.get(i)
            if player and player['client_conn'] and player['client_conn'].fileno() != -1:
                opponent_id = 1 - i
                
                # Strzały przeciwnika (do narysowania na mojej planszy) - wszystkie strzały, które spadły na moją planszę
                enemy_shots_coords = list(self.players[opponent_id]['my_shots_on_enemy'])

                # Stan planszy przeciwnika (moje trafienia u przeciwnika)
                my_shots_confirmed_hits_coords = list(self.players[i]['my_shots_confirmed_hits'])
                
                game_state_data = {
                    'my_board_hits': [], # To pole jest de facto nieużywane już przez klienta
                    'enemy_board_hits': my_shots_confirmed_hits_coords, # Koordynaty moich trafień u przeciwnika (tylko trafienia)
                    'my_turn': (self.current_player_turn == i),
                    'enemy_shots': enemy_shots_coords # Wszystkie strzały przeciwnika na mojej planszy (do wizualizacji pudel i trafień)
                }
                
                try:
                    self.send_message(i, f"UPDATE_BOARD:{json.dumps(game_state_data)}")
                except Exception: 
                    pass # send_message już loguje błąd


    def check_game_over(self):
        if not self.game_started:
            return

        for player_id in [0, 1]:
            player_data = self.players.get(player_id)
            opponent_id = 1 - player_id
            
            # Sprawdź, czy gracz nadal jest połączony i ma statki
            if player_data and player_data['client_conn'] and player_data['client_conn'].fileno() != -1 and player_data['all_ship_coords']:
                all_ship_coords = player_data['all_ship_coords']
                hits_on_me = player_data['hits_on_me']

                # Jeśli wszystkie pola zajmowane przez statki gracza zostały trafione
                if all(coord in hits_on_me for coord in all_ship_coords):
                    print(f"[Server] Gracz {self.players[player_id]['name']} stracił wszystkie statki. Gracz {self.players[opponent_id]['name']} wygrał!")
                    self.end_game(opponent_id, win_type="WIN")
                    return
            
            # Dodatkowy warunek: jeśli jeden z graczy rozłączył się podczas gry
            # Musimy sprawdzić, czy OBA sloty graczy istnieją i czy mają aktywne połączenia
            active_player_count = 0
            for p_id in [0, 1]:
                if p_id in self.players and self.players[p_id]['client_conn'] and self.players[p_id]['client_conn'].fileno() != -1:
                    active_player_count += 1
            
            if self.game_started and active_player_count < 2:
                # Znajdź połączonego gracza
                connected_player_id = None
                for p_id in [0, 1]:
                    if p_id in self.players and self.players[p_id]['client_conn'] and self.players[p_id]['client_conn'].fileno() != -1:
                        connected_player_id = p_id
                        break
                
                if connected_player_id is not None:
                    print(f"[Server] Gracz {self.players[connected_player_id]['name']} wygrywa z powodu rozłączenia przeciwnika.")
                    self.end_game(connected_player_id, win_type="WIN_DISCONNECT")
                else: # Nikt nie jest połączony
                    print("[Server] Obaj gracze rozłączeni. Gra zakończona bez zwycięzcy.")
                    self.reset_server_state()
                return 

    def handle_disconnection(self, disconnected_player_id):
        with self.lock:
            # Upewnij się, że obiekt gracza istnieje i ma aktywne połączenie, zanim spróbujesz go zamknąć
            if disconnected_player_id not in self.players or \
               not self.players[disconnected_player_id]['client_conn'] or \
               self.players[disconnected_player_id]['client_conn'].fileno() == -1:
                return # Już obsłużono lub klient nie istnieje/był rozłączony

            print(f"[Server] Obsługa rozłączenia gracza {disconnected_player_id} ({self.players[disconnected_player_id]['name']})")
            
            # Zamknij socket dla rozłączonego gracza
            try:
                self.players[disconnected_player_id]['client_conn'].shutdown(socket.SHUT_RDWR)
                self.players[disconnected_player_id]['client_conn'].close()
            except OSError as e:
                print(f"[Server] Błąd zamykania gniazda dla gracza {disconnected_player_id}: {e}")
            except Exception as e:
                print(f"[Server] Nieoczekiwany błąd podczas zamykania gniazda dla gracza {disconnected_player_id}: {e}")
            
            # Oznacz client_conn jako None, aby wskazać, że gracz jest rozłączony
            self.players[disconnected_player_id]['client_conn'] = None

            # Sprawdź, ilu klientów jest nadal aktywnych (nie None i nie zamknięte fileno)
            active_clients_count = sum(1 for p_id in [0, 1] if p_id in self.players and self.players[p_id]['client_conn'] and self.players[p_id]['client_conn'].fileno() != -1)
            
            if self.game_started:
                if active_clients_count == 1:
                    remaining_player_id = None
                    for p_id in [0, 1]:
                        if p_id in self.players and self.players[p_id]['client_conn'] and self.players[p_id]['client_conn'].fileno() != -1:
                            remaining_player_id = p_id
                            break
                    print(f"[Server] Gracz {self.players[remaining_player_id]['name']} wygrywa z powodu rozłączenia przeciwnika.")
                    self.end_game(remaining_player_id, win_type="WIN_DISCONNECT")
                else: # 0 aktywnych klientów
                    print("[Server] Obaj gracze rozłączeni. Gra zakończona bez zwycięzcy.")
                    self.reset_server_state()
            else: # Jeśli jeszcze nie rozpoczęto gry (faza setupu lub oczekiwania)
                 print("[Server] Gracz rozłączył się przed startem gry. Resetuję stan serwera.")
                 self.reset_server_state()


    def reset_server_state(self):
        # Resetowanie stanu serwera do początkowego
        # Upewnij się, że wszystkie sockety są zamknięte
        for p_id in [0, 1]:
            player_data = self.players.get(p_id)
            if player_data and player_data['client_conn'] and player_data['client_conn'].fileno() != -1:
                try:
                    player_data['client_conn'].shutdown(socket.SHUT_RDWR)
                    player_data['client_conn'].close()
                except OSError:
                    pass 

        # Całkowicie zresetuj graczy
        self.players = { 
            0: {'client_conn': None, 'name': 'Gracz 1', 'ships': [], 'all_ship_coords': set(), 'hits_on_me': set(), 'my_shots_on_enemy': set(), 'my_shots_confirmed_hits': set(), 'difficulty': None},
            1: {'client_conn': None, 'name': 'Gracz 2', 'ships': [], 'all_ship_coords': set(), 'hits_on_me': set(), 'my_shots_on_enemy': set(), 'my_shots_confirmed_hits': set(), 'difficulty': None}
        }
        self.game_started = False
        self.current_player_turn = 0
        self.players_ready = [False, False] 
        self.game_difficulty = None
        self.board_size = 0
        print("[Server] Stan serwera zresetowany.")


    def end_game(self, winner_id, win_type="WIN"):
        """Kończy grę i zapisuje wynik."""
        winner_name = self.players[winner_id]['name']
        
        # Znajdź nazwę przegranego. Jeśli rozłączony, ustaw domyślną.
        loser_id = 1 - winner_id
        loser_name = "Nieznany (rozłączony)"
        # Sprawdzamy, czy loser_id istnieje i ma przypisaną nazwę.
        if loser_id in self.players and self.players[loser_id] and self.players[loser_id].get('name'): 
             loser_name = self.players[loser_id]['name']
        else:
            # Jeśli loser_id nie istnieje lub nie ma nazwy, poszukaj drugiego gracza w players_ready
            # który nie jest winner_id, a jego połączenie jest None
            for p_id in [0,1]:
                if p_id != winner_id and p_id in self.players and (not self.players[p_id]['client_conn'] or self.players[p_id]['client_conn'].fileno() == -1):
                    loser_name = self.players[p_id].get('name', f"Gracz {p_id+1} (rozłączony)")
                    break


        print(f"[Server] Game over! Winner: {winner_name}")
        
        if win_type == "WIN": # Zapisz wynik tylko jeśli to była "prawdziwa" wygrana
            self.scores.append({
                'winner': winner_name,
                'loser': loser_name,
                'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
                'difficulty': self.game_difficulty
            })
            self.save_scores()
        
        score_data = json.dumps(self.scores)
        for i in [0, 1]:
            player_data = self.players.get(i)
            if player_data and player_data['client_conn'] and player_data['client_conn'].fileno() != -1: 
                try:
                    if i == winner_id:
                        player_data['client_conn'].sendall(f"GAME_OVER:{win_type}:{score_data}\n".encode())
                    else: # Przegrany
                        player_data['client_conn'].sendall(f"GAME_OVER:LOSE:{score_data}\n".encode())
                except (ConnectionResetError, BrokenPipeError) as e:
                    print(f"[Server] Klient {i} rozłączył się podczas game over: {e}.")
                    player_data['client_conn'] = None 
                    continue
                except Exception as e:
                    print(f"[Server] Nieoczekiwany błąd wysyłania GAME_OVER do klienta {i}: {e}")
                    player_data['client_conn'] = None
                    continue
        
        self.game_started = False
        self.reset_server_state() 

if __name__ == "__main__":
    BattleshipServer()