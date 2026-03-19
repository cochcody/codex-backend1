import os
import json
import time
import stripe
import jwt
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ============================================================
#  CONFIG
# ============================================================

JWT_SECRET = "SUPER_SECRET_KEY_CHANGE_THIS"
JWT_ALGO = "HS256"

ADMIN_EMAIL = "codexgamessupport@gmail.com"
ADMIN_PASSWORD = "Codexgames1828"  # change in real use

STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "whsec_L5IOHbIlYrWO1s7lnsk9E2uGtdS5QbDZ"

stripe.api_key = STRIPE_SECRET_KEY

PLATFORM_FEE_PERCENT = 20

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
    except:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

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
    except:
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
        if not user or user["role"] != "admin":
            return jsonify({"error": "Admin only"}), 403
        request.user = user
        return f(*args, **kwargs)
    return wrapper

def require_developer(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_user_from_token()
        if not user or user["role"] != "developer":
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
    data = request.get_json(force=True)
    email = data.get("email", "").lower().strip()
    password = data.get("password")
    role = data.get("role", "player")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required"}), 400

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    if any(u["email"] == email for u in accounts["users"]):
        return jsonify({"success": False, "message": "Account exists"}), 400

    if email == ADMIN_EMAIL:
        role = "admin"

    user = {
        "email": email,
        "password": password,
        "role": role,
        "owned_games": []
    }

    accounts["users"].append(user)
    save_json(ACCOUNTS_PATH, accounts)

    token = create_token(user)
    return jsonify({"success": True, "token": token})

@app.post("/api/auth/login")
def login():
    data = request.get_json(force=True)
    email = data.get("email", "").lower().strip()
    password = data.get("password")

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    user = next((u for u in accounts["users"] if u["email"] == email), None)

    if not user or user["password"] != password:
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
#  DEVELOPER UPLOAD (METADATA ONLY)
# ============================================================

@app.post("/api/dev/upload")
@require_developer
def dev_upload():
    data = request.form.to_dict()

    required_fields = ["id", "name", "price", "folder", "download"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return jsonify({
            "success": False,
            "message": f"Missing fields: {', '.join(missing)}"
        }), 400

    upload = {
        "id": data["id"],
        "name": data["name"],
        "price": data["price"],
        "developer_account": data.get("developer_account"),
        "folder": data["folder"],
        "download": data["download"],
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
    data = request.get_json(force=True)
    upload_id = data.get("upload_id")

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    games = load_json(GAMES_PATH, DEFAULT_GAMES)

    upload = next((u for u in uploads["uploads"] if u["id"] == upload_id), None)
    if not upload:
        return jsonify({"error": "Upload not found"}), 404

    games.setdefault("games", [])
    games["games"].append({
        "id": upload["id"],
        "name": upload["name"],
        "price": upload["price"],
        "developer_account": upload["developer_account"],
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
    data = request.get_json(force=True)
    upload_id = data.get("upload_id")

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    upload = next((u for u in uploads["uploads"] if u["id"] == upload_id), None)

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
