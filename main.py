import os
import json
import time
import stripe
import jwt
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

# ============================================================
#  CONFIG
# ============================================================

JWT_SECRET = "SUPER_SECRET_KEY_CHANGE_THIS"
JWT_ALGO = "HS256"

ADMIN_EMAIL = "codexgamessupport@gmail.com"
ADMIN_PASSWORD = "ChangeThisAdminPassword123"  # change in real use

STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_L5IOHbIlYrWO1s7lnsk9E2uGtdS5QbDZ"

stripe.api_key = STRIPE_SECRET_KEY

PLATFORM_FEE_PERCENT = 20

ALLOWED_EXTENSIONS = {"zip", "exe"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================================
#  FILE PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PUBLIC_DIR, exist_ok=True)
os.makedirs(os.path.join(PUBLIC_DIR, "games"), exist_ok=True)

ACCOUNTS_PATH = os.path.join(DATA_DIR, "accounts.json")
GAMES_PATH = os.path.join(DATA_DIR, "games.json")
PURCHASES_PATH = os.path.join(DATA_DIR, "purchases.json")
MESSAGES_PATH = os.path.join(DATA_DIR, "messages.json")
UPLOADS_PATH = os.path.join(DATA_DIR, "uploads.json")

DEFAULT_ACCOUNTS = {"users": []}
DEFAULT_GAMES = {"games": []}
DEFAULT_PURCHASES = {"purchases": []}
DEFAULT_MESSAGES = {"messages": []}
DEFAULT_UPLOADS = {"uploads": []}

# ============================================================
#  JSON HELPERS
# ============================================================

def load_json(path, default):
    if not os.path.exists(path):
        save_json(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving JSON to {path}: {e}")

# ============================================================
#  AUTO‑CREATE ADMIN ACCOUNT
# ============================================================

def ensure_admin_account():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    if "users" not in accounts or not isinstance(accounts["users"], list):
        accounts["users"] = []

    if not any(u.get("email") == ADMIN_EMAIL for u in accounts["users"]):
        admin_user = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "role": "admin",
            "owned_games": []
        }
        accounts["users"].append(admin_user)
        save_json(ACCOUNTS_PATH, accounts)

ensure_admin_account()

# ============================================================
#  JWT HELPERS
# ============================================================

def create_token(user):
    payload = {
        "email": user["email"],
        "role": user["role"],
        "exp": time.time() + 60 * 60 * 24 * 7
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        return None

def get_user_from_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ")[1]
    return decode_token(token)

# ============================================================
#  ROLE DECORATORS
# ============================================================

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_user_from_token()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        request.user = user
        return f(*args, **kwargs)
    return wrapper

def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_user_from_token()
        if not user or user.get("role") != "admin":
            return jsonify({"error": "Admin only"}), 403
        request.user = user
        return f(*args, **kwargs)
    return wrapper

def require_developer(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_user_from_token()
        if not user or user.get("role") != "developer":
            return jsonify({"error": "Developer only"}), 403
        request.user = user
        return f(*args, **kwargs)
    return wrapper

# ============================================================
#  FLASK APP
# ============================================================

app = Flask(__name__)
CORS(app)

# ============================================================
#  AUTH
# ============================================================

@app.post("/api/auth/create")
def create_account():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = (data.get("email") or "").lower().strip()
    password = data.get("password")
    role = data.get("role", "player")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required"}), 400

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    if any(u.get("email") == email for u in accounts.get("users", [])):
        return jsonify({"success": False, "message": "Account exists"}), 400

    if email == ADMIN_EMAIL:
        role = "admin"

    user = {
        "email": email,
        "password": password,
        "role": role,
        "owned_games": []
    }

    accounts.setdefault("users", [])
    accounts["users"].append(user)
    save_json(ACCOUNTS_PATH, accounts)

    token = create_token(user)
    return jsonify({"success": True, "token": token})

@app.post("/api/auth/login")
def login():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = (data.get("email") or "").lower().strip()
    password = data.get("password")

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    user = next((u for u in accounts.get("users", []) if u.get("email") == email), None)

    if not user or user.get("password") != password:
        return jsonify({"success": False, "message": "Invalid login"}), 401

    token = create_token(user)
    return jsonify({"success": True, "token": token})

@app.get("/api/auth/me")
@require_auth
def auth_me():
    return jsonify(request.user)

# ============================================================
#  STORE
# ============================================================

@app.get("/api/store")
def store():
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    return jsonify(games)

# ============================================================
#  DEVELOPER UPLOAD (REAL FILE + METADATA)

@app.post("/api/dev/upload")
@require_developer
def dev_upload():
    try:
        data = request.form.to_dict()
    except Exception:
        return jsonify({"success": False, "message": "Invalid form data"}), 400

    file = request.files.get("build")

    required = ["id", "name", "price"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({
            "success": False,
            "message": f"Missing fields: {', '.join(missing)}"
        }), 400

    if not file or file.filename == "":
        return jsonify({
            "success": False,
            "message": "Build file is required."
        }), 400

    if not allowed_file(file.filename):
        return jsonify({
            "success": False,
            "message": "Invalid file type. Use ZIP or EXE."
        }), 400

    filename = secure_filename(file.filename)

    folder_name = data.get("folder") or data["id"]
    game_dir = os.path.join(PUBLIC_DIR, "games", folder_name)
    try:
        os.makedirs(game_dir, exist_ok=True)
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Could not create game folder: {e}"
        }), 500

    file_path = os.path.join(game_dir, filename)
    try:
        file.save(file_path)
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Could not save file: {e}"
        }), 500

    download_path = f"/public/games/{folder_name}/{filename}"

    upload = {
        "id": data["id"],
        "name": data["name"],
        "price": data["price"],
        "developer_account": data.get("developer_account"),
        "folder": folder_name,
        "download": download_path,
        "developer_email": request.user["email"],
        "status": "pending",
        "timestamp": int(time.time())
    }

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    uploads.setdefault("uploads", [])
    uploads["uploads"].append(upload)
    save_json(UPLOADS_PATH, uploads)

    return jsonify({"success": True})

# ============================================================
#  ADMIN ROUTES
# ============================================================

@app.get("/api/admin/uploads")
@require_admin
def admin_get_uploads():
    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    return jsonify(uploads)

@app.post("/api/admin/approve")
@require_admin
def admin_approve():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    upload_id = data.get("upload_id")
    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    games = load_json(GAMES_PATH, DEFAULT_GAMES)

    upload = next((u for u in uploads.get("uploads", []) if u.get("id") == upload_id), None)
    if not upload:
        return jsonify({"error": "Upload not found"}), 404

    games.setdefault("games", [])
    games["games"].append({
        "id": upload["id"],
        "name": upload["name"],
        "price": upload["price"],
        "developer_account": upload.get("developer_account"),
        "folder": upload["folder"],
        "download": upload["download"]
    })

    upload["status"] = "approved"

    save_json(GAMES_PATH, games)
    save_json(UPLOADS_PATH, uploads)

    return jsonify({"success": True})

@app.post("/api/admin/reject")
@require_admin
def admin_reject():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    upload_id = data.get("upload_id")
    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    upload = next((u for u in uploads.get("uploads", []) if u.get("id") == upload_id), None)

    if not upload:
        return jsonify({"error": "Upload not found"}), 404

    upload["status"] = "rejected"
    save_json(UPLOADS_PATH, uploads)

    return jsonify({"success": True})

# ============================================================
#  STATIC FILES
# ============================================================

@app.get("/public/<path:filename>")
def public_files(filename):
    return send_from_directory(PUBLIC_DIR, filename)

# ============================================================
#  RUN
# ============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
