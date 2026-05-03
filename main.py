import os
import json
import time
import stripe
import jwt
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
PAYOUTS_PATH = os.path.join(DATA_DIR, "payouts.json")
DEFAULT_PAYOUTS = {"payouts": []}

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
#  EMAIL HELPER
# ============================================================

EMAIL_USER = ADMIN_EMAIL  # codxgamessupport@gmail.com
EMAIL_PASS = os.getenv("EMAIL_PASS")  # Gmail App Password


def send_email(to, subject, html):
    if not EMAIL_PASS:
        print("EMAIL_PASS not set; skipping email send.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = to

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, [to], msg.as_string())
    except Exception as e:
        print(f"Error sending email to {to}: {e}")


# ============================================================
#  AUTO‑CREATE ADMIN ACCOUNT
# ============================================================

def ensure_admin_account():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    if "users" not in accounts or not isinstance(accounts["users"], list):
        accounts["users"] = []

    existing = next((u for u in accounts["users"] if u.get("email") == ADMIN_EMAIL), None)
    if not existing:
        admin_user = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "role": "admin",
            "gamertag": "CodeXAdmin",
            "status": "active",
            "owned_games": [],
            "company": "Code‑X"
        }
        accounts["users"].append(admin_user)
        save_json(ACCOUNTS_PATH, accounts)
    else:
        changed = False
        if "status" not in existing:
            existing["status"] = "active"
            changed = True
        if "gamertag" not in existing:
            existing["gamertag"] = "CodeXAdmin"
            changed = True
        if changed:
            save_json(ACCOUNTS_PATH, accounts)


ensure_admin_account()


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
    gamertag = (data.get("gamertag") or "").strip()
    role = "player"

    if not email or not password or not gamertag:
        return jsonify({"success": False, "message": "Email, password, and gamertag required"}), 400

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])

    if any(u.get("email") == email for u in users):
        return jsonify({"success": False, "message": "Account exists"}), 400

    if any((u.get("gamertag") or "").lower() == gamertag.lower() for u in users):
        return jsonify({"success": False, "message": "Gamertag already taken"}), 400

    if email == ADMIN_EMAIL:
        role = "admin"

    user = {
        "email": email,
        "password": password,
        "role": role,
        "gamertag": gamertag,
        "status": "active",
        "owned_games": []
    }

    accounts.setdefault("users", [])
    accounts["users"].append(user)
    save_json(ACCOUNTS_PATH, accounts)

    # EMAIL: user created account
    try:
        send_email(
            email,
            "Welcome to Code‑X!",
            """
            <h2>Welcome to Code‑X!</h2>
            <p>Your account has been created successfully.</p>
            <p>You can now log in and start exploring the platform.</p>
            """
        )
    except Exception as e:
        print("Error sending welcome email:", e)

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
    users = accounts.get("users", [])
    user = next((u for u in users if u.get("email") == email), None)

    if not user or user.get("password") != password:
        return jsonify({"success": False, "message": "Invalid login"}), 401

    if "status" not in user:
        user["status"] = "active"
        save_json(ACCOUNTS_PATH, accounts)
    if "gamertag" not in user:
        user["gamertag"] = email.split("@")[0]
        save_json(ACCOUNTS_PATH, accounts)

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
#  DEVELOPER VERIFICATION (JSONBIN)
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

    # EMAIL: developer submitted application
    try:
        send_email(
            email,
            "Developer Application Received",
            f"""
            <h2>Developer Application Received</h2>
            <p>We’ve received your developer application for <strong>{company}</strong>.</p>
            <p>You’ll get another email once it has been reviewed.</p>
            """
        )
    except Exception as e:
        print("Error sending dev application received email:", e)

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

    # EMAIL: developer approved
    try:
        send_email(
            email,
            "Developer Application Approved",
            f"""
            <h2>Developer Application Approved</h2>
            <p>Congratulations!</p>
            <p>Your developer application for <strong>{app_entry.get("company", "your company")}</strong> has been approved.</p>
            <p>You can now log in and access the Code‑X Developer tools.</p>
            """
        )
    except Exception as e:
        print("Error sending dev approved email:", e)

    return jsonify({"success": True})


@app.post("/api/dev/stripe/account")
@require_developer
def dev_save_stripe_account():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    stripe_account_id = (data.get("stripe_account_id") or "").strip()
    if not stripe_account_id:
        return jsonify({"success": False, "message": "stripe_account_id required"}), 400

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])
    email = request.user["email"]

    user = next((u for u in users if u.get("email") == email), None)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["stripe_account_id"] = stripe_account_id
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
            "gamertag": u.get("gamertag"),
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
    games_data = load_json(GAMES_PATH, DEFAULT_GAMES)
    base_games = games_data.get("games", [])

    uploads_data = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    uploads = uploads_data.get("uploads", [])

    approved_uploads = [
        u for u in uploads
        if u.get("status") == "approved"
    ]

    upload_games = []
    for u in approved_uploads:
        upload_games.append({
            "id": u["id"],
            "name": u["name"],
            "price": u["price"],
            "description": u.get("description", "No description provided."),
            "download": u["download"],
            "image": f"/public/images/{u['image']}" if u.get("image") else None
        })

    all_games = base_games + upload_games

    visible_games = [
        g for g in all_games
        if not g.get("hidden", False)
    ]

    return jsonify({"games": visible_games})


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

    if not email or not game_id:
        return jsonify({"error": "email and game_id are required"}), 400

    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    game_list = games.get("games", [])
    game = next((g for g in game_list if str(g.get("id")) == str(game_id)), None)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    try:
        price = float(game.get("price", 0))
    except:
        return jsonify({"error": "Invalid game price"}), 400

    price_cents = int(price * 100)
    platform_fee_cents = int(price_cents * (PLATFORM_FEE_PERCENT / 100.0))

    dev_stripe = game.get("developer_stripe_account")
    if not dev_stripe:
        return jsonify({"error": "Developer has no Stripe account connected"}), 400

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": game["name"]},
                    "unit_amount": price_cents
                },
                "quantity": 1
            }],
            success_url="https://codexgames.com/success",
            cancel_url="https://codexgames.com/cancel",
            payment_intent_data={
                "application_fee_amount": platform_fee_cents,
                "transfer_data": {
                    "destination": dev_stripe
                }
            },
            metadata={
                "email": email,
                "game_id": str(game_id)
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

        try:
            amount_total = session.get("amount_total") or 0
            payment_intent_id = session.get("payment_intent")

            pi = stripe.PaymentIntent.retrieve(payment_intent_id)
            app_fee = pi.get("application_fee_amount") or 0
            dev_amount = amount_total - app_fee

            games = load_json(GAMES_PATH, DEFAULT_GAMES)
            game_list = games.get("games", [])
            game = next((g for g in game_list if str(g.get("id")) == str(game_id)), None)

            dev_email = game.get("developer_email") if game else None

            payouts = load_json(PAYOUTS_PATH, DEFAULT_PAYOUTS)
            payouts.setdefault("payouts", [])
            payouts["payouts"].append({
                "payment_intent_id": payment_intent_id,
                "game_id": game_id,
                "buyer_email": email,
                "developer_email": dev_email,
                "amount_total_cents": amount_total,
                "platform_fee_cents": app_fee,
                "developer_amount_cents": dev_amount,
                "timestamp": int(time.time())
            })
            save_json(PAYOUTS_PATH, payouts)
        except Exception as e:
            print("Error logging payout:", e)

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

    build_file = request.files.get("build")
    image_file = request.files.get("image")

    required = ["id", "name", "price"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({
            "success": False,
            "message": f"Missing fields: {', '.join(missing)}"
        }), 400

    if not build_file or build_file.filename == "":
        return jsonify({
            "success": False,
            "message": "Build file is required."
        }), 400

    if not allowed_file(build_file.filename):
        return jsonify({
            "success": False,
            "message": "Invalid build file type. Use ZIP or EXE."
        }), 400

    build_filename = secure_filename(build_file.filename)
    folder_name = data.get("folder") or data["id"]
    game_dir = os.path.join(PUBLIC_DIR, "games", folder_name)
    os.makedirs(game_dir, exist_ok=True)

    build_path = os.path.join(game_dir, build_filename)
    build_file.save(build_path)

    download_path = f"/public/games/{folder_name}/{build_filename}"

    image_filename = None
    if image_file and image_file.filename:
        if not image_file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
            return jsonify({"success": False, "message": "Image must be PNG or JPG"}), 400

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
        "folder": folder_name,
        "download": download_path,
        "image": image_filename,
        "developer_email": request.user["email"],
        "status": "pending",
        "timestamp": int(time.time())
    }

    uploads = load_json(UPLOADS_PATH, DEFAULT_UPLOADS)
    uploads.setdefault("uploads", [])
    uploads["uploads"].append(upload)
    save_json(UPLOADS_PATH, uploads)

    # EMAIL: developer uploaded game
    try:
        send_email(
            request.user["email"],
            "Game Upload Received",
            f"""
            <h2>Game Upload Received</h2>
            <p>Your game <strong>{data["name"]}</strong> has been uploaded and is now pending review.</p>
            <p>You’ll receive another email once it has been approved.</p>
            """
        )
    except Exception as e:
        print("Error sending game upload received email:", e)

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
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    upload = next((u for u in uploads.get("uploads", []) if u.get("id") == upload_id), None)
    if not upload:
        return jsonify({"error": "Upload not found"}), 404

    dev_email = upload.get("developer_email")
    dev_user = next((u for u in accounts.get("users", []) if u.get("email") == dev_email), None)

    if not dev_user:
        return jsonify({"error": "Developer not found"}), 404

    dev_stripe = dev_user.get("stripe_account_id")

    games.setdefault("games", [])
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

    # EMAIL: game approved
    try:
        if dev_email:
            send_email(
                dev_email,
                "Your Game Has Been Approved",
                f"""
                <h2>Your Game Is Now Live!</h2>
                <p>Your game <strong>{upload.get("name")}</strong> has been approved and added to the Code‑X Store.</p>
                <p>Players can now see and download it.</p>
                """
            )
    except Exception as e:
        print("Error sending game approved email:", e)

    return jsonify({"success": True})


@app.get("/api/admin/analytics")
@require_admin
def admin_analytics():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    purchases = load_json(PURCHASES_PATH, DEFAULT_PURCHASES)
    payouts = load_json(PAYOUTS_PATH, DEFAULT_PAYOUTS)

    users = accounts.get("users", [])
    total_users = len(users)
    total_devs = len([u for u in users if u.get("role") == "developer"])
    total_games = len(games.get("games", []))
    total_sales = len(purchases.get("purchases", []))

    total_revenue = sum(p.get("amount_total_cents", 0) for p in payouts.get("payouts", []))

    return jsonify({
        "total_users": total_users,
        "total_developers": total_devs,
        "total_games": total_games,
        "total_sales": total_sales,
        "total_revenue_cents": total_revenue
    })


# ============================================================
#  ADMIN USER MANAGEMENT
# ============================================================

@app.get("/api/admin/users")
@require_admin
def admin_get_users():
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])

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

    result = []
    for u in users:
        result.append({
            "email": u.get("email"),
            "gamertag": u.get("gamertag"),
            "role": u.get("role", "player"),
            "status": u.get("status", "active"),
            "company": u.get("company"),
            "owned_games": u.get("owned_games", [])
        })

    return jsonify({"users": result})


@app.get("/api/admin/user/<email>")
@require_admin
def admin_get_user(email):
    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    result = {
        "email": user.get("email"),
        "gamertag": user.get("gamertag") or (user.get("email") or "").split("@")[0],
        "role": user.get("role", "player"),
        "status": user.get("status", "active"),
        "company": user.get("company"),
        "owned_games": user.get("owned_games", [])
    }
    return jsonify(result)


def _find_user_by_email(email):
    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    users = accounts.get("users", [])
    user = next((u for u in users if u.get("email") == email), None)
    return accounts, users, user


@app.post("/api/admin/user/promote")
@require_admin
def admin_user_promote():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

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
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

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
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["status"] = "suspended"
    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})


@app.post("/api/admin/user/unsuspend")
@require_admin
def admin_user_unsuspend():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["status"] = "active"
    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})


@app.post("/api/admin/user/ban")
@require_admin
def admin_user_ban():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

    accounts, users, user = _find_user_by_email(email)
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    user["status"] = "banned"
    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True})


@app.post("/api/admin/user/unban")
@require_admin
def admin_user_unban():
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400

    email = data.get("email")
    if not email:
        return jsonify({"success": False, "message": "email required"}), 400

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
