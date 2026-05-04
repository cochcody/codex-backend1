import os
import json
import time
import stripe
import jwt
import requests
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
ADMIN_PASSWORD = "Codexgames1828"

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
DEV_APPS_PATH = os.path.join(DATA_DIR, "developer_applications.json")
PAYOUTS_PATH = os.path.join(DATA_DIR, "payouts.json")

DEFAULT_ACCOUNTS = {"users": []}
DEFAULT_GAMES = {"games": []}
DEFAULT_PURCHASES = {"purchases": []}
DEFAULT_MESSAGES = {"messages": []}
DEFAULT_UPLOADS = {"uploads": []}
DEFAULT_DEV_APPS = {"applications": []}
DEFAULT_PAYOUTS = {"payouts": []}

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
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving JSON to {path}: {e}")

# ============================================================
#  JSONBIN (Developer Applications Only)
# ============================================================

JSONBIN_URL = "https://api.jsonbin.io/v3/b/69cb36c436566621a8642602"
JSONBIN_KEY = "$2a$10$JMbtIt49UIA0cZntnOWtfu695M3OqQ50NY5qUx0VgbAnvndW74beC"

def load_dev_apps():
    headers = {"X-Master-Key": JSONBIN_KEY}
    r = requests.get(JSONBIN_URL, headers=headers)
    r.raise_for_status()
    data = r.json()
    record = data.get("record") or {}
    apps = record.get("applications")
    return apps if isinstance(apps, list) else []

def save_dev_apps(apps):
    headers = {"X-Master-Key": JSONBIN_KEY}
    body = {"applications": apps}
    r = requests.put(JSONBIN_URL, json=body, headers=headers)
    r.raise_for_status()

# ============================================================
#  JWT HELPERS
# ============================================================

def create_token(user):
    payload = {
        "email": user["email"],
        "role": user.get("role", "player"),
        "gamertag": user.get("gamertag"),
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
    return decode_token(auth.split(" ")[1])

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
#  AUTO‑CREATE ADMIN ACCOUNT
# ============================================================

def ensure_admin_account():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])

    existing = next((u for u in users if u.get("email") == ADMIN_EMAIL), None)
    if not existing:
        users.append({
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "role": "admin",
            "gamertag": "CodeXAdmin",
            "status": "active",
            "owned_games": [],
            "company": "Code‑X"
        })
        save_json(ACCOUNTS_PATH, accounts)

ensure_admin_account()

# ============================================================
#  AUTH
# ============================================================

@app.post("/api/auth/create")
def create_account():
    data = request.get_json(force=True)

    email = (data.get("email") or "").lower().strip()
    password = data.get("password")
    gamertag = (data.get("gamertag") or "").strip()

    if not email or not password or not gamertag:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])

    if any(u.get("email") == email for u in users):
        return jsonify({"success": False, "message": "Account exists"}), 400

    if any((u.get("gamertag") or "").lower() == gamertag.lower() for u in users):
        return jsonify({"success": False, "message": "Gamertag taken"}), 400

    role = "admin" if email == ADMIN_EMAIL else "player"

    user = {
        "email": email,
        "password": password,
        "role": role,
        "gamertag": gamertag,
        "status": "active",
        "owned_games": []
    }

    users.append(user)
    save_json(ACCOUNTS_PATH, accounts)

    token = create_token(user)
    return jsonify({"success": True, "token": token})

@app.post("/api/auth/login")
def login():
    data = request.get_json(force=True)

    email = (data.get("email") or "").lower().strip()
    password = data.get("password")

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])
    user = next((u for u in users if u.get("email") == email), None)

    if not user or user.get("password") != password:
        return jsonify({"success": False, "message": "Invalid login"}), 401

    token = create_token(user)
    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "email": user["email"],
            "role": user.get("role", "player"),
            "gamertag": user.get("gamertag"),
            "status": user.get("status", "active"),
            "company": user.get("company"),
            "owned_games": user.get("owned_games", [])
        }
    })

@app.get("/api/auth/me")
@require_auth
def auth_me():
    return jsonify(request.user)

# ============================================================
#  DEVELOPER APPLICATIONS (JSONBIN)
# ============================================================

@app.post("/api/dev/apply")
@require_auth
def apply_developer():
    data = request.get_json(force=True)

    email = request.user["email"]
    company = (data.get("company") or "").strip()
    website = (data.get("website") or "").strip()
    description = (data.get("description") or "").strip()

    if not company:
        return jsonify({"success": False, "message": "Company required"}), 400

    apps = load_dev_apps()

    if any(a.get("email") == email and a.get("status") == "pending" for a in apps):
        return jsonify({"success": False, "message": "Already pending"}), 400

    apps.append({
        "email": email,
        "company": company,
        "website": website,
        "description": description,
        "status": "pending",
        "timestamp": int(time.time())
    })

    save_dev_apps(apps)
    return jsonify({"success": True})

@app.get("/api/admin/dev-applications")
@require_admin
def admin_dev_apps():
    return jsonify({"applications": load_dev_apps()})

@app.post("/api/admin/dev-approve")
@require_admin
def admin_dev_approve():
    data = request.get_json(force=True)
    email = data.get("email")

    apps = load_dev_apps()
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    app_entry = next((a for a in apps if a.get("email") == email), None)
    user = next((u for u in accounts["users"] if u.get("email") == email), None)

    if not app_entry or not user:
        return jsonify({"success": False}), 404

    app_entry["status"] = "approved"
    user["role"] = "developer"
    user["company"] = app_entry.get("company")

    save_dev_apps(apps)
    save_json(ACCOUNTS_PATH, accounts)

    return jsonify({"success": True})

@app.post("/api/admin/dev-reject")
@require_admin
def admin_dev_reject():
    data = request.get_json(force=True)
    email = data.get("email")

    apps = load_dev_apps()
    app_entry = next((a for a in apps if a.get("email") == email), None)

    if not app_entry:
        return jsonify({"success": False}), 404

    app_entry["status"] = "rejected"
    save_dev_apps(apps)

    return jsonify({"success": True})

# ============================================================
#  STORE + PURCHASES
# ============================================================

@app.get("/api/store")
def store():
    games = load_json(GAMES_PATH, DEFAULT_GAMES).get("games", [])
    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS).get("uploads", [])

    approved_uploads = [
        {
            "id": u["id"],
            "name": u["name"],
            "price": u["price"],
            "description": u.get("description", "No description."),
            "download": u["download"],
            "image": f"/public/images/{u['image']}" if u.get("image") else None
        }
        for u in uploads if u.get("status") == "approved"
    ]

    all_games = games + approved_uploads
    visible = [g for g in all_games if not g.get("hidden", False)]

    return jsonify({"games": visible})

@app.post("/api/purchase")
def purchase():
    data = request.get_json(force=True)

    email = data.get("email")
    games = data.get("games", [])

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    user = next((u for u in accounts["users"] if u.get("email") == email), None)

    if not user:
        return jsonify({"success": False}), 404

    user.setdefault("owned_games", [])
    for g in games:
        if g not in user["owned_games"]:
            user["owned_games"].append(g)

    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True, "owned_games": user["owned_games"]})

# ============================================================
#  DEVELOPER UPLOADS
# ============================================================

@app.post("/api/dev/upload")
@require_developer
def dev_upload():
    data = request.form.to_dict()
    build_file = request.files.get("build")
    image_file = request.files.get("image")

    required = ["id", "name", "price"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"success": False, "message": f"Missing: {', '.join(missing)}"}), 400

    if not build_file or build_file.filename == "":
        return jsonify({"success": False, "message": "Build required"}), 400

    if not allowed_file(build_file.filename):
        return jsonify({"success": False, "message": "Invalid build type"}), 400

    folder = data.get("folder") or data["id"]
    game_dir = os.path.join(PUBLIC_DIR, "games", folder)
    os.makedirs(game_dir, exist_ok=True)

    build_filename = secure_filename(build_file.filename)
    build_path = os.path.join(game_dir, build_filename)
    build_file.save(build_path)

    download_path = f"/public/games/{folder}/{build_filename}"

    image_filename = None
    if image_file and image_file.filename:
        if not image_file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            return jsonify({"success": False, "message": "Image must be PNG/JPG"}), 400

        image_filename = secure_filename(image_file.filename)
        image_dir = os.path.join(PUBLIC_DIR, "images")
        os.makedirs(image_dir, exist_ok=True)

        image_path = os.path.join(image_dir, image_filename)
        image_file.save(image_path)

    upload = {
        "id": data["id"],
        "name": data["name"],
        "price": data["price"],
        "developer_account": data.get("developer_account"),
        "folder": folder,
        "download": download_path,
        "image": image_filename,
        "developer_email": request.user["email"],
        "status": "pending",
        "timestamp": int(time.time())
    }

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    uploads["uploads"].append(upload)
    save_json(UPLOADS_PATH, uploads)

    return jsonify({"success": True})

# ============================================================
#  ADMIN UPLOAD APPROVAL
# ============================================================

@app.get("/api/admin/uploads")
@require_admin
def admin_get_uploads():
    return jsonify(load_json(UPLOADS_PATH, DEFAULT_UPLOADS))

@app.post("/api/admin/approve")
@require_admin
def admin_approve():
    data = request.get_json(force=True)
    upload_id = data.get("upload_id")

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    upload = next((u for u in uploads["uploads"] if u.get("id") == upload_id), None)
    if not upload:
        return jsonify({"error": "Not found"}), 404

    dev_email = upload.get("developer_email")
    dev_user = next((u for u in accounts["users"] if u.get("email") == dev_email), None)

    dev_stripe = dev_user.get("stripe_account_id") if dev_user else None

    games["games"].append({
        "id": upload["id"],
        "name": upload["name"],
        "price": upload["price"],
        "developer_email": dev_email,
        "developer_stripe_account": dev_stripe,
        "folder": upload["folder"],
        "download": upload["download"],
        "hidden": False,
        "featured": False
    })

    upload["status"] = "approved"

    save_json(GAMES_PATH, games)
    save_json(UPLOADS_PATH, uploads)

    return jsonify({"success": True})

# ============================================================
#  ADMIN ANALYTICS
# ============================================================

@app.get("/api/admin/analytics")
@require_admin
def admin_analytics():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    purchases = load_json(PURCHASES_PATH, DEFAULT_PURCHASES)
    payouts = load_json(PAYOUTS_PATH, DEFAULT_PAYOUTS)

    return jsonify({
        "total_users": len(accounts.get("users", [])),
        "total_developers": len([u for u in accounts.get("users", []) if u.get("role") == "developer"]),
        "total_games": len(games.get("games", [])),
        "total_sales": len(purchases.get("purchases", [])),
        "total_revenue_cents": sum(p.get("amount_total_cents", 0) for p in payouts.get("payouts", []))
    })

# ============================================================
#  ADMIN USER MANAGEMENT
# ============================================================

def _find_user_by_email(email):
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])
    user = next((u for u in users if u.get("email") == email), None)
    return accounts, users, user

@app.get("/api/admin/users")
@require_admin
def admin_get_users():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])

    # Ensure fields exist
    changed = False
    for u in users:
        if "status" not in u:
            u["status"] = "active"
            changed = True
        if "gamertag" not in u:
            u["gamertag"] = (u.get("email") or "").split("@")[0]
            changed = True

    if changed:
        save_json(ACCOUNTS_PATH, accounts)

    result = [
        {
            "email": u.get("email"),
            "gamertag": u.get("gamertag"),
            "role": u.get("role", "player"),
            "status": u.get("status", "active"),
            "company": u.get("company"),
            "owned_games": u.get("owned_games", [])
        }
        for u in users
    ]

    return jsonify({"users": result})

@app.get("/api/admin/user/<email>")
@require_admin
def admin_get_user(email):
    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    return jsonify({
        "email": user.get("email"),
        "gamertag": user.get("gamertag") or (user.get("email") or "").split("@")[0],
        "role": user.get("role", "player"),
        "status": user.get("status", "active"),
        "company": user.get("company"),
        "owned_games": user.get("owned_games", [])
    })

@app.post("/api/admin/user/promote")
@require_admin
def admin_user_promote():
    data = request.get_json(force=True)
    email = data.get("email")

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    role = user.get("role", "player")
    if role == "player":
        user["role"] = "developer"
    elif role == "developer":
        user["role"] = "admin"

    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})

@app.post("/api/admin/user/demote")
@require_admin
def admin_user_demote():
    data = request.get_json(force=True)
    email = data.get("email")

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    role = user.get("role", "player")
    if role == "admin":
        user["role"] = "developer"
    elif role == "developer":
        user["role"] = "player"

    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})

@app.post("/api/admin/user/suspend")
@require_admin
def admin_user_suspend():
    data = request.get_json(force=True)
    email = data.get("email")

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["status"] = "suspended"
    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})

@app.post("/api/admin/user/unsuspend")
@require_admin
def admin_user_unsuspend():
    data = request.get_json(force=True)
    email = data.get("email")

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["status"] = "active"
    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})

@app.post("/api/admin/user/ban")
@require_admin
def admin_user_ban():
    data = request.get_json(force=True)
    email = data.get("email")

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["status"] = "banned"
    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})

@app.post("/api/admin/user/unban")
@require_admin
def admin_user_unban():
    data = request.get_json(force=True)
    email = data.get("email")

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["status"] = "active"
    save_json(ACCOUNTS_PATH, accounts)
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
