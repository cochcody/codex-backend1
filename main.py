import os
import json
import tkinter as tk
from tkinter import messagebox
import subprocess
import zipfile
from PIL import Image, ImageTk, ImageDraw
import pygame
import pyttsx3
import requests

# ============================================================
# CONFIG / GLOBALS
# ============================================================

BASE_URL = "https://codex-backend1.onrender.com"
ACCENT = "#00c8ff"
ACCENT_DARK = "#00cc55"
BG_MAIN = "#0d0d0d"
BG_PANEL = "#111111"
BG_TILE = "#1a1a1a"
BG_TILE_HOVER = "#222222"
TEXT_PRIMARY = "#ffffff"
TEXT_MUTED = "#888888"
TEXT_WARNING = "#ffb347"

current_user = {"data": None}


# ============================================================
# PATHS AND FOLDERS
# ============================================================

def get_codex_root():
    return os.path.join(os.getenv("LOCALAPPDATA"), "CodeX")

def get_config_path():
    return os.path.join(get_codex_root(), "config")

def get_library_path():
    return os.path.join(get_codex_root(), "library")

def get_user_path():
    return os.path.join(get_codex_root(), "user")

def get_logs_path():
    return os.path.join(get_codex_root(), "logs")

def get_accounts_file():
    return os.path.join(get_user_path(), "accounts.json")

def get_messages_file():
    return os.path.join(get_user_path(), "messages.json")

def get_installed_games_file():
    return os.path.join(get_library_path(), "installed_games.json")

def get_settings_file():
    return os.path.join(get_config_path(), "settings.json")

def get_remembered_user_file():
    return os.path.join(get_user_path(), "remembered_user.json")


def create_codex_folders():
    root = get_codex_root()
    folders = ["audio", "system", "ui", "user", "config", "library", "logs", "downloads", "cache"]
    for f in folders:
        os.makedirs(os.path.join(root, f), exist_ok=True)

    os.makedirs("C:/CodeXGames", exist_ok=True)

    if not os.path.exists(get_settings_file()):
        with open(get_settings_file(), "w") as f:
            json.dump({"installPath": "C:/CodeXGames/", "theme": "dark"}, f, indent=4)

    if not os.path.exists(get_installed_games_file()):
        with open(get_installed_games_file(), "w") as f:
            json.dump([], f, indent=4)

    if not os.path.exists(get_accounts_file()):
        with open(get_accounts_file(), "w") as f:
            json.dump({"users": []}, f, indent=4)

    if not os.path.exists(get_messages_file()):
        with open(get_messages_file(), "w") as f:
            json.dump({"messages": []}, f, indent=4)


# ============================================================
# DATA HELPERS
# ============================================================

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def load_installed_games():
    return load_json(get_installed_games_file(), [])

def save_installed_games(games):
    save_json(get_installed_games_file(), games)

def load_settings():
    return load_json(get_settings_file(), {"installPath": "C:/CodeXGames/", "theme": "dark"})

def save_settings_data(data):
    save_json(get_settings_file(), data)

def load_messages():
    return load_json(get_messages_file(), {"messages": []})

def save_messages(data):
    save_json(get_messages_file(), data)


# ============================================================
# REMEMBERED USER
# ============================================================

def remember_user(email):
    save_json(get_remembered_user_file(), {"email": email})

def forget_user():
    p = get_remembered_user_file()
    if os.path.exists(p):
        os.remove(p)

def load_remembered_user():
    data = load_json(get_remembered_user_file(), {})
    return data.get("email")


# ============================================================
# BACKEND API HELPERS
# ============================================================

def api_login(email, password):
    url = f"{BASE_URL}/api/auth/login"
    data = {"email": email, "password": password}
    try:
        r = requests.post(url, json=data, timeout=5)
        return r.json()
    except Exception as e:
        return {"success": False, "message": f"Connection error: {e}"}

def api_create_account(email, password):
    url = f"{BASE_URL}/api/auth/create"
    data = {"email": email, "password": password}
    try:
        r = requests.post(url, json=data, timeout=5)
        return r.json()
    except Exception as e:
        return {"success": False, "message": f"Connection error: {e}"}

def api_load_store():
    url = f"{BASE_URL}/api/store"
    r = requests.get(url)
    return r.json().get("games", [])

def api_load_owned(email):
    url = f"{BASE_URL}/api/user/owned?email={email}"
    r = requests.get(url)
    return r.json().get("owned_games", [])

def api_purchase(email, games):
    url = f"{BASE_URL}/api/purchase"
    data = {"email": email, "games": games}
    r = requests.post(url, json=data)
    return r.json()

def api_get_manifest():
    url = f"{BASE_URL}/public/manifest.json"
    r = requests.get(url)
    return r.json()

def download_game(url, save_path):
    r = requests.get(url, stream=True)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "wb") as f:
        for chunk in r.iter_content(1024):
            if chunk:
                f.write(chunk)


# ============================================================
# INSTALL SYSTEM
# ============================================================

def launch_game(exe_path):
    try:
        subprocess.Popen(exe_path)
    except Exception as e:
        print("Error launching:", e)

def install_game(game, install_root=None):
    settings = load_settings()
    base = install_root or settings["installPath"]
    install_path = os.path.join(base, game["folder"])
    os.makedirs(install_path, exist_ok=True)

    zip_path = os.path.join(install_path, "game.zip")
    download_game(BASE_URL + game["download"], zip_path)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(install_path)

    os.remove(zip_path)

    games = load_installed_games()
    exe_path = os.path.join(install_path, "Game.exe")
    entry = next((g for g in games if g["name"] == game["name"]), None)
    if entry:
        entry["exe"] = exe_path
    else:
        games.append({"name": game["name"], "exe": exe_path})
    save_installed_games(games)

def is_game_installed(name):
    return any(g["name"] == name for g in load_installed_games())


# ============================================================
# AUDIO + VOICE
# ============================================================

def playsound_pygame(path):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
    except Exception as e:
        print("Audio error:", e)

def speak_codex():
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        female_keywords = ["zira", "hazel", "eva", "female"]
        selected = None
        for v in voices:
            vid = v.id.lower()
            if any(k in vid for k in female_keywords):
                selected = v.id
                break
        if not selected and len(voices) > 1:
            selected = voices[-1].id
        if selected:
            engine.setProperty("voice", selected)
        engine.setProperty("rate", 150)
        engine.setProperty("volume", 1.0)
        engine.say("Welcome to Code-X")
        engine.runAndWait()
    except Exception as e:
        print("Voice error:", e)


# ============================================================
# SCROLLABLE FRAME
# ============================================================

class ScrollableFrame(tk.Frame):
    def __init__(self, parent, bg="#0d0d0d"):
        super().__init__(parent, bg=bg)
        canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=bg)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")


# ============================================================
# MAIN UI
# ============================================================

def launch_ui(root):

    def start_main_window():
        window = tk.Toplevel(root)
        window.title("Code‑X Launcher")
        window.geometry("1100x700")
        window.configure(bg=BG_MAIN)

        try:
            window.iconbitmap(os.path.join("assets", "logo.ico"))
        except:
            pass

        try:
            window.iconphoto(True, tk.PhotoImage(file="assets/logo.png"))
        except:
            pass

        cart = []
        cached_store = None

        sidebar = tk.Frame(window, bg=BG_PANEL, width=230)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        content = tk.Frame(window, bg=BG_MAIN)
        content.pack(side="right", fill="both", expand=True)

        # SIDEBAR HEADER
        top_sb = tk.Frame(sidebar, bg=BG_PANEL)
        top_sb.pack(fill="x", pady=(20, 10))

        try:
            logo_img = Image.open("assets/logo.png").resize((90, 90))
            logo_photo = ImageTk.PhotoImage(logo_img)
            logo_lbl = tk.Label(top_sb, image=logo_photo, bg=BG_PANEL)
            logo_lbl.image = logo_photo
            logo_lbl.pack(pady=(0, 5))
        except:
            pass

        tk.Label(
            top_sb, text="CODE‑X", fg=ACCENT,
            bg=BG_PANEL, font=("Segoe UI", 20, "bold")
        ).pack()

        user_label = tk.Label(
            sidebar, text="Not signed in", fg=TEXT_MUTED,
            bg=BG_PANEL, font=("Segoe UI", 9)
        )
        user_label.pack(pady=(5, 15))

        # HELPERS
        def clear_content():
            for w in content.winfo_children():
                w.destroy()

        def update_user_label():
            if current_user["data"]:
                user_label.config(
                    text=f"Signed in as: {current_user['data']['email']}",
                    fg=ACCENT
                )
            else:
                user_label.config(text="Not signed in", fg=TEXT_MUTED)

        def do_logout():
            forget_user()
            current_user["data"] = None
            update_user_label()
            messagebox.showinfo("Logout", "You have been signed out.")
            show_login()

        # COVER ART
        def load_cover_art(path, size=(90, 90), radius=14):
            try:
                img = Image.open(path).convert("RGBA")
            except:
                img = Image.new("RGBA", size, (30, 30, 30, 255))

            img = img.resize(size, Image.LANCZOS)

            mask = Image.new("L", size, 0)
            m = ImageDraw.Draw(mask)
            m.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)

            rounded = Image.new("RGBA", size)
            rounded.paste(img, (0, 0), mask)
            return ImageTk.PhotoImage(rounded)

        # GAME DETAILS
        def show_game_details(name):
            clear_content()

            header = tk.Frame(content, bg=BG_MAIN)
            header.pack(fill="x", pady=(20, 10), padx=30)

            tk.Label(
                header, text=name, fg=TEXT_PRIMARY, bg=BG_MAIN,
                font=("Segoe UI", 22, "bold")
            ).pack(side="left")

            installed_list = load_installed_games()
            installed_entry = next((g for g in installed_list if g["name"] == name), None)
            installed = installed_entry is not None

            body = tk.Frame(content, bg=BG_MAIN)
            body.pack(fill="both", expand=True, padx=30, pady=10)

            left = tk.Frame(body, bg=BG_MAIN)
            left.pack(side="left", anchor="n")

            right = tk.Frame(body, bg=BG_MAIN)
            right.pack(side="left", anchor="n", padx=40)

            cover_path = os.path.join("C:/CodeXGames", name, "cover.jpg")
            cover = load_cover_art(cover_path, size=(220, 220), radius=24)
            lbl = tk.Label(left, image=cover, bg=BG_MAIN)
            lbl.image = cover
            lbl.pack(pady=(0, 10))

            status = "Installed" if installed else "Not Installed"
            color = ACCENT if installed else TEXT_WARNING

            tk.Label(
                left, text=status, fg=color, bg=BG_MAIN,
                font=("Segoe UI", 11)
            ).pack(pady=(0, 10))

            def do_play():
                if not installed_entry:
                    return

                manifest = api_get_manifest()
                game_info = manifest.get(name)

                if game_info:
                    latest_version = game_info.get("version", "0")
                    installed_version = installed_entry.get("version", "0")

                    if latest_version != installed_version:
                        messagebox.showinfo("Update Available", f"Updating {name} to version {latest_version}...")

                        install_path = os.path.dirname(installed_entry["exe"])
                        zip_path = os.path.join(install_path, "update.zip")

                        download_game(BASE_URL + game_info["download"], zip_path)

                        with zipfile.ZipFile(zip_path, "r") as z:
                            z.extractall(install_path)

                        os.remove(zip_path)

                        installed_entry["version"] = latest_version
                        games = load_installed_games()
                        for g in games:
                            if g["name"] == name:
                                g["version"] = latest_version
                        save_installed_games(games)

                        messagebox.showinfo("Update Complete", f"{name} is now up to date.")

                launch_game(installed_entry["exe"])

            def do_install():
                games = api_load_store()
                game = next((g for g in games if g["name"] == name), None)
                if not game:
                    messagebox.showerror("Install", "Game not found in store.")
                    return
                install_game(game)
                show_game_details(name)

            btn_frame = tk.Frame(right, bg=BG_MAIN)
            btn_frame.pack(anchor="w", pady=(10, 0))

            if installed:
                tk.Button(
                    btn_frame, text="Play",
                    bg=ACCENT, fg="black",
                    activebackground=ACCENT_DARK,
                    activeforeground="black",
                    bd=0, padx=18, pady=8,
                    font=("Segoe UI", 11, "bold"),
                    command=do_play
                ).pack(side="left", padx=(0, 10))
            else:
                tk.Button(
                    btn_frame, text="Install",
                    bg=ACCENT, fg="black",
                    activebackground=ACCENT_DARK,
                    activeforeground="black",
                    bd=0, padx=18, pady=8,
                    font=("Segoe UI", 11, "bold"),
                    command=do_install
                ).pack(side="left", padx=(0, 10))

            tk.Button(
                btn_frame, text="Back to Library",
                bg=BG_TILE, fg=TEXT_PRIMARY,
                activebackground=BG_TILE_HOVER,
                activeforeground=TEXT_PRIMARY,
                bd=0, padx=14, pady=8,
                font=("Segoe UI", 10),
                command=lambda: show_library_filtered("")
            ).pack(side="left")

        # LIBRARY
        def show_library_filtered(query):
            clear_content()

            top = tk.Frame(content, bg=BG_MAIN)
            top.pack(fill="x", pady=(18, 5), padx=30)

            tk.Label(
                top, text="Library", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 20, "bold")
            ).pack(side="left")

            search_frame = tk.Frame(content, bg=BG_MAIN)
            search_frame.pack(fill="x", padx=30, pady=(0, 10))

            search_var = tk.StringVar(value=query)

            def update_list(*_):
                show_library_filtered(search_var.get())

            search_var.trace("w", update_list)

            search_entry = tk.Entry(
                search_frame, textvariable=search_var, width=40,
                bg=BG_TILE, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
                relief="flat", font=("Segoe UI", 11)
            )
            search_entry.pack(side="left", ipadx=8, ipady=6)
            search_entry.icursor(tk.END)
            search_entry.focus_set()

            if not current_user["data"]:
                tk.Label(
                    content, text="Sign in to view your library.",
                    fg=TEXT_WARNING, bg=BG_MAIN, font=("Segoe UI", 12)
                ).pack(pady=20)
                return

            owned = api_load_owned(current_user["data"]["email"])
            owned = sorted(owned)

            q = query.lower().strip()
            if q:
                owned = [g for g in owned if q in g.lower()]

            if not owned:
                tk.Label(
                    content, text="No games match your search.",
                    fg=TEXT_MUTED, bg=BG_MAIN, font=("Segoe UI", 13)
                ).pack(pady=20)
                return

            grid = ScrollableFrame(content, bg=BG_MAIN)
            grid.pack(fill="both", expand=True, padx=30, pady=10)

            covers = []
            columns = 4

            for index, gname in enumerate(owned):
                row = index // columns
                col = index % columns

                tile = tk.Frame(
                    grid.scrollable_frame,
                    bg=BG_TILE,
                    width=180,
                    height=240
                )
                tile.grid(row=row, column=col, padx=12, pady=12)
                tile.grid_propagate(False)

                def on_enter(e, f=tile):
                    f.config(bg=BG_TILE_HOVER)

                def on_leave(e, f=tile):
                    f.config(bg=BG_TILE)

                tile.bind("<Enter>", on_enter)
                tile.bind("<Leave>", on_leave)

                cover_path = f"C:/CodeXGames/{gname}/cover.jpg"
                img = load_cover_art(cover_path)
                covers.append(img)

                img_lbl = tk.Label(tile, image=img, bg=BG_TILE)
                img_lbl.pack(pady=(10, 8))

                name_lbl = tk.Label(
                    tile, text=gname,
                    fg=TEXT_PRIMARY, bg=BG_TILE,
                    font=("Segoe UI", 10, "bold"),
                    wraplength=160, justify="center"
                )
                name_lbl.pack(pady=(0, 4))

                play_lbl = tk.Label(
                    tile, text="View details",
                    fg=ACCENT, bg=BG_TILE,
                    font=("Segoe UI", 9)
                )
                play_lbl.pack()

                def open_details(e=None, n=gname):
                    show_game_details(n)

                tile.bind("<Button-1>", open_details)
                img_lbl.bind("<Button-1>", open_details)
                name_lbl.bind("<Button-1>", open_details)
                play_lbl.bind("<Button-1>", open_details)

        def show_library():
            show_library_filtered("")

        # STORE
        def show_store_filtered(query):
            nonlocal cached_store

            clear_content()

            top = tk.Frame(content, bg=BG_MAIN)
            top.pack(fill="x", pady=(18, 5), padx=30)

            tk.Label(
                top, text="Store", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 20, "bold")
            ).pack(side="left")

            search_frame = tk.Frame(content, bg=BG_MAIN)
            search_frame.pack(fill="x", padx=30, pady=(0, 10))
            search_var = tk.StringVar(value=query)

            def update_list(*_):
                show_store_filtered(search_var.get())

            search_var.trace("w", update_list)

            search_entry = tk.Entry(
                search_frame, textvariable=search_var, width=40,
                bg=BG_TILE, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY,
                relief="flat", font=("Segoe UI", 11)
            )
            search_entry.pack(side="left", ipadx=8, ipady=6)
            search_entry.icursor(tk.END)
            search_entry.focus_set()

            if cached_store is None:
                cached_store = api_load_store()

            store_games = cached_store or []

            q = query.lower().strip()
            if q:
                store_games = [g for g in store_games if q in g["name"].lower()]

            if not store_games:
                tk.Label(
                    content, text="No games found.",
                    fg=TEXT_MUTED, bg=BG_MAIN, font=("Segoe UI", 13)
                ).pack(pady=20)
                return

            list_frame = ScrollableFrame(content, bg=BG_MAIN)
            list_frame.pack(fill="both", expand=True, padx=30, pady=10)

            cover_images = []

            for game in store_games:
                frame = tk.Frame(list_frame.scrollable_frame, bg=BG_TILE, padx=14, pady=14)
                frame.pack(fill="x", pady=6)

                cover_path = os.path.join("C:/CodeXGames", game["folder"], "cover.jpg")
                cover = load_cover_art(cover_path)
                cover_images.append(cover)

                img_label = tk.Label(frame, image=cover, bg=BG_TILE)
                img_label.image = cover
                img_label.pack(side="left", padx=(0, 12))

                text_frame = tk.Frame(frame, bg=BG_TILE)
                text_frame.pack(side="left", padx=10)

                tk.Label(
                    text_frame, text=game["name"], fg=TEXT_PRIMARY,
                    bg=BG_TILE, font=("Segoe UI", 13, "bold")
                ).pack(anchor="w")

                tk.Label(
                    text_frame, text=f"${game['price']:.2f}", fg=ACCENT,
                    bg=BG_TILE, font=("Segoe UI", 10)
                ).pack(anchor="w", pady=(2, 0))

                btn_frame = tk.Frame(frame, bg=BG_TILE)
                btn_frame.pack(side="right")

                tk.Button(
                    btn_frame, text="Details",
                    bg=BG_PANEL, fg=TEXT_PRIMARY,
                    activebackground=BG_TILE_HOVER,
                    activeforeground=TEXT_PRIMARY,
                    bd=0, padx=12, pady=6,
                    font=("Segoe UI", 9),
                    command=lambda n=game["name"]: show_game_details(n)
                ).pack(side="left", padx=(0, 8))

                def add_to_cart(g=game):
                    cart.append(g)
                    messagebox.showinfo("Cart", f"{g['name']} added to cart.")

                tk.Button(
                    btn_frame, text="Add to Cart",
                    bg=ACCENT, fg="black",
                    activebackground=ACCENT_DARK,
                    activeforeground="black",
                    bd=0, padx=12, pady=6,
                    font=("Segoe UI", 9, "bold"),
                    command=add_to_cart
                ).pack(side="left")

        def show_store():
            show_store_filtered("")

        # CART
        def show_cart():
            clear_content()

            tk.Label(
                content, text="Cart", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 20, "bold")
            ).pack(pady=(20, 10))

            if not cart:
                tk.Label(
                    content, text="Your cart is empty.",
                    fg=TEXT_MUTED, bg=BG_MAIN, font=("Segoe UI", 13)
                ).pack(pady=20)
                return

            total = sum(g["price"] for g in cart)

            list_frame = ScrollableFrame(content, bg=BG_MAIN)
            list_frame.pack(fill="both", expand=True, padx=30, pady=10)

            for game in cart:
                frame = tk.Frame(list_frame.scrollable_frame, bg=BG_TILE, padx=12, pady=12)
                frame.pack(fill="x", pady=5)

                tk.Label(
                    frame, text=f"{game['name']}",
                    fg=TEXT_PRIMARY, bg=BG_TILE,
                    font=("Segoe UI", 12, "bold")
                ).pack(side="left")

                tk.Label(
                    frame, text=f"${game['price']:.2f}",
                    fg=ACCENT, bg=BG_TILE,
                    font=("Segoe UI", 11)
                ).pack(side="left", padx=(10, 0))

                def remove(g=game):
                    cart.remove(g)
                    show_cart()

                tk.Button(
                    frame, text="Remove",
                    bg=BG_PANEL, fg=TEXT_PRIMARY,
                    activebackground=BG_TILE_HOVER,
                    activeforeground=TEXT_PRIMARY,
                    bd=0, padx=10, pady=4,
                    font=("Segoe UI", 9),
                    command=remove
                ).pack(side="right")

            bottom = tk.Frame(content, bg=BG_MAIN)
            bottom.pack(fill="x", padx=30, pady=(10, 20))

            tk.Label(
                bottom, text=f"Total: ${total:.2f}",
                fg=TEXT_PRIMARY, bg=BG_MAIN,
                font=("Segoe UI", 13, "bold")
            ).pack(side="left")

            def checkout():
                if not current_user["data"]:
                    messagebox.showinfo("Sign In Required", "Please sign in first.")
                    return

                names = [g["name"] for g in cart]
                result = api_purchase(current_user["data"]["email"], names)

                if result.get("success"):
                    messagebox.showinfo("Purchase Complete", "Games added to your account.")
                    cart.clear()
                    show_cart()
                else:
                    messagebox.showerror("Error", result.get("message", "Purchase failed"))

            tk.Button(
                bottom, text="Checkout (no billing yet)",
                bg=ACCENT, fg="black",
                activebackground=ACCENT_DARK,
                activeforeground="black",
                bd=0, padx=16, pady=6,
                font=("Segoe UI", 10, "bold"),
                command=checkout
            ).pack(side="right")

        # SETTINGS
        def show_settings():
            clear_content()

            tk.Label(
                content, text="Settings", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 20, "bold")
            ).pack(pady=(20, 10))

            settings = load_settings()

            form = tk.Frame(content, bg=BG_MAIN)
            form.pack(pady=10, padx=30, anchor="w")

            tk.Label(
                form, text="Install Path:", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 11)
            ).grid(row=0, column=0, sticky="w", pady=(0, 4))

            entry = tk.Entry(
                form, width=50, bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat",
                font=("Segoe UI", 10)
            )
            entry.grid(row=1, column=0, sticky="w")
            entry.insert(0, settings.get("installPath", "C:/CodeXGames/"))

            def save():
                path = entry.get().strip()
                if not path:
                    messagebox.showinfo("Settings", "Install path cannot be empty.")
                    return
                save_settings_data({"installPath": path, "theme": "dark"})
                messagebox.showinfo("Settings", "Settings saved.")

            tk.Button(
                content, text="Save Settings",
                bg=ACCENT, fg="black",
                activebackground=ACCENT_DARK,
                activeforeground="black",
                bd=0, padx=14, pady=6,
                font=("Segoe UI", 10, "bold"),
                command=save
            ).pack(pady=(10, 0))

        # CONTACT
        def show_contact():
            clear_content()

            tk.Label(
                content, text="Contact Support", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 20, "bold")
            ).pack(pady=(20, 10))

            form = tk.Frame(content, bg=BG_MAIN)
            form.pack(pady=10, padx=30, anchor="w")

            tk.Label(form, text="Name:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=0, column=0, sticky="w")
            name_entry = tk.Entry(
                form, width=50, bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            name_entry.grid(row=1, column=0, pady=(0, 8), sticky="w")

            tk.Label(form, text="Email:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=2, column=0, sticky="w")
            email_entry = tk.Entry(
                form, width=50, bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            email_entry.grid(row=3, column=0, pady=(0, 8), sticky="w")

            tk.Label(form, text="Message:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=4, column=0, sticky="w")
            msg_entry = tk.Text(
                form, width=60, height=8, bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            msg_entry.grid(row=5, column=0, pady=(0, 8))

            def send():
                msg = msg_entry.get("1.0", "end").strip()
                if not msg:
                    messagebox.showinfo("Contact", "Please enter a message.")
                    return

                data = load_messages()
                data["messages"].append({
                    "name": name_entry.get().strip(),
                    "email": email_entry.get().strip(),
                    "message": msg
                })
                save_messages(data)

                messagebox.showinfo("Contact", "Message saved.")
                name_entry.delete(0, "end")
                email_entry.delete(0, "end")
                msg_entry.delete("1.0", "end")

            tk.Button(
                content, text="Send Message",
                bg=ACCENT, fg="black",
                activebackground=ACCENT_DARK,
                activeforeground="black",
                bd=0, padx=14, pady=6,
                font=("Segoe UI", 10, "bold"),
                command=send
            ).pack(pady=(10, 0))

        # LOGIN
        def show_login():
            clear_content()

            tk.Label(
                content, text="Sign In", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 20, "bold")
            ).pack(pady=(30, 10))

            form = tk.Frame(content, bg=BG_MAIN)
            form.pack(pady=10)

            tk.Label(form, text="Email:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=0, column=0, sticky="w")
            email_entry = tk.Entry(
                form, width=40, bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            email_entry.grid(row=1, column=0, pady=(0, 8))

            remembered = load_remembered_user()
            if remembered:
                email_entry.insert(0, remembered)

            tk.Label(form, text="Password:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=2, column=0, sticky="w")
            pwd_entry = tk.Entry(
                form, width=40, show="*", bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            pwd_entry.grid(row=3, column=0, pady=(0, 8))

            keep_var = tk.BooleanVar(value=True)
            tk.Checkbutton(
                form, text="Keep me signed in",
                variable=keep_var, fg=TEXT_PRIMARY, bg=BG_MAIN,
                activebackground=BG_MAIN, activeforeground=TEXT_PRIMARY,
                selectcolor=BG_MAIN
            ).grid(row=4, column=0, sticky="w", pady=(0, 10))

            def do_login():
                email = email_entry.get().strip()
                pwd = pwd_entry.get().strip()

                if not email or not pwd:
                    messagebox.showerror("Login", "Email and password required.")
                    return

                result = api_login(email, pwd)
                if result.get("success"):
                    current_user["data"] = result["user"]
                    if keep_var.get():
                        remember_user(email)
                    else:
                        forget_user()
                    update_user_label()
                    messagebox.showinfo("Login", "Signed in successfully.")
                    show_library()
                else:
                    messagebox.showerror("Login", result.get("message", "Invalid email or password."))

            btn_row = tk.Frame(content, bg=BG_MAIN)
            btn_row.pack(pady=10)

            tk.Button(
                btn_row, text="Sign In",
                bg=ACCENT, fg="black",
                activebackground=ACCENT_DARK,
                activeforeground="black",
                bd=0, padx=16, pady=6,
                font=("Segoe UI", 10, "bold"),
                command=do_login
            ).pack(side="left", padx=(0, 10))

            tk.Button(
                btn_row, text="Create Account",
                bg=BG_TILE, fg=TEXT_PRIMARY,
                activebackground=BG_TILE_HOVER,
                activeforeground=TEXT_PRIMARY,
                bd=0, padx=14, pady=6,
                font=("Segoe UI", 10),
                command=show_create_account
            ).pack(side="left")

        # CREATE ACCOUNT
        def show_create_account():
            clear_content()

            tk.Label(
                content, text="Create Account", fg=TEXT_PRIMARY,
                bg=BG_MAIN, font=("Segoe UI", 20, "bold")
            ).pack(pady=(30, 10))

            form = tk.Frame(content, bg=BG_MAIN)
            form.pack(pady=10)

            tk.Label(form, text="Email:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=0, column=0, sticky="w")
            email_entry = tk.Entry(
                form, width=40, bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            email_entry.grid(row=1, column=0, pady=(0, 8))

            tk.Label(form, text="Password:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=2, column=0, sticky="w")
            pwd_entry = tk.Entry(
                form, width=40, show="*", bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            pwd_entry.grid(row=3, column=0, pady=(0, 8))

            tk.Label(form, text="Confirm Password:", fg=TEXT_PRIMARY, bg=BG_MAIN).grid(row=4, column=0, sticky="w")
            confirm_entry = tk.Entry(
                form, width=40, show="*", bg=BG_TILE, fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY, relief="flat"
            )
            confirm_entry.grid(row=5, column=0, pady=(0, 8))

            def do_create():
                email = email_entry.get().strip()
                pwd = pwd_entry.get().strip()
                confirm = confirm_entry.get().strip()

                if not email or not pwd:
                    messagebox.showinfo("Create Account", "Email and password required.")
                    return
                if pwd != confirm:
                    messagebox.showinfo("Create Account", "Passwords do not match.")
                    return

                result = api_create_account(email, pwd)
                if result.get("success"):
                    messagebox.showinfo("Create Account", "Account created. You can sign in now.")
                    show_login()
                else:
                    messagebox.showerror("Create Account", result.get("message", "Could not create account."))

            btn_row = tk.Frame(content, bg=BG_MAIN)
            btn_row.pack(pady=10)

            tk.Button(
                btn_row, text="Create Account",
                bg=ACCENT, fg="black",
                activebackground=ACCENT_DARK,
                activeforeground="black",
                bd=0, padx=16, pady=6,
                font=("Segoe UI", 10, "bold"),
                command=do_create
            ).pack(side="left", padx=(0, 10))

            tk.Button(
                btn_row, text="Back to Login",
                bg=BG_TILE, fg=TEXT_PRIMARY,
                activebackground=BG_TILE_HOVER,
                activeforeground=TEXT_PRIMARY,
                bd=0, padx=14, pady=6,
                font=("Segoe UI", 10),
                command=show_login
            ).pack(side="left")

        # SIDEBAR BUTTONS
        def make_sidebar_button(text, command):
            btn = tk.Button(
                sidebar, text=text,
                bg=BG_PANEL, fg=TEXT_PRIMARY,
                activebackground=BG_TILE, activeforeground=TEXT_PRIMARY,
                bd=0, padx=14, pady=8,
                font=("Segoe UI", 11),
                anchor="w",
                command=command
            )
            btn.pack(fill="x", padx=18, pady=3)
            return btn

        make_sidebar_button("Library", show_library)
        make_sidebar_button("Store", show_store)
        make_sidebar_button("Cart", show_cart)
        make_sidebar_button("Account", show_login)
        make_sidebar_button("Contact", show_contact)
        make_sidebar_button("Settings", show_settings)

        tk.Frame(sidebar, bg=BG_PANEL, height=1).pack(fill="x", pady=(10, 6))

        tk.Button(
            sidebar, text="Sign Out",
            bg="#661111", fg=TEXT_PRIMARY,
            activebackground="#882222", activeforeground=TEXT_PRIMARY,
            bd=0, padx=14, pady=8,
            font=("Segoe UI", 11),
            anchor="w",
            command=do_logout
        ).pack(fill="x", padx=18, pady=(0, 12))

        # DEFAULT SCREEN
        update_user_label()
        if current_user["data"]:
            show_library()
        else:
            show_login()

        window.mainloop()

    start_main_window()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    create_codex_folders()

    root = tk.Tk()
    root.withdraw()

    launch_ui(root)

    root.mainloop()
