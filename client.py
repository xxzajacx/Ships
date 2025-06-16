import socket
import threading
import json
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
import time
from PIL import Image, ImageTk # Upewnij się, że masz zainstalowane Pillow: pip install Pillow
import os

HOST = '127.0.0.1'

class BattleshipClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Statki - Gra Sieciowa")

        self.my_turn = False
        self.game_started = False
        self.enemy_shots = set()
        self.my_shots = set()
        self.difficulty = None
        self.board_size = 10
        self.ship_lengths = []
        self.placed_ships = [] # Statki rozmieszczone przez gracza na własnej planszy (lista list krotek koordynatów)
        self.ship_count = 0 # Całkowita liczba pól zajmowanych przez statki (dla walidacji)
        self.player_name = ""
        self.connected = False
        self.current_port = None

        self.window_sizes = {
            'easy': '700x800', # Zwiększone rozmiary dla lepszego UI
            'medium': '900x900',
            'hard': '1100x1100'
        }

        self.ship_configs = {
            'easy': {'board_size': 10, 'ships': [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]},
            'medium': {'board_size': 14, 'ships': [5, 4, 4, 3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1]},
            'hard': {'board_size': 20, 'ships': [6, 5, 5, 4, 4, 4, 3, 3, 3, 3, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1]}
        }

        # Zmienne dla drag and drop
        self.dragging_ship_length = None # Długość statku, który jest przeciągany
        self.dragging_ship_idx = -1 # Indeks statku w self.ship_labels, który jest przeciągany
        self.dragged_ship_label = None # Etykieta reprezentująca przeciągany statek (kopia)
        self.current_preview_cells = [] # Komórki pod podglądem statku
        self.current_drag_orientation = "horizontal" # "horizontal" or "vertical"
        self.last_mouse_pos_on_board = (None, None) # Ostatnia znana pozycja myszy na planszy

        # Ładowanie obrazków
        self.images = {}
        self.load_images()
        self.explosion_frames = []
        self.load_explosion_frames()

        self.create_connection_screen()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def load_images(self):
        """Ładuje wszystkie potrzebne obrazki do pamięci."""
        try:
            self.images['sea'] = ImageTk.PhotoImage(Image.open("assets/sea.png").resize((30, 30)))
            self.images['ship_part_horizontal'] = ImageTk.PhotoImage(Image.open("assets/ship_part_horizontal.png").resize((30, 30)))
            self.images['ship_part_vertical'] = ImageTk.PhotoImage(Image.open("assets/ship_part_vertical.png").resize((30, 30)))
            self.images['hit'] = ImageTk.PhotoImage(Image.open("assets/hit.png").resize((30, 30)))
            self.images['miss'] = ImageTk.PhotoImage(Image.open("assets/miss.png").resize((30, 30)))
            
            # Obrazki dla palety statków (możesz użyć jednego segmentu lub stworzyć dla każdej długości)
            self.images['palette_ship_part'] = ImageTk.PhotoImage(Image.open("assets/ship_part_horizontal.png").resize((25, 25)))
        
        except FileNotFoundError as e:
            messagebox.showerror("Błąd Ładowania Obrazów", f"Nie znaleziono pliku obrazu: {e}\nUpewnij się, że pliki .png są w folderze 'assets'.")
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nieoczekiwany błąd podczas ładowania obrazów: {e}")
            self.root.destroy()

    def load_explosion_frames(self):
        """Ładuje ramki animacji wybuchu."""
        self.explosion_frames = []
        # Upewnij się, że masz co najmniej jedną ramkę, aby animacja się nie zawiesiła
        # Nawet jeśli będzie tylko jedna, to jest to bezpieczniejsze niż brak
        for i in range(1, 10): # Załóżmy 9 ramek animacji wybuchu (explosion_frame_01.png do explosion_frame_09.png)
            try:
                frame_path = f"assets/explosion_frame_{i:02d}.png"
                img = Image.open(frame_path).resize((30, 30))
                self.explosion_frames.append(ImageTk.PhotoImage(img))
            except FileNotFoundError:
                # print(f"Brak ramki wybuchu: {frame_path}") # Debug
                break # Przestań szukać, jeśli brakuje kolejnej ramki
        if not self.explosion_frames:
            print("Błąd: Nie załadowano żadnych ramek wybuchu. Animacja nie będzie działać.")
            # Można tu załadować jakiś domyślny obraz 'hit' jako fallback
            # self.explosion_frames.append(self.images['hit'])

    def connect_to_server(self):
        """Próbuje połączyć się z serwerem na dostępnych portach."""
        ports_to_try = [12345, 12346, 12347]
        connected_successfully = False
        
        for port in ports_to_try:
            try:
                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client.connect((HOST, port))
                self.connected = True
                self.player_name = self.name_entry.get().strip()
                self.current_port = port # Zapisz używany port
                
                self.receive_thread = threading.Thread(target=self.receive_messages)
                self.receive_thread.daemon = True
                self.receive_thread.start()
                
                self.client.sendall(f"SET_NAME:{self.player_name}\n".encode())
                self.create_welcome_screen()
                connected_successfully = True
                break
                
            except Exception as e:
                print(f"Nie można połączyć z portem {port}: {e}")
                self.connection_status.config(text=f"Próba połączenia z portem {port} nieudana...", fg="orange")
                time.sleep(0.5)
        
        if not connected_successfully:
            messagebox.showerror("Błąd połączenia", "Nie można połączyć z serwerem na żadnym z dostępnych portów.")
            self.connection_status.config(text="Nie można połączyć z serwerem", fg="red")

    def clear_window(self):
        """Usuwa wszystkie widżety z okna."""
        for widget in self.root.winfo_children():
            widget.destroy()

    def create_connection_screen(self):
        """Tworzy ekran połączenia z serwerem."""
        self.clear_window()
        self.root.geometry("400x300")
        
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, padx=20, pady=20)
        
        tk.Label(main_frame, text="Połączenie z serwerem", font=("Arial", 16, "bold")).pack(pady=10)
        
        name_frame = tk.Frame(main_frame)
        name_frame.pack(pady=10)
        
        tk.Label(name_frame, text="Podaj nazwę gracza:", font=("Arial", 12)).pack()
        self.name_entry = tk.Entry(name_frame, font=("Arial", 12))
        self.name_entry.pack()
        
        self.connect_button = tk.Button(
            main_frame, 
            text="Połącz", 
            font=("Arial", 12), 
            command=self.connect_to_server
        )
        self.connect_button.pack(pady=20)
        
        self.connection_status = tk.Label(main_frame, text="", font=("Arial", 10))
        self.connection_status.pack()

    def create_welcome_screen(self):
        """Tworzy ekran powitalny i wyboru trudności."""
        self.clear_window()
        self.root.geometry("500x400")
        
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, padx=20, pady=20)
        
        tk.Label(main_frame, text="Statki - Gra Sieciowa", font=("Arial", 18, "bold")).pack(pady=20)
        
        difficulty_frame = tk.Frame(main_frame)
        difficulty_frame.pack(pady=10)
        
        tk.Label(difficulty_frame, text="Wybierz poziom trudności:", font=("Arial", 14)).pack()
        
        self.difficulty_var = tk.StringVar(value="easy")
        difficulties = [
            ("Łatwy (10x10, 10 statków)", "easy"),
            ("Średni (14x14, 14 statków)", "medium"),
            ("Trudny (20x20, 20 statków)", "hard")
        ]
        
        for text, mode in difficulties:
            rb = tk.Radiobutton(
                difficulty_frame, 
                text=text, 
                variable=self.difficulty_var,
                value=mode, 
                font=("Arial", 12),
                width=25,
                anchor="w"
            )
            rb.pack(anchor=tk.W)
        
        self.start_button = tk.Button(
            main_frame, 
            text="Rozpocznij grę", 
            font=("Arial", 14), 
            command=self.start_game, 
            width=20
        )
        self.start_button.pack(pady=20)

    def start_game(self):
        """Inicjuje grę po wybraniu trudności."""
        selected_difficulty = self.difficulty_var.get()
        if selected_difficulty in self.ship_configs:
            self.difficulty = selected_difficulty
            self.board_size = self.ship_configs[self.difficulty]['board_size']
            self.ship_lengths = sorted(self.ship_configs[self.difficulty]['ships'], reverse=True) # Sortowanie ułatwi wyświetlanie palety
            self.ship_count = sum(self.ship_configs[self.difficulty]['ships']) # Całkowita liczba pól dla walidacji
            self.placed_ships = [] # Resetuj listę rozmieszczonych statków
            self.ship_labels = [] # Resetuj etykiety statków dla palety
        try:
            self.client.sendall(f"SET_DIFFICULTY:{self.difficulty}\n".encode())
        except (ConnectionResetError, BrokenPipeError):
            self.handle_disconnection()

    def create_setup_screen(self):
        """Tworzy ekran rozmieszczania statków z funkcją drag & drop."""
        self.clear_window()
        self.root.geometry(self.window_sizes.get(self.difficulty, '700x800'))
        
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, padx=20, pady=20)
        
        tk.Label(
            main_frame, 
            text="Rozmieść swoje statki na planszy", 
            font=("Arial", 16, "bold")
        ).pack(pady=10)

        # Plansza gracza
        board_frame = tk.Frame(main_frame, bd=2, relief="groove")
        board_frame.pack(pady=10)
        
        self.board_buttons = [] # Przyciski planszy, na które upuszczamy
        for i in range(self.board_size):
            row = []
            for j in range(self.board_size):
                btn = tk.Button(
                    board_frame, 
                    image=self.images['sea'], # Obrazek morza
                    width=30, 
                    height=30, 
                    bd=1, 
                    relief="solid",
                    bg="SystemButtonFace" # Domyślny kolor tła
                )
                btn.grid(row=i, column=j, padx=0, pady=0)
                # Bindowanie zdarzeń myszy do każdego pola planszy dla drag & drop
                btn.bind("<Motion>", lambda event, r=i, c=j: self.on_board_motion(event, r, c))
                btn.bind("<ButtonRelease-1>", lambda event, r=i, c=j: self.on_drag_release(event, r, c))
                btn.bind("<Button-3>", lambda event: self.rotate_dragged_ship()) # Prawy przycisk myszy dla rotacji

                row.append(btn)
            self.board_buttons.append(row)

        self.status_label = tk.Label(
            main_frame, 
            text="Przeciągnij statki na planszę. Kliknij prawym przyciskiem myszy, aby obrócić.", 
            font=("Arial", 12)
        )
        self.status_label.pack(pady=10)
        
        self.total_ships_label = tk.Label(
            main_frame,
            text=f"Statki do rozmieszczenia: {len(self.ship_lengths)}",
            font=("Arial", 12)
        )
        self.total_ships_label.pack()

        # --- Panel statków do rozmieszczenia (Drag Source) ---
        self.ships_palette_frame = tk.Frame(main_frame, bd=2, relief="sunken", padx=10, pady=10)
        self.ships_palette_frame.pack(pady=20)

        tk.Label(self.ships_palette_frame, text="Twoje statki:", font=("Arial", 12, "bold")).pack()
        
        self.ship_labels = [] # Lista słowników dla statków do przeciągania
        for i, length in enumerate(self.ship_lengths):
            ship_container = tk.Frame(self.ships_palette_frame, bd=1, relief="raised", padx=2, pady=2, bg="lightgray")
            ship_container.pack(pady=5, padx=5, fill=tk.X)
            
            segments_frame = tk.Frame(ship_container, bg="lightgray")
            segments_frame.pack(side=tk.LEFT, padx=5)

            ship_segments = []
            for _ in range(length):
                segment_label = tk.Label(segments_frame, image=self.images['palette_ship_part'], width=25, height=25, bg="lightgray")
                segment_label.pack(side=tk.LEFT, padx=1)
                ship_segments.append(segment_label)

            # Bindowanie zdarzeń do kontenera dla drag start
            ship_container.bind("<Button-1>", lambda event, idx=i, length=length: self.start_drag(event, idx, length))
            
            self.ship_labels.append({
                'container': ship_container, 
                'segments': ship_segments,
                'length': length, 
                'placed': False,
                'coords': None, # Pozycja statku po rozmieszczeniu
                'orientation': 'horizontal' # Domyślna orientacja
            })
        
        self.finish_placement_button = tk.Button(
            main_frame,
            text="Zakończ rozmieszczanie",
            font=("Arial", 14),
            command=self.send_ships,
            state=tk.DISABLED
        )
        self.finish_placement_button.pack(pady=10)
        self.check_all_ships_placed() # Sprawdź początkowy stan przycisku

    def start_drag(self, event, ship_index, length):
        """Rozpoczyna operację przeciągania statku."""
        if self.ship_labels[ship_index]['placed']:
            return # Nie można przeciągać już umieszczonych statków

        self.dragging_ship_length = length
        self.dragging_ship_idx = ship_index
        self.current_drag_orientation = self.ship_labels[ship_index]['orientation'] # Utrzymaj obecną orientację

        # Utwórz kopię wizualną przeciąganego statku jako Toplevel
        self.dragged_ship_label = tk.Toplevel(self.root, highlightbackground="black", highlightthickness=1)
        self.dragged_ship_label.overrideredirect(True) # Usuwa ramkę okna
        self.dragged_ship_label.attributes("-topmost", True) # Zawsze na wierzchu

        self.update_dragged_ship_display() # Narysuj statek w odpowiedniej orientacji
        
        # Oblicz offset, aby środek statku był pod kursorem
        self.drag_offset_x = event.x
        self.drag_offset_y = event.y

        # Przesuń dragged_ship_label, aby był pod kursorem
        self.root.bind("<B1-Motion>", self.on_drag_motion_global)
        self.root.bind("<ButtonRelease-1>", self.on_drag_release_global)

        self.ship_labels[ship_index]['container'].config(relief="sunken")

    def update_dragged_ship_display(self):
        """Aktualizuje wygląd przeciąganego statku (np. po rotacji)."""
        if not self.dragged_ship_label:
            return

        # Usuń stare segmenty
        for widget in list(self.dragged_ship_label.winfo_children()): # Użyj list() by uniknąć RuntimeError: dictionary changed size during iteration
            widget.destroy()
        
        # Dodaj nowe segmenty w zależności od orientacji
        for i in range(self.dragging_ship_length):
            img = self.images['ship_part_horizontal'] if self.current_drag_orientation == 'horizontal' else self.images['ship_part_vertical']
            seg_lbl = tk.Label(self.dragged_ship_label, image=img, width=30, height=30, bd=0)
            if self.current_drag_orientation == 'horizontal':
                seg_lbl.pack(side=tk.LEFT, padx=0, pady=0)
            else:
                seg_lbl.pack(side=tk.TOP, padx=0, pady=0)
        
        # Pamiętaj, aby po zmianie orientacji zaktualizować pozycję okna
        # Ponieważ rozmiar mógł się zmienić (np. z 30x90 na 90x30)
        self.dragged_ship_label.update_idletasks() # Odśwież widżety, aby uzyskać poprawny rozmiar
        
        # Upewnij się, że okno jest wyśrodkowane pod kursorem lub zachowuje swój offset
        if self.last_mouse_pos_on_board[0] is not None:
             # Użyj ostatniej pozycji myszy dla przesuwania okna
            x_root, y_root = self.root.winfo_pointerx(), self.root.winfo_pointery()
            self.dragged_ship_label.geometry(f"+{x_root - self.dragged_ship_label.winfo_width() // 2}+{y_root - self.dragged_ship_label.winfo_height() // 2}")


    def on_drag_motion_global(self, event):
        """Obsługuje ruch myszy podczas przeciągania statku (globalnie na całym oknie root)."""
        if self.dragging_ship_length is not None and self.dragged_ship_label:
            # Przesuń Toplevel za kursorem
            self.dragged_ship_label.geometry(f"+{event.x_root - self.dragged_ship_label.winfo_width() // 2}+{event.y_root - self.dragged_ship_label.winfo_height() // 2}")
            
            # Pobierz aktualną pozycję myszy względem root
            x_on_root = event.x
            y_on_root = event.y

            # Sprawdź, czy kursor jest nad planszą
            if hasattr(self, 'board_buttons') and self.board_buttons:
                first_btn = self.board_buttons[0][0]
                board_x_start = first_btn.winfo_x() + first_btn.winfo_toplevel().winfo_x() # Bez root_x, jeśli plansza w main_frame
                board_y_start = first_btn.winfo_y() + first_btn.winfo_toplevel().winfo_y()

                board_x_end = board_x_start + self.board_size * first_btn.winfo_width()
                board_y_end = board_y_start + self.board_size * first_btn.winfo_height()

                if board_x_start <= x_on_root <= board_x_end and \
                   board_y_start <= y_on_root <= board_y_end:
                    
                    # Oblicz, na której komórce planszy znajduje się kursor
                    cell_width = first_btn.winfo_width()
                    cell_height = first_btn.winfo_height()

                    row = (y_on_root - board_y_start) // cell_height
                    col = (x_on_root - board_x_start) // cell_width
                    
                    self.on_board_motion(event, row, col)
                    self.last_mouse_pos_on_board = (row, col) # Zapisz ostatnią pozycję na planszy
                else:
                    self.clear_preview_cells() # Wyczyść podgląd, jeśli mysz poza planszą
                    self.last_mouse_pos_on_board = (None, None)


    def on_board_motion(self, event, row, col):
        """Obsługuje ruch myszy nad planszą podczas przeciągania."""
        if self.dragging_ship_length is not None:
            
            # Oblicz początkowe koordynaty statku (górny lewy róg statku),
            # tak aby środek przeciąganego statku był mniej więcej na komórce (row, col)
            start_col = col
            start_row = row

            # Jeśli statek jest parzystej długości, nie będzie idealnie wyśrodkowany na jednej komórce
            # więc skorygujmy początkową pozycję, aby statek był wyśrodkowany pod kursorem
            half_length = self.dragging_ship_length // 2
            
            if self.current_drag_orientation == "horizontal":
                start_col = col - half_length
                # Jeśli długość parzysta, a kursor jest po lewej stronie środka, przesuń w lewo o 1
                if self.dragging_ship_length % 2 == 0 and (event.x % self.board_buttons[0][0].winfo_width()) < (self.board_buttons[0][0].winfo_width() // 2):
                     start_col -=1 
            else: # vertical
                start_row = row - half_length
                if self.dragging_ship_length % 2 == 0 and (event.y % self.board_buttons[0][0].winfo_height()) < (self.board_buttons[0][0].winfo_height() // 2):
                    start_row -=1

            proposed_cells = []
            for i in range(self.dragging_ship_length):
                if self.current_drag_orientation == "horizontal":
                    proposed_cells.append((start_row, start_col + i))
                else: # vertical
                    proposed_cells.append((start_row + i, start_col))
            
            self.preview_ship_placement(proposed_cells)

    def rotate_dragged_ship(self):
        """Zmienia orientację przeciąganego statku."""
        if self.dragging_ship_length is not None and self.dragged_ship_label:
            self.current_drag_orientation = "vertical" if self.current_drag_orientation == "horizontal" else "horizontal"
            self.update_dragged_ship_display() # Zaktualizuj wygląd Toplevel
            
            # Po rotacji odśwież podgląd na planszy
            if self.last_mouse_pos_on_board[0] is not None:
                self.on_board_motion(None, self.last_mouse_pos_on_board[0], self.last_mouse_pos_on_board[1])

    def on_drag_release_global(self, event):
        """Obsługuje zwolnienie przycisku myszy po przeciąganiu statku (globalnie)."""
        self.root.unbind("<B1-Motion>")
        self.root.unbind("<ButtonRelease-1>")

        if self.dragging_ship_length is not None:
            self.clear_preview_cells()
            if self.dragged_ship_label:
                self.dragged_ship_label.destroy()
                self.dragged_ship_label = None

            # Obliczanie komórki, na którą upuszczono statek
            # Konwertuj globalne koordynaty myszy na koordynaty względem planszy
            board_x_start = self.board_buttons[0][0].winfo_x() + self.board_buttons[0][0].winfo_toplevel().winfo_x()
            board_y_start = self.board_buttons[0][0].winfo_y() + self.board_buttons[0][0].winfo_toplevel().winfo_y()
            
            rel_x = event.x_root - board_x_start
            rel_y = event.y_root - board_y_start

            cell_width = self.board_buttons[0][0].winfo_width()
            cell_height = self.board_buttons[0][0].winfo_height()
            
            # Oblicz komórkę, na którą upuszczono (zaokrąglając do najbliższej komórki)
            # Używamy floor do bezpośredniego mapowania na komórki
            drop_col = int(rel_x / cell_width)
            drop_row = int(rel_y / cell_height)

            # Oblicz początkowe koordynaty statku (górny lewy róg statku)
            half_length = self.dragging_ship_length // 2
            
            start_col = drop_col
            start_row = drop_row

            if self.current_drag_orientation == "horizontal":
                start_col = drop_col - half_length
                # Jeśli długość parzysta, a kursor był po lewej stronie środka komórki drop_col
                if self.dragging_ship_length % 2 == 0 and (rel_x % cell_width) < (cell_width // 2):
                    start_col -= 1
            else: # vertical
                start_row = drop_row - half_length
                if self.dragging_ship_length % 2 == 0 and (rel_y % cell_height) < (cell_height // 2):
                    start_row -= 1

            # Spróbuj umieścić statek
            self.attempt_place_ship(start_row, start_col, self.dragging_ship_length, self.current_drag_orientation, self.dragging_ship_idx)
            
            self.dragging_ship_length = None
            self.dragging_ship_idx = -1
            self.current_drag_orientation = "horizontal" # Resetuj do domyślnej
            self.last_mouse_pos_on_board = (None, None)


    def preview_ship_placement(self, cells):
        """Podświetla komórki, na których potencjalnie zostanie umieszczony statek."""
        # Wyczyść poprzednie podświetlenia, ale tylko te, które były ustawione przez podgląd
        for r, c in self.current_preview_cells:
            if 0 <= r < self.board_size and 0 <= c < self.board_size:
                # Upewnij się, że nie zmieniasz koloru umieszczonych już statków
                is_placed_ship_cell = False
                for ship_coords in self.placed_ships:
                    if (r, c) in ship_coords:
                        is_placed_ship_cell = True
                        break
                if not is_placed_ship_cell:
                    self.board_buttons[r][c].config(bg="SystemButtonFace") # Resetuj kolor do domyślnego
        
        self.current_preview_cells = []
        valid_placement = True

        for r, c in cells:
            # 1. Walidacja granic planszy
            if not (0 <= r < self.board_size and 0 <= c < self.board_size):
                valid_placement = False
                break
            # 2. Walidacja kolizji z istniejącymi statkami
            for existing_ship_coords in self.placed_ships:
                if (r, c) in existing_ship_coords:
                    valid_placement = False
                    break
            if not valid_placement:
                break
            
            # 3. Walidacja stykających się statków (strefa ochronna 1px wokół)
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0:
                        continue # Pomiń bieżące pole
                    neighbor_r, neighbor_c = r + dr, c + dc
                    # Sprawdź tylko istniejące statki, nie dotykaj pól, które są częścią podglądu
                    for existing_ship_coords in self.placed_ships:
                        if (neighbor_r, neighbor_c) in existing_ship_coords and (neighbor_r, neighbor_c) not in cells: # Nie liczy się styk z samym sobą w podglądzie
                            valid_placement = False
                            break
                    if not valid_placement: break
                if not valid_placement: break
            
        color = "lightgreen" if valid_placement else "salmon" # Kolor podglądu
        for r, c in cells:
            # Upewnij się, że malujesz tylko komórki w granicach planszy
            if 0 <= r < self.board_size and 0 <= c < self.board_size:
                self.board_buttons[r][c].config(bg=color)
                self.current_preview_cells.append((r, c))
        return valid_placement

    def clear_preview_cells(self):
        """Czyści podświetlone komórki podglądu statku."""
        for r, c in self.current_preview_cells:
            if 0 <= r < self.board_size and 0 <= c < self.board_size:
                # Upewnij się, że nie zmieniasz koloru umieszczonych już statków
                is_placed_ship_cell = False
                for ship_coords in self.placed_ships:
                    if (r, c) in ship_coords:
                        is_placed_ship_cell = True
                        break
                if not is_placed_ship_cell:
                    self.board_buttons[r][c].config(bg="SystemButtonFace")
        self.current_preview_cells = []

    def attempt_place_ship(self, start_row, start_col, length, orientation, ship_idx):
        """Próbuje umieścić statek na planszy po przeciągnięciu."""
        proposed_ship_coords = []
        for i in range(length):
            if orientation == "horizontal":
                proposed_ship_coords.append((start_row, start_col + i))
            else: # vertical
                proposed_ship_coords.append((start_row + i, start_col))

        # Walidacja: poza planszą, kolizje, stykające się statki
        valid = self.is_placement_valid(proposed_ship_coords) # Teraz is_placement_valid sprawdza wszystko
        
        if valid:
            self.placed_ships.append(tuple(proposed_ship_coords)) # Zapisz jako krotki krotek
            self.ship_labels[ship_idx]['placed'] = True
            self.ship_labels[ship_idx]['coords'] = tuple(proposed_ship_coords) # Zapisz też w słowniku etykiety
            self.ship_labels[ship_idx]['orientation'] = orientation
            
            self.ship_labels[ship_idx]['container'].destroy() # Usuń cały kontener statku z palety
            
            for r, c in proposed_ship_coords:
                if orientation == "horizontal":
                    self.board_buttons[r][c].config(image=self.images['ship_part_horizontal'], bg="SystemButtonFace") # Resetuj tło po upuszczeniu
                else:
                    self.board_buttons[r][c].config(image=self.images['ship_part_vertical'], bg="SystemButtonFace")
            
            # messagebox.showinfo("Sukces", f"Statek o długości {length} rozmieszczony!") # Zbyt dużo komunikatów
            self.update_placement_status()
            self.check_all_ships_placed()
        else:
            messagebox.showwarning("Błąd", "Nie można umieścić statku w tym miejscu! Sprawdź, czy nie wychodzi poza planszę, nie koliduje z innym statkiem i nie styka się z żadnym z nich.")
            # Jeśli nieudane, zresetuj wizualny stan etykiety w palecie
            self.ship_labels[ship_idx]['container'].config(relief="raised")
            # Nie "niszcz" etykiety, jeśli nie została umieszczona

    def is_placement_valid(self, proposed_coords):
        """Sprawdza, czy proponowane rozmieszczenie statku jest prawidłowe."""
        # Walidacja granic planszy
        for r, c in proposed_coords:
            if not (0 <= r < self.board_size and 0 <= c < self.board_size):
                return False

        # Walidacja kolizji z istniejącymi statkami
        for r, c in proposed_coords:
            for existing_ship_coords in self.placed_ships:
                if (r, c) in existing_ship_coords:
                    return False # Kolizja

        # Walidacja strefy wokół statku (statki nie mogą się stykać ani rogami, ani bokami)
        # Tworzymy zbiór wszystkich zajętych pól plus pól ochronnych
        occupied_and_protected = set()
        for ship in self.placed_ships:
            for r, c in ship:
                # Dodaj samo pole statku
                occupied_and_protected.add((r, c))
                # Dodaj pola ochronne wokół statku
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        protected_r, protected_c = r + dr, c + dc
                        if 0 <= protected_r < self.board_size and 0 <= protected_c < self.board_size:
                            occupied_and_protected.add((protected_r, protected_c))
        
        # Sprawdź, czy którykolwiek z proponowanych koordynatów koliduje z zajętymi/chronionymi polami (oprócz samych siebie)
        for r, c in proposed_coords:
            if (r, c) in occupied_and_protected:
                # Sprawdź, czy to pole nie jest częścią obecnego statku, który właśnie jest testowany
                # To jest logiczne tylko w przypadku re-walidacji. W świeżym umieszczaniu, każde trafienie oznacza błąd.
                # W uproszczeniu: jeśli już jest na liście zajętych/chronionych (a nie jest to część testowanego statku), to jest błąd.
                return False 
        
        return True

    def update_placement_status(self):
        """Aktualizuje etykietę informującą o liczbie statków do rozmieszczenia."""
        remaining_ships = sum(1 for s in self.ship_labels if not s['placed'])
        self.total_ships_label.config(text=f"Statki do rozmieszczenia: {remaining_ships}")

    def check_all_ships_placed(self):
        """Sprawdza, czy wszystkie statki zostały rozmieszczone i aktywuje przycisk zakończenia."""
        all_placed = all(s['placed'] for s in self.ship_labels)
        self.finish_placement_button.config(state=tk.NORMAL if all_placed else tk.DISABLED)


    def send_ships(self):
        """Wysyła rozmieszczone statki do serwera."""
        if all(s['placed'] for s in self.ship_labels):
            # Upewnij się, że self.placed_ships zawiera tylko listy list, a nie krotki dla JSON
            ships_data = json.dumps([[list(coords) for coords in ship] for ship in self.placed_ships])
            try:
                self.client.sendall(f"SET_SHIPS:{ships_data}\n".encode())
                self.status_label.config(text="Czekaj na przeciwnika...")
                self.finish_placement_button.config(state=tk.DISABLED)
                # Wyłącz interakcję z planszą po wysłaniu statków
                for r in range(self.board_size):
                    for c in range(self.board_size):
                        # Usuń bindowania drag&drop, bo faza umieszczania się kończy
                        self.board_buttons[r][c].unbind("<Motion>")
                        self.board_buttons[r][c].unbind("<ButtonRelease-1>")
                        self.board_buttons[r][c].unbind("<Button-3>")
                        self.board_buttons[r][c].config(state=tk.DISABLED) 
            except (ConnectionResetError, BrokenPipeError):
                self.handle_disconnection()
        else:
            messagebox.showwarning("Błąd", "Proszę rozmieścić wszystkie statki przed kontynuowaniem.")

    def create_game_boards(self):
        """Tworzy plansze gry (plansza przeciwnika i twoja plansza)."""
        self.clear_window()
        self.root.geometry(self.window_sizes.get(self.difficulty, '800x800'))
        
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, padx=20, pady=20)
        
        stats_frame = tk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=10)
        
        self.stats_label = tk.Label(stats_frame, text="Trafienia: 0 | Pudła: 0", font=("Arial", 12))
        self.stats_label.pack(side=tk.LEFT)
        
        self.turn_label = tk.Label(stats_frame, text="", font=("Arial", 12))
        self.turn_label.pack(side=tk.RIGHT)
        
        # Plansza przeciwnika
        enemy_frame = tk.Frame(main_frame, bd=2, relief="groove")
        enemy_frame.pack(pady=10)
        
        tk.Label(enemy_frame, text="Plansza przeciwnika - Twoje strzały:", 
                font=("Arial", 12)).grid(row=0, column=0, columnspan=self.board_size)
        
        self.enemy_board_buttons = [] # Przyciski planszy przeciwnika
        for i in range(self.board_size):
            row = []
            for j in range(self.board_size):
                btn = tk.Button(
                    enemy_frame, 
                    image=self.images['sea'], 
                    width=30, 
                    height=30, 
                    bd=1, 
                    relief="solid",
                    command=lambda x=i, y=j: self.make_shot(x, y),
                    state=tk.DISABLED # Domyślnie wyłączone, aktywowane w YOUR_TURN
                )
                btn.grid(row=i+1, column=j, padx=0, pady=0)
                row.append(btn)
            self.enemy_board_buttons.append(row)
        
        # Twoja plansza
        my_frame = tk.Frame(main_frame, bd=2, relief="groove")
        my_frame.pack(pady=10)
        
        tk.Label(my_frame, text="Twoja plansza - Statki:", 
                font=("Arial", 12)).grid(row=0, column=0, columnspan=self.board_size)
        
        self.my_board_labels = [] # Etykiety na własnej planszy
        for i in range(self.board_size):
            row = []
            for j in range(self.board_size):
                lbl = tk.Label(my_frame, image=self.images['sea'], width=30, height=30, bd=1, relief="solid")
                lbl.grid(row=i+1, column=j, padx=0, pady=0)
                # Ustawiamy obrazki statków na planszy gracza
                # Wyszukaj koordynaty (i, j) wśród rozmieszczonych statków
                for ship_info_dict in self.ship_labels: # Iterujemy po oryginalnych słownikach statków z palety
                    if ship_info_dict['placed'] and (i, j) in ship_info_dict['coords']:
                        if ship_info_dict['orientation'] == 'horizontal':
                            lbl.config(image=self.images['ship_part_horizontal']) 
                        else:
                            lbl.config(image=self.images['ship_part_vertical']) 
                        break
                row.append(lbl)
            self.my_board_labels.append(row)

        if self.my_turn:
            self.turn_label.config(text="Twoja tura!")
        else:
            self.turn_label.config(text="Czekaj na przeciwnika...")

    def make_shot(self, x, y):
        """Obsługuje strzał gracza w pole przeciwnika."""
        if self.game_started and self.my_turn and (x, y) not in self.my_shots:
            try:
                self.client.sendall(f"SHOT:{x},{y}\n".encode())
                # Przycisk zostanie wyłączony, gdy serwer odeśle rezultat strzału i zmieni turę
                # self.my_shots.add((x, y)) # Dodawanie tutaj, aby nie można było kliknąć ponownie zanim serwer odpowie
            except (ConnectionResetError, BrokenPipeError):
                self.handle_disconnection()

    def receive_messages(self):
        """Odbiera i przetwarza wiadomości od serwera."""
        while self.connected:
            try:
                data = self.client.recv(1024).decode().strip()
                if not data:
                    continue

                if data.startswith("DIFFICULTY_ACCEPTED:"):
                    self.root.after(0, self.create_setup_screen)

                elif data.startswith("DIFFICULTY_FORCED:"):
                    parts = data.split(":")
                    forced_difficulty = parts[1]
                    self.difficulty = forced_difficulty
                    self.board_size = self.ship_configs[self.difficulty]['board_size']
                    self.ship_lengths = sorted(self.ship_configs[self.difficulty]['ships'], reverse=True)
                    self.ship_count = sum(self.ship_configs[self.difficulty]['ships'])
                    self.root.after(0, self.create_setup_screen)
                    self.root.after(0, messagebox.showinfo, 
                                 "Info", f"Przeciwnik wybrał poziom: {forced_difficulty}. Twój poziom został zmieniony.")

                elif data == "START":
                    self.game_started = True
                    self.root.geometry(self.window_sizes.get(self.difficulty, '800x800'))
                    self.root.after(0, self.create_game_boards)

                elif data == "YOUR_TURN":
                    self.my_turn = True
                    self.root.after(0, self.update_turn_label, "Twoja tura!")
                    # Aktywuj przyciski na planszy przeciwnika
                    for r in range(self.board_size):
                        for c in range(self.board_size):
                            # Aktywuj tylko, jeśli pole nie było już strzelane i jest to przycisk
                            if (r, c) not in self.my_shots and self.enemy_board_buttons[r][c].cget('state') == tk.DISABLED: # Sprawdzamy stan
                                self.enemy_board_buttons[r][c].config(state=tk.NORMAL)

                elif data == "WAIT":
                    self.my_turn = False
                    self.root.after(0, self.update_turn_label, "Czekaj na przeciwnika...")
                    # Dezaktywuj przyciski na planszy przeciwnika
                    for r in range(self.board_size):
                        for c in range(self.board_size):
                            if self.enemy_board_buttons[r][c].cget('state') == tk.NORMAL: # Sprawdzamy stan
                                self.enemy_board_buttons[r][c].config(state=tk.DISABLED)

                elif data.startswith("SHOT_RESULT:"):
                    _, coords, result = data.split(":")
                    x, y = map(int, coords.split(","))
                    self.my_shots.add((x, y)) # Dodaj do swoich strzałów
                    if result == "HIT":
                        self.hits += 1
                        self.root.after(0, self.animate_explosion, self.enemy_board_buttons[x][y], 0, self.images['hit'])
                    else:
                        self.misses += 1
                        self.root.after(0, self.enemy_board_buttons[x][y].config, {'image': self.images['miss']})
                    self.root.after(0, self.update_stats_label)

                elif data.startswith("ENEMY_SHOT:"):
                    _, coords, result = data.split(":")
                    x, y = map(int, coords.split(","))
                    self.enemy_shots.add((x, y))
                    if hasattr(self, 'my_board_labels') and 0 <= x < len(self.my_board_labels) and 0 <= y < len(self.my_board_labels[0]):
                        if result == "HIT":
                            self.root.after(0, self.animate_explosion, self.my_board_labels[x][y], 0, self.images['hit'])
                        else:
                            self.root.after(0, self.my_board_labels[x][y].config, {'image': self.images['miss']})

                elif data == "SHIP_SUNK":
                    self.root.after(0, lambda: messagebox.showinfo("Statek zatopiony!", "Zatopiono statek przeciwnika! Masz kolejny ruch!"))
                
                elif data == "YOUR_SHIP_SUNK":
                    self.root.after(0, lambda: messagebox.showinfo("Twój statek zatopiony!", "Twój statek został zatopiony!"))

                elif data.startswith("GAME_OVER:"):
                    parts = data.split(":")
                    result = parts[1]
                    scores = json.loads(parts[2]) if len(parts) > 2 else []
                    self.root.after(0, self.handle_game_over, result, scores)

                elif data.startswith("REMATCH_REQUEST:"):
                    opponent_name = data.split(":")[1]
                    self.root.after(0, self.show_rematch_dialog, opponent_name)

                elif data.startswith("REMATCH_RESPONSE:"):
                    response = data.split(":")[1]
                    self.root.after(0, self.show_rematch_response, response)

                elif data == "RESET":
                    self.root.after(0, self.reset_game_state)

                elif data == "SERVER_FULL":
                    self.root.after(0, lambda: messagebox.showerror("Błąd", "Serwer jest pełny. Spróbuj później."))
                    self.root.after(0, self.root.destroy)
                
                elif data == "INVALID_SHOT":
                    self.root.after(0, lambda: messagebox.showwarning("Błąd strzału", "Nieprawidłowy strzał! Spróbuj ponownie."))
                    self.my_turn = True # Przywróć turę graczowi po błędnym strzale
                    self.root.after(0, self.update_turn_label, "Twoja tura!")

                elif data == "DUPLICATE_SHOT":
                    self.root.after(0, lambda: messagebox.showwarning("Błąd strzału", "Już strzelałeś w to miejsce!"))
                    self.my_turn = True # Przywróć turę graczowi po błędnym strzale
                    self.root.after(0, self.update_turn_label, "Twoja tura!")

            except (ConnectionResetError, BrokenPipeError):
                self.root.after(0, self.handle_disconnection)
                break
            except Exception as e:
                print(f"Błąd odbierania wiadomości: {e}")
                self.root.after(0, self.handle_disconnection)
                break

    def animate_explosion(self, widget, frame_index, final_image):
        """Odtwarza animację wybuchu na danym widżecie (przycisku/etykiecie)."""
        if not self.explosion_frames:
            # Jeśli nie ma ramek wybuchu, od razu ustaw finalny obraz
            widget.config(image=final_image)
            return

        if frame_index < len(self.explosion_frames):
            widget.config(image=self.explosion_frames[frame_index])
            self.root.after(100, self.animate_explosion, widget, frame_index + 1, final_image)
        else:
            # Po zakończeniu animacji, ustaw finalny obraz trafienia
            widget.config(image=final_image)

    def update_turn_label(self, text):
        """Aktualizuje etykietę informującą o czyjej turze."""
        if hasattr(self, 'turn_label'):
            self.turn_label.config(text=text)

    def update_stats_label(self):
        """Aktualizuje etykietę ze statystykami trafień i pudeł."""
        if hasattr(self, 'stats_label'):
            self.stats_label.config(text=f"Trafienia: {self.hits} | Pudła: {self.misses}")

    def create_scoreboard(self, scores):
        """Tworzy i wyświetla ekran tabeli wyników."""
        self.clear_window()
        self.root.geometry("800x600")
        
        main_frame = tk.Frame(self.root)
        main_frame.pack(expand=True, padx=20, pady=20)
        
        tk.Label(main_frame, text="Tabela wyników", font=("Arial", 16, "bold")).pack(pady=10)
        
        # --- Najlepsi gracze ---
        player_stats = {}
        for score in scores:
            winner = score['winner']
            loser = score['loser']
            
            player_stats.setdefault(winner, {'wins': 0, 'losses': 0})
            player_stats.setdefault(loser, {'wins': 0, 'losses': 0})
            
            player_stats[winner]['wins'] += 1
            player_stats[loser]['losses'] += 1
        
        sorted_players = sorted(player_stats.items(), key=lambda item: item[1]['wins'], reverse=True)
        
        top_players_frame = tk.LabelFrame(main_frame, text="Najlepsi gracze (liczba zwycięstw)", font=("Arial", 12, "bold"))
        top_players_frame.pack(pady=10, fill=tk.X)

        for i, (player_name, stats) in enumerate(sorted_players[:5]):
            win_ratio = (stats['wins'] / (stats['wins'] + stats['losses'])) * 100 if (stats['wins'] + stats['losses']) > 0 else 0
            tk.Label(top_players_frame, text=f"{i+1}. {player_name}: Wygrane: {stats['wins']}, Przegrane: {stats['losses']}, Stosunek: {win_ratio:.2f}%", font=("Arial", 10)).pack(anchor=tk.W, padx=10, pady=2)

        # --- Historia gier ---
        tk.Label(main_frame, text="Ostatnie gry", font=("Arial", 14, "bold")).pack(pady=10)

        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ('winner', 'loser', 'date', 'difficulty')
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=10,
                           yscrollcommand=scrollbar.set)
        
        tree.heading('winner', text='Zwycięzca')
        tree.heading('loser', text='Przegrany')
        tree.heading('date', text='Data')
        tree.heading('difficulty', text='Poziom')
        
        tree.column('winner', width=150)
        tree.column('loser', width=150)
        tree.column('date', width=150)
        tree.column('difficulty', width=100)
        
        for score in reversed(scores[-10:]):
            tree.insert('', tk.END, values=(
                score['winner'],
                score['loser'],
                score['date'],
                {'easy': 'Łatwy', 'medium': 'Średni', 'hard': 'Trudny'}.get(score['difficulty'], score['difficulty'])
            ))
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        rematch_btn = tk.Button(button_frame, text="Poproś o rewanż", 
                               font=("Arial", 12), command=self.request_rematch, width=15)
        rematch_btn.pack(side=tk.LEFT, padx=10)
        
        exit_btn = tk.Button(button_frame, text="Zakończ grę", 
                           font=("Arial", 12), command=self.root.destroy, width=15)
        exit_btn.pack(side=tk.LEFT, padx=10)

    def request_rematch(self):
        """Wysyła prośbę o rewanż do serwera."""
        try:
            self.client.sendall("REMATCH_REQUEST\n".encode())
        except (ConnectionResetError, BrokenPipeError):
            self.handle_disconnection()

    def respond_rematch(self, response):
        """Odpowiada na prośbę o rewanż."""
        try:
            self.client.sendall(f"REMATCH_RESPONSE:{response}\n".encode())
        except (ConnectionResetError, BrokenPipeError):
            self.handle_disconnection()

    def show_rematch_dialog(self, opponent_name):
        """Wyświetla dialog rewanżu."""
        response = messagebox.askyesno("Rewanż", f"{opponent_name} prosi o rewanż. Zaakceptować?")
        self.respond_rematch("ACCEPT" if response else "DECLINE")

    def show_rematch_response(self, response):
        """Wyświetla odpowiedź na prośbę o rewanż."""
        if response == "ACCEPT":
            messagebox.showinfo("Rewanż", "Przeciwnik zaakceptował rewanż! Rozpoczyna się nowa gra.")
        else:
            messagebox.showinfo("Rewanż", "Przeciwnik odrzucił rewanż. Wracasz do ekranu głównego.")
            self.create_welcome_screen() # Wróć do ekranu powitalnego jeśli rewanż odrzucony

    def reset_game_state(self):
        """Resetuje stan gry klienta dla nowej rundy (rewanżu)."""
        self.placed_ships = []
        self.my_shots = set()
        self.enemy_shots = set()
        self.hits = 0
        self.misses = 0
        self.game_started = False
        self.ship_labels = [] # Resetuj listę etykiet, bo będą tworzone od nowa
        self.ship_lengths = sorted(self.ship_configs[self.difficulty]['ships'], reverse=True) # Załaduj statki ponownie

        self.root.after(0, self.create_setup_screen)


    def handle_game_over(self, result, scores):
        """Obsługuje zakończenie gry."""
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
        """Obsługuje rozłączenie z serwerem."""
        self.connected = False
        messagebox.showerror("Błąd połączenia", "Utracono połączenie z serwerem. Gra zostanie zakończona.")
        self.root.destroy()

    def on_closing(self):
        """Obsługuje zamknięcie okna aplikacji."""
        if self.connected:
            try:
                self.client.sendall("DISCONNECT\n".encode()) # Poinformuj serwer o rozłączeniu
                self.client.close()
            except:
                pass
        self.root.destroy()

if __name__ == "__main__":
    BattleshipClient()