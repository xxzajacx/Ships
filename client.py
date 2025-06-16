import socket
import threading
import json
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
import time
from PIL import Image, ImageTk
import os

HOST = '127.0.0.1'

class BattleshipClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Statki - Gra Sieciowa")

        self.my_turn = False
        self.game_started = False
        self.enemy_shots = set() # Shots made by the enemy on my board (can be hits or misses)
        self.my_shots = set() # Shots I made on the enemy board (can be hits or misses)
        self.difficulty = None
        self.board_size = 10
        self.ship_lengths = []
        self.placed_ships = [] # List of dictionaries: {'id': 'ship_x_y', 'length': z, 'orientation': 'horiz/vert', 'coords': [(r,c)]}
        self.player_name = ""
        self.connected = False
        self.current_port = None
        self.enemy_hit_coords = set() # Confirmed hits I made on the enemy board (for drawing red marks)

        self.window_sizes = {
            'easy': '800x900', # Zwiększone rozmiary dla lepszego UI i większych plansz
            'medium': '1000x1000',
            'hard': '1200x1200'
        }

        self.ship_configs = {
            'easy': {'ships': [4, 3, 3, 2, 2, 2, 1, 1, 1, 1], 'board_size': 10},
            'medium': {'ships': [5, 4, 4, 3, 3, 2, 2, 1, 1], 'board_size': 12},
            'hard': {'ships': [6, 5, 4, 3, 3, 2, 2, 1, 1], 'board_size': 15}
        }

        self.client_socket = None
        self.all_assets = {}
        self.load_assets()

        # Zmienne do przeciągania statków
        self.dragging_ship = None # Ref do tk.Label statku
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.drag_image_id = None # ID tymczasowego obrazu na canvasie
        self.cell_size = 40 # Rozmiar komórki w pikselach (dopasowany do generate_assets.py)

        self.create_start_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def load_assets(self):
        assets_dir = "assets"
        if not os.path.exists(assets_dir):
            messagebox.showerror("Błąd", "Brak katalogu 'assets'. Uruchom generate_assets.py")
            self.root.destroy()
            return

        try:
            self.all_assets['sea'] = ImageTk.PhotoImage(Image.open(os.path.join(assets_dir, "sea.png")))
            self.all_assets['ship_part_horizontal'] = ImageTk.PhotoImage(Image.open(os.path.join(assets_dir, "ship_part_horizontal.png")))
            self.all_assets['ship_part_vertical'] = ImageTk.PhotoImage(Image.open(os.path.join(assets_dir, "ship_part_vertical.png")))
            self.all_assets['hit_mark'] = ImageTk.PhotoImage(Image.open(os.path.join(assets_dir, "hit_mark.png")))
            self.all_assets['miss_mark'] = ImageTk.PhotoImage(Image.open(os.path.join(assets_dir, "miss_mark.png")))
            self.all_assets['explosion'] = ImageTk.PhotoImage(Image.open(os.path.join(assets_dir, "explosion.png")))
            self.all_assets['water_splash'] = ImageTk.PhotoImage(Image.open(os.path.join(assets_dir, "water_splash.png")))
        except FileNotFoundError as e:
            messagebox.showerror("Błąd ładowania zasobów", f"Nie znaleziono pliku zasobów: {e}. Uruchom generate_assets.py")
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Błąd ładowania zasobów", f"Wystąpił błąd podczas ładowania zasobów: {e}")
            self.root.destroy()

    def create_start_screen(self):
        self.clear_window()

        self.root.geometry("400x300")

        self.name_label = tk.Label(self.root, text="Podaj swoje imię:")
        self.name_label.pack(pady=10)

        self.name_entry = tk.Entry(self.root)
        self.name_entry.pack(pady=5)
        self.name_entry.focus_set()

        self.difficulty_label = tk.Label(self.root, text="Wybierz poziom trudności:")
        self.difficulty_label.pack(pady=10)

        self.difficulty_var = tk.StringVar(self.root)
        self.difficulty_var.set("easy")
        self.difficulty_menu = ttk.OptionMenu(self.root, self.difficulty_var, "easy", "easy", "medium", "hard")
        self.difficulty_menu.pack(pady=5)

        self.start_button = tk.Button(self.root, text="Połącz i Rozpocznij Grę", command=self.connect_to_server)
        self.start_button.pack(pady=20)

    def connect_to_server(self):
        self.player_name = self.name_entry.get().strip()
        self.difficulty = self.difficulty_var.get()

        if not self.player_name:
            messagebox.showwarning("Błąd", "Imię gracza nie może być puste!")
            return

        # Te wartości będą nadpisane przez serwer, ale ustawiamy je jako początkowe
        # Nie ustawiamy tutaj self.board_size ani self.ship_lengths, bo one przyjdą z serwera w START_SETUP
        # Upewniamy się, że są puste, żeby nie było niespodzianek
        self.board_size = 0
        self.ship_lengths = []

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Próba połączenia z dostępnymi portami
            ports_to_try = [12345, 12346, 12347]
            connected_successfully = False
            for port in ports_to_try:
                try:
                    self.client_socket.connect((HOST, port))
                    self.current_port = port
                    connected_successfully = True
                    break
                except ConnectionRefusedError:
                    print(f"Port {port} odrzucił połączenie. Próbuję następny...")
                    time.sleep(0.5) # Krótka pauza przed kolejną próbą
            
            if not connected_successfully:
                messagebox.showerror("Błąd połączenia", "Nie udało się połączyć z serwerem na żadnym z dostępnych portów.")
                self.client_socket = None
                return

            self.connected = True
            # Wysyłamy informację o wybranej trudności
            self.client_socket.sendall(f"CONNECT:{self.player_name}:{self.difficulty}\n".encode())
            
            # Uruchomienie wątku do odbierania danych
            self.receive_thread = threading.Thread(target=self.receive_messages)
            self.receive_thread.daemon = True
            self.receive_thread.start()

            self.create_waiting_screen()

        except Exception as e:
            messagebox.showerror("Błąd połączenia", f"Nie można połączyć się z serwerem: {e}")
            self.connected = False

    def create_waiting_screen(self):
        self.clear_window()
        self.root.geometry("400x200")
        self.waiting_label = tk.Label(self.root, text="Oczekiwanie na drugiego gracza...", font=("Arial", 16))
        self.waiting_label.pack(pady=50)

    def create_setup_screen(self):
        self.clear_window()
        self.root.geometry(self.window_sizes[self.difficulty])

        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(expand=True, fill="both", padx=10, pady=10)

        # Sekcja lewa: Plansza gracza
        self.player_board_frame = tk.LabelFrame(self.main_frame, text="Twoja Plansza", padx=5, pady=5)
        self.player_board_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Ustawienie rozmiaru canvasu z uwzględnieniem miejsca na etykiety osi
        canvas_width = self.board_size * self.cell_size + self.cell_size # Dodatkowy cell_size na etykiety
        canvas_height = self.board_size * self.cell_size + self.cell_size # Dodatkowy cell_size na etykiety

        self.player_canvas = tk.Canvas(self.player_board_frame, bg="lightblue",
                                      width=canvas_width, height=canvas_height)
        self.player_canvas.pack()

        self.draw_grid(self.player_canvas, self.board_size, is_player_board=True)

        # Sekcja prawa: Panele statków do rozmieszczenia
        self.ships_to_place_frame = tk.LabelFrame(self.main_frame, text="Statki do rozmieszczenia", padx=5, pady=5)
        self.ships_to_place_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.ship_labels = [] # Resetuj listę etykiet za każdym razem, gdy tworzysz setup screen
        for i, length in enumerate(self.ship_lengths):
            frame = tk.Frame(self.ships_to_place_frame, bd=2, relief="groove")
            frame.pack(pady=5)
            
            ship_id = f"ship_{i}_{length}"

            label = tk.Label(frame) # Bez tekstu, bo tekst będzie obok obrazka
            label.pack(side="left", padx=5) # Spakuj obrazek

            text_label = tk.Label(frame, text=f"Statek {length} pól")
            text_label.pack(side="left", padx=5) # Spakuj tekst obok obrazka
            
            # Ustawiamy obrazek
            label.config(image=self.all_assets['ship_part_horizontal'])
            label.image = self.all_assets['ship_part_horizontal'] # Zachowaj referencję

            # Dodajemy atrybuty do labela, żeby łatwiej było śledzić statek
            label.ship_length = length
            label.ship_orientation = "horizontal" # Domyślna orientacja
            label.ship_coords_on_grid = [] # Będzie przechowywać koordynaty na siatce po upuszczeniu
            label.ship_id = ship_id # Unikalny ID dla statku

            self.ship_labels.append(label)

            # Bindowanie zdarzeń myszy do labela statku
            label.bind("<ButtonPress-1>", self.on_ship_drag_start)
            label.bind("<B1-Motion>", self.on_ship_drag)
            label.bind("<ButtonRelease-1>", self.on_ship_drag_end)
            label.bind("<ButtonPress-3>", self.on_ship_right_click) # Prawy przycisk dla obrotu

        self.place_ships_button = tk.Button(self.main_frame, text="Zatwierdź rozmieszczenie", command=self.send_ships_to_server, state="disabled")
        self.place_ships_button.grid(row=1, column=0, columnspan=2, pady=10)

        # Upewnij się, że kolumny i wiersze rozciągają się poprawnie
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

    def draw_grid(self, canvas, size, is_player_board=False):
        canvas.delete("all")
        
        # Obliczenie offsetu dla siatki (na etykiety osi)
        offset = self.cell_size
        
        # Rysowanie tła morza
        for r in range(size):
            for c in range(size):
                x1, y1 = c * self.cell_size + offset, r * self.cell_size + offset
                canvas.create_image(x1, y1, anchor="nw", image=self.all_assets['sea'])

        # Rysowanie linii siatki
        for i in range(size + 1):
            canvas.create_line(i * self.cell_size + offset, offset, i * self.cell_size + offset, size * self.cell_size + offset, fill="gray")
            canvas.create_line(offset, i * self.cell_size + offset, size * self.cell_size + offset, i * self.cell_size + offset, fill="gray")

        # Rysowanie etykiet (A, B, C... i 1, 2, 3...)
        for i in range(size):
            # Litery (kolumny) - nad planszą
            canvas.create_text((i * self.cell_size) + offset + self.cell_size / 2, offset / 2, text=chr(65 + i), font=("Arial", 10, "bold"), fill="black")
            # Cyfry (rzędy) - po lewej stronie planszy
            canvas.create_text(offset / 2, (i * self.cell_size) + offset + self.cell_size / 2, text=str(i + 1), font=("Arial", 10, "bold"), fill="black")
        
        # Ustawienie scrollregion, aby etykiety były widoczne i nie było zbędnych pasków przewijania
        canvas.config(scrollregion=(0, 0, size * self.cell_size + offset, size * self.cell_size + offset))

        if is_player_board:
            # Rysowanie rozmieszczonych statków gracza
            for ship_data in self.placed_ships:
                for r, c in ship_data['coords']:
                    x1, y1 = c * self.cell_size + offset, r * self.cell_size + offset
                    if ship_data['orientation'] == "horizontal":
                        canvas.create_image(x1, y1, anchor="nw", image=self.all_assets['ship_part_horizontal'], tags=ship_data['id'])
                    else:
                        canvas.create_image(x1, y1, anchor="nw", image=self.all_assets['ship_part_vertical'], tags=ship_data['id'])
            
            # Rysowanie strzałów przeciwnika (na planszy gracza)
            for r, c in self.enemy_shots:
                x, y = c * self.cell_size + offset + self.cell_size // 2, r * self.cell_size + offset + self.cell_size // 2
                
                # Sprawdź, czy to pole jest częścią jakiegoś statku gracza
                is_hit_on_my_ship = False
                for ship in self.placed_ships:
                    if (r, c) in ship['coords']:
                        is_hit_on_my_ship = True
                        break

                if is_hit_on_my_ship:
                     canvas.create_image(x, y, image=self.all_assets['explosion'], tags="explosion")
                else:
                    canvas.create_image(x, y, image=self.all_assets['water_splash'], tags="water_splash")

        else: # Plansza przeciwnika
            # Rysowanie moich strzałów na planszy przeciwnika
            for r, c in self.my_shots:
                x, y = c * self.cell_size + offset + self.cell_size // 2, r * self.cell_size + offset + self.cell_size // 2
                if (r, c) in self.enemy_hit_coords: # Jeśli serwer potwierdził trafienie
                    canvas.create_image(x, y, image=self.all_assets['hit_mark'], tags="hit_mark")
                else: # Jeśli serwer potwierdził pudło
                    canvas.create_image(x, y, image=self.all_assets['miss_mark'], tags="miss_mark")
            
            # Bindowanie zdarzeń myszy do planszy przeciwnika (strzały)
            if self.game_started and self.my_turn:
                canvas.bind("<ButtonPress-1>", self.on_enemy_board_click)
            else:
                canvas.unbind("<ButtonPress-1>")

        canvas.lower("all") # Upewnij się, że siatka jest na wierzchu, a obrazki pod spodem
        canvas.update_idletasks() # Wymuś odświeżenie

    def on_ship_drag_start(self, event):
        # Znajdź statek, który został kliknięty
        for ship_label in self.ship_labels:
            if ship_label == event.widget:
                self.dragging_ship = ship_label
                self.drag_start_x = event.x_root
                self.drag_start_y = event.y_root
                
                # Oblicz offset od lewego górnego rogu etykiety statku do punktu kliknięcia
                self.drag_offset_x = event.x
                self.drag_offset_y = event.y
                
                # Jeśli statek był już na planszy, usuń jego obraz z canvasa
                if self.dragging_ship.ship_id in [s['id'] for s in self.placed_ships]:
                    self.player_canvas.delete(self.dragging_ship.ship_id)
                
                # Ukryj oryginalną etykietę statku z bocznego panelu (tymczasowo)
                self.dragging_ship.master.pack_forget() # Ukryj ramkę zawierającą label

                # Utwórz tymczasowy obiekt na canvasie, reprezentujący przeciągany statek
                image_to_use = self.all_assets['ship_part_horizontal'] if self.dragging_ship.ship_orientation == "horizontal" else self.all_assets['ship_part_vertical']
                
                # Początkowa pozycja tymczasowego obrazu na canvasie (dopasowana do kursora)
                initial_x = event.x_root - self.player_canvas.winfo_rootx() - self.drag_offset_x
                initial_y = event.y_root - self.player_canvas.winfo_rooty() - self.drag_offset_y

                self.drag_image_id = self.player_canvas.create_image(initial_x, initial_y,
                                                                      anchor="nw", image=image_to_use, tags="dragging_ship")
                self.player_canvas.lift(self.drag_image_id) # Upewnij się, że jest na wierzchu
                break

    def on_ship_drag(self, event):
        if self.dragging_ship and self.drag_image_id:
            # Oblicz nową pozycję tymczasowego obrazu
            # Korekta o offset planszy (etykiety A-J, 1-10)
            offset = self.cell_size
            new_x = event.x_root - self.player_canvas.winfo_rootx() - self.drag_offset_x
            new_y = event.y_root - self.player_canvas.winfo_rooty() - self.drag_offset_y
            self.player_canvas.coords(self.drag_image_id, new_x, new_y)

    def on_ship_drag_end(self, event):
        if self.dragging_ship and self.drag_image_id:
            self.player_canvas.delete(self.drag_image_id) # Usuń tymczasowy obraz
            self.drag_image_id = None
            
            # Oblicz pozycję komórki, na której upuszczono statek
            # Użyj current mouse position relative to canvas root
            canvas_x = event.x_root - self.player_canvas.winfo_rootx()
            canvas_y = event.y_root - self.player_canvas.winfo_rooty()

            # Oblicz górny lewy róg statku, biorąc pod uwagę offset kliknięcia
            ship_top_left_x = canvas_x - self.drag_offset_x
            ship_top_left_y = canvas_y - self.drag_offset_y

            # Skoryguj o offset planszy (etykiety A-J, 1-10)
            row = int(round((ship_top_left_y - self.cell_size) / self.cell_size))
            col = int(round((ship_top_left_x - self.cell_size) / self.cell_size))

            potential_coords = self.get_ship_coordinates(row, col, self.dragging_ship.ship_length, self.dragging_ship.ship_orientation)
            
            # Walidacja pozycji
            if potential_coords is None: # Statek poza planszą po upuszczeniu
                messagebox.showwarning("Błąd rozmieszczenia", "Statek nie mieści się na planszy w tej pozycji i orientacji!")
                self.reset_dragged_ship()
                return

            # Sprawdź, czy statek koliduje z innymi statkami lub sąsiaduje zbyt blisko
            if self.check_ship_collision(potential_coords, self.dragging_ship.ship_id):
                messagebox.showwarning("Błąd rozmieszczenia", "Statki nie mogą na siebie nachodzić lub być zbyt blisko!")
                self.reset_dragged_ship()
                return
            
            # Usuń stary statek z listy self.placed_ships jeśli był już rozmieszczony
            self.placed_ships = [s for s in self.placed_ships if s['id'] != self.dragging_ship.ship_id]
            
            # Dodaj nowy statek do listy rozmieszczonych statków
            self.placed_ships.append({
                'id': self.dragging_ship.ship_id,
                'length': self.dragging_ship.ship_length,
                'orientation': self.dragging_ship.ship_orientation,
                'coords': potential_coords
            })
            self.dragging_ship.ship_coords_on_grid = potential_coords

            self.draw_grid(self.player_canvas, self.board_size, is_player_board=True)
            self.update_ship_placement_ui()
            self.dragging_ship = None

    def reset_dragged_ship(self):
        # Przywróć etykietę statku do panelu bocznego
        if self.dragging_ship:
            self.dragging_ship.master.pack(pady=5) # Przywróć ramkę, która zawiera label
            self.dragging_ship.ship_coords_on_grid = [] # Resetuj koordynaty na siatce
            # Usuń statek z placed_ships, jeśli tam był (na wypadek, gdyby był przeciągany z planszy i upuszczony niepoprawnie)
            self.placed_ships = [s for s in self.placed_ships if s['id'] != self.dragging_ship.ship_id]
            self.dragging_ship = None
        
        self.draw_grid(self.player_canvas, self.board_size, is_player_board=True)
        self.update_ship_placement_ui()


    def on_ship_right_click(self, event):
        clicked_label = event.widget
        if hasattr(clicked_label, 'ship_orientation'):
            current_orientation = clicked_label.ship_orientation
            new_orientation = "vertical" if current_orientation == "horizontal" else "horizontal"
            
            # Zmień orientację labela
            clicked_label.ship_orientation = new_orientation

            # Zmień obrazek etykiety w panelu bocznym
            if new_orientation == "horizontal":
                clicked_label.config(image=self.all_assets['ship_part_horizontal'])
            else:
                clicked_label.config(image=self.all_assets['ship_part_vertical'])
            # Ważne: zaktualizuj referencję do obrazu
            clicked_label.image = self.all_assets['ship_part_horizontal'] if new_orientation == "horizontal" else self.all_assets['ship_part_vertical']

            # Jeśli statek jest już na planszy, spróbuj go obrócić na planszy
            # Sprawdzamy czy statek ma przypisane koordynaty z planszy
            if clicked_label.ship_coords_on_grid: 
                # Zapamiętaj stare koordynaty i orientację na wypadek niepowodzenia
                old_coords = clicked_label.ship_coords_on_grid[:]
                old_orientation = current_orientation

                # Pobierz początkową komórkę statku na planszy
                start_row, start_col = clicked_label.ship_coords_on_grid[0]
                potential_coords = self.get_ship_coordinates(start_row, start_col, clicked_label.ship_length, new_orientation)

                # Sprawdź, czy obrót jest możliwy (nie wychodzi poza planszę i nie koliduje)
                if potential_coords is None or self.check_ship_collision(potential_coords, clicked_label.ship_id):
                    messagebox.showwarning("Błąd obrotu", "Statek nie może zostać obrócony w tej pozycji (kolizja lub poza planszą)!")
                    
                    # Przywróć poprzednią orientację i koordynaty
                    clicked_label.ship_orientation = old_orientation
                    if old_orientation == "horizontal":
                        clicked_label.config(image=self.all_assets['ship_part_horizontal'])
                    else:
                        clicked_label.config(image=self.all_assets['ship_part_vertical'])
                    clicked_label.image = self.all_assets['ship_part_horizontal'] if old_orientation == "horizontal" else self.all_assets['ship_part_vertical']
                    
                    # Znajdź statek w self.placed_ships i przywróć jego stare dane
                    for ship_data in self.placed_ships:
                        if ship_data['id'] == clicked_label.ship_id:
                            ship_data['orientation'] = old_orientation
                            ship_data['coords'] = old_coords
                            break
                    clicked_label.ship_coords_on_grid = old_coords # Upewnij się, że ten atrybut jest też zaktualizowany
                    
                else:
                    # Usuń stary obraz statku z planszy
                    self.player_canvas.delete(clicked_label.ship_id)

                    # Zaktualizuj dane statku w self.placed_ships
                    for ship_data in self.placed_ships:
                        if ship_data['id'] == clicked_label.ship_id:
                            ship_data['orientation'] = new_orientation
                            ship_data['coords'] = potential_coords
                            break
                    clicked_label.ship_coords_on_grid = potential_coords
                
                # Niezależnie od sukcesu obrotu, przerysuj planszę, aby odzwierciedlić stan
                self.draw_grid(self.player_canvas, self.board_size, is_player_board=True)


    def get_ship_coordinates(self, start_row, start_col, length, orientation):
        coords = []
        # Sprawdź, czy początkowe koordynaty są w granicach planszy
        if not (0 <= start_row < self.board_size and 0 <= start_col < self.board_size):
            return None

        if orientation == "horizontal":
            if start_col + length > self.board_size:
                return None
            for i in range(length):
                coords.append((start_row, start_col + i))
        else: # vertical
            if start_row + length > self.board_size:
                return None
            for i in range(length):
                coords.append((start_row + i, start_col))
        return coords

    def check_ship_collision(self, new_ship_coords, ship_id_to_exclude=None):
        for existing_ship_data in self.placed_ships:
            # Pomiń sprawdzanie kolizji z samym sobą podczas przeciągania
            if ship_id_to_exclude and existing_ship_data['id'] == ship_id_to_exclude:
                continue

            for new_r, new_c in new_ship_coords:
                # Sprawdź również sąsiednie pola (promień 1)
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        check_r, check_c = new_r + dr, new_c + dc
                        if (check_r, check_c) in existing_ship_data['coords']:
                            return True
        return False
    
    def update_ship_placement_ui(self):
        # Zaktualizuj widoczność etykiet statków do rozmieszczenia
        placed_ship_ids = {s['id'] for s in self.placed_ships}
        
        # Upewnij się, że wszystkie ramki statków są spakowane przed ponownym pakowaniem
        for label in self.ship_labels:
            label.master.pack_forget()

        # Spakuj tylko te statki, które NIE są jeszcze na planszy
        for label in self.ship_labels:
            if label.ship_id not in placed_ship_ids:
                label.master.pack(pady=5) # Spakuj ramkę, która zawiera label

        # Włącz/wyłącz przycisk "Zatwierdź rozmieszczenie"
        if len(self.placed_ships) == len(self.ship_lengths):
            self.place_ships_button.config(state="normal")
        else:
            self.place_ships_button.config(state="disabled")

    def send_ships_to_server(self):
        if len(self.placed_ships) != len(self.ship_lengths):
            messagebox.showwarning("Błąd", "Musisz rozmieścić wszystkie statki!")
            return

        # Przekształć listę obiektów statków na format do wysłania
        ships_to_send = []
        for ship_data in self.placed_ships:
            ships_to_send.append({
                'coords': ship_data['coords'],
                'length': ship_data['length'],
                'orientation': ship_data['orientation']
            })

        message = {"type": "SHIPS_PLACED", "ships": ships_to_send}
        self.send_message(message)
        self.player_board_frame.config(text="Twoja Plansza (Oczekiwanie na przeciwnika)")
        self.place_ships_button.config(state="disabled")
        # Usuń bindowania zdarzeń myszy, aby zablokować dalsze przesuwanie statków
        for label in self.ship_labels:
            label.unbind("<ButtonPress-1>")
            label.unbind("<B1-Motion>")
            label.unbind("<ButtonRelease-1>")
            label.unbind("<ButtonPress-3>")


    def create_game_boards(self):
        self.clear_window()
        self.root.geometry(self.window_sizes[self.difficulty])

        self.game_frame = tk.Frame(self.root)
        self.game_frame.pack(expand=True, fill="both", padx=10, pady=10)

        # Plansza gracza
        self.player_board_frame = tk.LabelFrame(self.game_frame, text="Twoja Plansza", padx=5, pady=5)
        self.player_board_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        canvas_width = self.board_size * self.cell_size + self.cell_size
        canvas_height = self.board_size * self.cell_size + self.cell_size

        self.player_canvas = tk.Canvas(self.player_board_frame, bg="lightblue",
                                      width=canvas_width, height=canvas_height)
        self.player_canvas.pack()
        self.draw_grid(self.player_canvas, self.board_size, is_player_board=True)

        # Plansza przeciwnika
        self.enemy_board_frame = tk.LabelFrame(self.game_frame, text="Plansza Przeciwnika", padx=5, pady=5)
        self.enemy_board_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        self.enemy_canvas = tk.Canvas(self.enemy_board_frame, bg="lightblue",
                                     width=canvas_width, height=canvas_height)
        self.enemy_canvas.pack()
        self.draw_grid(self.enemy_canvas, self.board_size, is_player_board=False) # Początkowo pusta

        # Etykieta tury
        self.turn_label = tk.Label(self.game_frame, text="", font=("Arial", 14))
        self.turn_label.grid(row=1, column=0, columnspan=2, pady=10)

        # Upewnij się, że kolumny i wiersze rozciągają się poprawnie
        self.game_frame.grid_columnconfigure(0, weight=1)
        self.game_frame.grid_columnconfigure(1, weight=1)
        self.game_frame.grid_rowconfigure(0, weight=1)

    def on_enemy_board_click(self, event):
        if not self.my_turn:
            messagebox.showwarning("Czekaj", "Nie Twoja kolej!")
            return

        # Skoryguj koordynaty kliknięcia o offset planszy
        col = (event.x - self.cell_size) // self.cell_size
        row = (event.y - self.cell_size) // self.cell_size

        if not (0 <= row < self.board_size and 0 <= col < self.board_size):
            messagebox.showwarning("Błąd", "Kliknięto poza planszą!")
            return # Kliknięto poza planszą

        shot_coord = (row, col)
        if shot_coord in self.my_shots:
            messagebox.showwarning("Błąd", "Już strzelałeś w to pole!")
            return

        self.my_shots.add(shot_coord) # Dodaj do moich strzałów (tymczasowo)
        message = {"type": "SHOT", "coords": [row, col]}
        self.send_message(message)
        # my_turn = False # Serwer zdecyduje, czy tura przechodzi, czy nie

    def update_game_state(self, my_board_state, enemy_board_state, my_turn, enemy_shots, my_shots_confirmed_hits):
        self.my_turn = my_turn
        self.enemy_shots = set(tuple(e) for e in enemy_shots) # Aktualizuj strzały przeciwnika (potrzebne do rysowania na mojej planszy)
        self.enemy_hit_coords = set(tuple(e) for e in my_shots_confirmed_hits) # To są moje trafienia potwierdzone przez serwer

        # Zaktualizuj etykietę tury
        if self.my_turn:
            self.turn_label.config(text="Twoja kolej!", fg="green")
        else:
            self.turn_label.config(text="Kolej przeciwnika...", fg="red")

        # Rysuj moją planszę z trafieniami przeciwnika
        self.draw_grid(self.player_canvas, self.board_size, is_player_board=True)

        # Rysuj planszę przeciwnika z moimi strzałami (trafienia i pudła)
        self.draw_grid(self.enemy_canvas, self.board_size, is_player_board=False)


    def receive_messages(self):
        buffer = ""
        while self.connected:
            try:
                data = self.client_socket.recv(4096).decode()
                if not data:
                    print("[Client] Serwer zamknął połączenie.")
                    self.root.after(0, self.handle_disconnection)
                    break
                
                buffer += data
                while "\n" in buffer:
                    message, buffer = buffer.split("\n", 1)
                    if not message:
                        continue
                    print(f"[Client] Otrzymano: {message}")
                    self.process_server_message(message)

            except (ConnectionResetError, BrokenPipeError) as e:
                print(f"[Client] Utracono połączenie z serwerem: {e}")
                self.root.after(0, self.handle_disconnection)
                break
            except json.JSONDecodeError as e:
                print(f"[Client] Błąd dekodowania JSON: {e} w wiadomości: {buffer}")
                # W przypadku błędu JSON, spróbuj opróżnić bufor, aby nie blokował dalszego przetwarzania
                buffer = "" 
            except Exception as e:
                print(f"[Client] Nieoczekiwany błąd w receive_messages: {e}")
                self.root.after(0, self.handle_disconnection)
                break

    def process_server_message(self, message):
        if message.startswith("START_SETUP:"):
            try:
                _, board_size_str, ships_str = message.split(":", 2)
                self.board_size = int(board_size_str)
                self.ship_lengths = sorted(json.loads(ships_str), reverse=True)
                print(f"[Client] Otrzymano START_SETUP: {self.board_size}, {self.ship_lengths}")
                self.root.after(0, self.create_setup_screen)
            except ValueError as e:
                print(f"[Client] Błąd parsowania START_SETUP: {e} - wiadomość: {message}")
            except json.JSONDecodeError as e:
                print(f"[Client] Błąd JSON w START_SETUP: {e} - wiadomość: {message}")


        elif message.startswith("GAME_START:"):
            _, my_turn_str = message.split(":")
            self.game_started = True
            self.my_turn = (my_turn_str == "True")
            self.my_shots = set() # Reset my shots for a new game
            self.enemy_shots = set() # Reset enemy shots for a new game
            self.enemy_hit_coords = set() # Reset my confirmed hits on enemy
            self.root.after(0, self.create_game_boards)
            # Daj czas na utworzenie canvasów, zanim zaczniemy rysować
            self.root.after(100, lambda: self.update_game_state([], [], self.my_turn, [], [])) 

        elif message.startswith("UPDATE_BOARD:"):
            try:
                parts = message.split(":", 1)
                if len(parts) < 2:
                    print(f"Błąd parsowania UPDATE_BOARD: {message}")
                    return
                
                data_json = parts[1]
                game_state = json.loads(data_json)
                
                my_board_hits = game_state.get('my_board_hits', []) # Nie używamy już tego do rysowania statków gracza
                enemy_board_hits = game_state.get('enemy_board_hits', []) # To są moje trafienia na przeciwniku
                my_turn = game_state.get('my_turn', False)
                enemy_shots = game_state.get('enemy_shots', []) # Nowe: faktyczne strzały przeciwnika na mojej planszy
                
                self.root.after(0, lambda: self.update_game_state(my_board_hits, enemy_board_hits, my_turn, enemy_shots, enemy_board_hits))
            except json.JSONDecodeError as e:
                print(f"[Client] Błąd JSON w UPDATE_BOARD: {e} dla wiadomości: {message}")
            except Exception as e:
                print(f"[Client] Nieoczekiwany błąd w process_server_message (UPDATE_BOARD): {e}")

        elif message.startswith("GAME_OVER:"):
            _, result, scores_json = message.split(":", 2)
            scores = json.loads(scores_json)
            self.root.after(0, lambda: self.handle_game_over(result, scores))

        elif message.startswith("DISCONNECT:"):
            self.root.after(0, self.handle_disconnection)
        
        elif message.startswith("WAITING_FOR_OPPONENT:"):
            print("[Client] Oczekiwanie na drugiego gracza...")
            # Możesz tu zaktualizować jakiś komunikat na ekranie klienta
            self.root.after(0, self.create_waiting_screen)


        elif message.startswith("ERROR:"):
            error_msg = message[len("ERROR:"):]
            messagebox.showerror("Błąd Serwera", error_msg)

        else:
            print(f"[Client] Nieznana wiadomość od serwera: {message}")

    def send_message(self, message):
        if self.connected and self.client_socket:
            try:
                self.client_socket.sendall((json.dumps(message) + "\n").encode())
            except (ConnectionResetError, BrokenPipeError) as e:
                print(f"[Client] Błąd wysyłania wiadomości: {e}")
                self.root.after(0, self.handle_disconnection)
            except Exception as e:
                print(f"[Client] Nieoczekiwany błąd podczas wysyłania: {e}")
                self.root.after(0, self.handle_disconnection)

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def reset_game_state(self):
        """Resetuje wszystkie zmienne stanu gry do wartości początkowych dla nowej rozgrywki."""
        self.my_turn = False
        self.game_started = False
        self.enemy_shots = set()
        self.my_shots = set()
        self.placed_ships = [] # Wyczyść rozmieszczone statki
        self.ship_labels = [] # Wyczyść listę referencji do etykiet statków (będą tworzone na nowo)
        self.enemy_hit_coords = set()
        # self.difficulty = None # Trudność zostaje odczytana z wyboru gracza na nowo
        # self.board_size = 0 # Serwer ponownie wyśle rozmiar planszy
        # self.ship_lengths = [] # Serwer ponownie wyśle konfigurację statków

        # Po prostu wracamy do ekranu startowego/połączeniowego, aby gracz mógł ponownie wybrać nazwę i trudność
        # (lub po prostu połączyć się, jeśli serwer czeka)
        self.root.after(0, self.create_start_screen)


    def handle_game_over(self, result, scores):
        self.game_started = False
        self.scores = scores
        
        if result == "WIN":
            messagebox.showinfo("Koniec gry", "Gratulacje! Wygrałeś!")
        elif result == "LOSE":
            messagebox.showinfo("Koniec gry", "Niestety, przegrałeś.")
        elif result == "WIN_DISCONNECT":
            messagebox.showinfo("Koniec gry", "Przeciwnik się rozłączył! Wygrałeś!")
        
        self.create_scoreboard(scores)

    def handle_disconnection(self):
        if not self.connected: # Już obsłużono
            return
        self.connected = False
        if self.client_socket:
            try:
                self.client_socket.shutdown(socket.SHUT_RDWR)
                self.client_socket.close()
            except OSError as e:
                print(f"[Client] Błąd zamykania gniazda: {e}")
            except Exception as e:
                print(f"[Client] Nieoczekiwany błąd podczas zamykania gniazda: {e}")

        # Jeśli okno nie zostało jeszcze zniszczone, wyświetl błąd
        if self.root.winfo_exists():
            messagebox.showerror("Błąd połączenia", "Utracono połączenie z serwerem. Gra zostanie zakończona.")
            self.root.destroy()
        else:
            print("[Client] Okno Tkinter już zamknięte. Nie można wyświetlić komunikatu.")


    def on_closing(self):
        if self.connected:
            try:
                # Wysyłamy informację o rozłączeniu, ale nie czekamy na odpowiedź
                # i od razu zamykamy, żeby uniknąć blokowania UI
                self.send_message({"type": "DISCONNECT"}) 
            except (ConnectionResetError, BrokenPipeError, AttributeError):
                pass # Serwer mógł się już zamknąć lub socket nie istnieje
            except Exception as e:
                print(f"Błąd podczas zamykania połączenia: {e}")
            finally:
                if self.client_socket:
                    try:
                        self.client_socket.shutdown(socket.SHUT_RDWR)
                        self.client_socket.close()
                    except OSError as e:
                        print(f"[Client] Błąd zamykania gniazda (on_closing): {e}")

        self.root.destroy()

    def create_scoreboard(self, scores):
        self.clear_window()
        self.root.geometry("600x400")
        self.scoreboard_label = tk.Label(self.root, text="Tablica wyników", font=("Arial", 18))
        self.scoreboard_label.pack(pady=10)

        # Utwórz drzewo (Treeview)
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(pady=10, padx=10, fill="both", expand=True)

        self.scoreboard_tree = ttk.Treeview(tree_frame, columns=("Winner", "Loser", "Date", "Difficulty"), show="headings")
        self.scoreboard_tree.heading("Winner", text="Zwycięzca")
        self.scoreboard_tree.heading("Loser", text="Przegrany")
        self.scoreboard_tree.heading("Date", text="Data")
        self.scoreboard_tree.heading("Difficulty", text="Poziom")

        self.scoreboard_tree.column("Winner", width=150, anchor="center")
        self.scoreboard_tree.column("Loser", width=150, anchor="center")
        self.scoreboard_tree.column("Date", width=150, anchor="center")
        self.scoreboard_tree.column("Difficulty", width=100, anchor="center")
        
        # Dodaj pasek przewijania
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.scoreboard_tree.yview)
        vsb.pack(side='right', fill='y')
        self.scoreboard_tree.configure(yscrollcommand=vsb.set)

        self.scoreboard_tree.pack(fill="both", expand=True)

        for score in scores:
            self.scoreboard_tree.insert("", "end", values=(score['winner'], score['loser'], score['date'], score['difficulty']))

        self.play_again_button = tk.Button(self.root, text="Zagraj ponownie", command=self.reset_game_state)
        self.play_again_button.pack(pady=10)

        self.exit_button = tk.Button(self.root, text="Wyjdź", command=self.root.destroy)
        self.exit_button.pack(pady=5)

if __name__ == "__main__":
    BattleshipClient()