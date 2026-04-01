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
ADMIN_PASSWORD = "Codexgames1828"  # change in real use

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

DEFAULT_ACCOUNTS = {"users": []}
DEFAULT_GAMES = {"games": []}
DEFAULT_PURCHASES = {"purchases": []}
DEFAULT_MESSAGES = {"messages": []}
DEFAULT_UPLOADS = {"uploads": []}
DEFAULT_DEV_APPS = {"applications": []}

# ============================================================
#  JSONBIN CONFIG (DEVELOPER APPLICATIONS ONLY)
# ============================================================

JSONBIN_URL = "https://api.jsonbin.io/v3/b/69cb36c436566621a8642602"
JSONBIN_KEY = "$2a$10$JMbtIt49UIA0cZntnOWtfu695M3OqQ50NY5qUx0VgbAnvndW74beC"


def load_dev_apps():
    """
    Load developer applications from JSONBin.
    Structure in bin:
    {
      "applications": [ ... ]
    }
    """
    headers = {"X-Master-Key": JSONBIN_KEY}
    r = requests.get(JSONBIN_URL, headers=headers)
    r.raise_for_status()
    data = r.json()
    record = data.get("record") or {}
    apps = record.get("applications")
    if not isinstance(apps, list):
        apps = []
    return apps


def save_dev_apps(apps):
    """
    Save developer applications back to JSONBin.
    """
    headers = {"X-Master-Key": JSONBIN_KEY}
    body = {"applications": apps}
    r = requests.put(JSONBIN_URL, json=body, headers=headers)
    r.raise_for_status()


# ============================================================
#  JSON HELPERS (LOCAL FILES FOR EVERYTHING ELSE)
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
            "owned_games": [],
            "company": "Code‑X"
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
    role = "player"

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
    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "email": user["email"],
            "role": user.get("role", "player"),
            "company": user.get("company"),
            "owned_games": user.get("owned_games", [])
        }
    })


@app.get("/api/auth/me")
@require_auth
def auth_me():
    return jsonify(request.user)


# ============================================================
#  DEVELOPER VERIFICATION (NOW USING JSONBIN)
# ============================================================
@app.post("/api/dev/apply")
@require_auth
def apply_developer():
    print("HIT /api/dev/apply")

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = request.user["email"]
    company = (data.get("company") or "").strip()
    website = (data.get("website") or "").strip()
    description = (data.get("description") or "").strip()

    if not company:
        return jsonify({"success": False, "message": "Company name required"}), 400

    try:
        apps = load_dev_apps()
    except Exception as e:
        print("Error loading dev apps from JSONBin:", e)
        return jsonify({"success": False, "message": "Storage error"}), 500

    existing = next((a for a in apps if a.get("email") == email and a.get("status") == "pending"), None)
    if existing:
        return jsonify({"success": False, "message": "Application already pending"}), 400

    apps.append({
        "email": email,
        "company": company,
        "website": website,
        "description": description,
        "status": "pending",
        "timestamp": int(time.time())
    })

    try:
        save_dev_apps(apps)
    except Exception as e:
        print("Error saving dev apps to JSONBin:", e)
        return jsonify({"success": False, "message": "Storage error"}), 500

    return jsonify({"success": True})



@app.get("/api/admin/dev-applications")
@require_admin
def admin_dev_apps():
    try:
        apps = load_dev_apps()
    except Exception as e:
        print("Error loading dev apps from JSONBin:", e)
        return jsonify({"applications": []}), 500

    return jsonify({"applications": apps})


@app.post("/api/admin/dev-approve")
@require_admin
def admin_dev_approve():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

    try:
        apps = load_dev_apps()
    except Exception as e:
        print("Error loading dev apps from JSONBin:", e)
        return jsonify({"success": False, "message": "Storage error"}), 500

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    app_entry = next((a for a in apps if a.get("email") == email), None)
    user = next((u for u in accounts.get("users", []) if u.get("email") == email), None)

    if not app_entry or not user:
        return jsonify({"success": False, "message": "Application or user not found"}), 404

    app_entry["status"] = "approved"
    user["role"] = "developer"
    user["company"] = app_entry.get("company")

    try:
        save_dev_apps(apps)
    except Exception as e:
        print("Error saving dev apps to JSONBin:", e)
        return jsonify({"success": False, "message": "Storage error"}), 500

    save_json(ACCOUNTS_PATH, accounts)

    return jsonify({"success": True})


@app.post("/api/admin/dev-reject")
@require_admin
def admin_dev_reject():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

    try:
        apps = load_dev_apps()
    except Exception as e:
        print("Error loading dev apps from JSONBin:", e)
        return jsonify({"success": False, "message": "Storage error"}), 500

    app_entry = next((a for a in apps if a.get("email") == email), None)

    if not app_entry:
        return jsonify({"success": False, "message": "Application not found"}), 404

    app_entry["status"] = "rejected"

    try:
        save_dev_apps(apps)
    except Exception as e:
        print("Error saving dev apps to JSONBin:", e)
        return jsonify({"success": False, "message": "Storage error"}), 500

    return jsonify({"success": True})


@app.get("/api/admin/developers")
@require_admin
def admin_developers():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    devs = [
        {
            "email": u["email"],
            "company": u.get("company", "Unknown")
        }
        for u in accounts.get("users", [])
        if u.get("role") == "developer"
    ]
    return jsonify({"developers": devs})


# ============================================================
#  STORE + OWNED + PURCHASE + STORE MANAGEMENT (ADMIN)
# ============================================================

@app.get("/api/store")
def store():
    games = load_json(GAMES_PATH, DEFAULT_GAMES)

    visible_games = [
        g for g in games.get("games", [])
        if not g.get("hidden", False)
    ]

    return jsonify({"games": visible_games})


@app.get("/api/user/owned/<email>")
def get_owned(email):
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])
    if not isinstance(users, list):
        users = []

    user = next((u for u in users if u.get("email") == email), None)
    if not user:
        return jsonify({"owned_games": []})

    owned = user.get("owned_games", [])
    if not isinstance(owned, list):
        owned = []

    return jsonify({"owned_games": owned})


@app.post("/api/purchase")
def purchase():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    games = data.get("games", [])

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])
    user = next((u for u in users if u.get("email") == email), None)

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    if "owned_games" not in user or not isinstance(user["owned_games"], list):
        user["owned_games"] = []

    for g in games:
        if g not in user["owned_games"]:
            user["owned_games"].append(g)

    save_json(ACCOUNTS_PATH, accounts)

    return jsonify({"success": True, "owned_games": user["owned_games"]})


@app.get("/api/admin/store/games")
@require_admin
def admin_store_games():
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    return jsonify(games)


@app.put("/api/admin/store/update/<folder>")
@require_admin
def admin_update_game(folder):
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    game_list = games.get("games", [])

    game = next((g for g in game_list if g.get("folder") == folder), None)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    if "name" in data:
        game["name"] = data["name"]

    if "price" in data:
        try:
            game["price"] = float(data["price"])
        except:
            return jsonify({"error": "Invalid price"}), 400

    if "description" in data:
        game["description"] = data["description"]

    save_json(GAMES_PATH, games)

    return jsonify({"success": True, "updated": game})


@app.post("/api/admin/store/feature/<game_id>")
@require_admin
def admin_feature_game(game_id):
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    game_list = games.get("games", [])

    game = next((g for g in game_list if g["id"] == game_id), None)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    game["featured"] = not game.get("featured", False)

    save_json(GAMES_PATH, games)
    return jsonify({"success": True, "featured": game["featured"]})


@app.post("/api/admin/store/hide/<game_id>")
@require_admin
def admin_hide_game(game_id):
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    game_list = games.get("games", [])

    game = next((g for g in game_list if g["id"] == game_id), None)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    game["hidden"] = not game.get("hidden", False)

    save_json(GAMES_PATH, games)
    return jsonify({"success": True, "hidden": game["hidden"]})


# ============================================================
#  STRIPE CHECKOUT + WEBHOOK
# ============================================================

@app.post("/create-checkout-session")
def create_checkout_session():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    email = data.get("email")
    game_id = data.get("game_id")
    price = data.get("price")

    if not email or not game_id or price is None:
        return jsonify({"error": "email, game_id, and price are required"}), 400

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": game_id},
                    "unit_amount": int(float(price) * 100)
                },
                "quantity": 1
            }],
            success_url="https://codexgames.com/success",
            cancel_url="https://codexgames.com/cancel",
            metadata={
                "email": email,
                "game_id": game_id
            }
        )
        return jsonify({"url": session.url})
    except Exception as e:
        print("Stripe error:", e)
        return jsonify({"error": "Stripe session failed"}), 400


@app.post("/stripe-webhook")
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print("Webhook signature error:", e)
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session["metadata"].get("email")
        game_id = session["metadata"].get("game_id")

        if email and game_id:
            accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
            users = accounts.get("users", [])
            user = next((u for u in users if u.get("email") == email), None)

            if user:
                if "owned_games" not in user or not isinstance(user["owned_games"], list):
                    user["owned_games"] = []
                if game_id not in user["owned_games"]:
                    user["owned_games"].append(game_id)
                save_json(ACCOUNTS_PATH, accounts)

    return "", 200


# ============================================================
#  DEVELOPER UPLOAD (REAL FILE + METADATA)
# ============================================================

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
#  ADMIN ROUTES (UPLOAD APPROVAL)
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
