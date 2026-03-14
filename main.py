import os
import json
import time
import stripe
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ============================================================
#  STRIPE CONFIG (PLACEHOLDERS — REPLACE WITH REAL KEYS)
# ============================================================

STRIPE_SECRET_KEY = "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"
STRIPE_WEBHOOK_SECRET = "YOUR_STRIPE_WEBHOOK_SECRET"

stripe.api_key = STRIPE_SECRET_KEY

# Platform fee (percentage you keep)
PLATFORM_FEE_PERCENT = 20  # Example: 20% to CodeX, 80% to developer


# ============================================================
#  INTERNAL JSON STORAGE
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

DEFAULT_ACCOUNTS = {"users": []}

DEFAULT_GAMES = {
    "games": [
        {
            "id": "example_game",
            "name": "Example Game",
            "price": 999,
            "developer_account": None,
            "folder": "ExampleGame",
            "download": "/public/games/ExampleGame.zip"
        },
        {
            "id": "space_runner",
            "name": "Space Runner",
            "price": 499,
            "developer_account": None,
            "folder": "SpaceRunner",
            "download": "/public/games/SpaceRunner.zip"
        },
        {
            "id": "kings_castle",
            "name": "Kings Castle",
            "price": 0,
            "developer_account": None,
            "folder": "KingsCastle",
            "download": "/public/games/KingsCastle.zip"
        }
    ]
}

DEFAULT_PURCHASES = {"purchases": []}
DEFAULT_MESSAGES = {"messages": []}


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
#  FLASK APP
# ============================================================

app = Flask(__name__)
CORS(app)


# ============================================================
#  HEALTH
# ============================================================

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "message": "CodeX backend running"})


# ============================================================
#  AUTH
# ============================================================

@app.route("/api/auth/create", methods=["POST"])
def create_account():
    data = request.get_json(force=True)
    email = data.get("email", "").lower().strip()
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required."}), 400

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)

    if any(u["email"].lower() == email for u in accounts["users"]):
        return jsonify({"success": False, "message": "Account already exists."}), 400

    accounts["users"].append({
        "email": email,
        "password": password,
        "owned_games": []
    })

    save_json(ACCOUNTS_PATH, accounts)
    return jsonify({"success": True, "message": "Account created."})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = data.get("email", "").lower().strip()
    password = data.get("password")

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    user = next((u for u in accounts["users"] if u["email"].lower() == email), None)

    if not user or user["password"] != password:
        return jsonify({"success": False, "message": "Invalid login."}), 401

    return jsonify({"success": True, "user": user})


# ============================================================
#  STORE
# ============================================================

@app.route("/api/store")
def store():
    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    return jsonify({"games": games["games"]})


# ============================================================
#  OWNED GAMES
# ============================================================

@app.route("/api/user/owned")
def owned_games():
    email = request.args.get("email", "").lower().strip()
    if not email:
        return jsonify({"success": False, "message": "Email required"}), 400

    accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
    user = next((u for u in accounts["users"] if u["email"].lower() == email), None)

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    return jsonify({"success": True, "owned_games": user.get("owned_games", [])})


# ============================================================
#  STRIPE CHECKOUT SESSION
# ============================================================

@app.route("/api/create-checkout-session", methods=["POST"])
def create_checkout_session():
    data = request.get_json(force=True)
    email = data.get("email", "").lower().strip()
    game_id = data.get("game_id")

    games = load_json(GAMES_PATH, DEFAULT_GAMES)
    game = next((g for g in games["games"] if g["id"] == game_id), None)

    if not game:
        return jsonify({"success": False, "message": "Game not found"}), 404

    # Developer Stripe account (None = platform keeps 100%)
    developer_account = game.get("developer_account")

    # Platform fee calculation
    platform_fee = int(game["price"] * (PLATFORM_FEE_PERCENT / 100))

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": game["name"]},
                "unit_amount": game["price"],
            },
            "quantity": 1,
        }],
        success_url="https://your-launcher-success-url",
        cancel_url="https://your-launcher-cancel-url",
        metadata={
            "email": email,
            "game_id": game_id
        },
        payment_intent_data={
            "application_fee_amount": platform_fee,
            "transfer_data": {
                "destination": developer_account
            } if developer_account else None
        }
    )

    return jsonify({"url": session.url})


# ============================================================
#  STRIPE WEBHOOK
# ============================================================

@app.route("/api/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        return "", 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session["metadata"]["email"]
        game_id = session["metadata"]["game_id"]

        accounts = load_json(ACCOUNTS_PATH, DEFAULT_ACCOUNTS)
        user = next((u for u in accounts["users"] if u["email"].lower() == email), None)

        if user:
            owned = set(user.get("owned_games", []))
            owned.add(game_id)
            user["owned_games"] = sorted(list(owned))
            save_json(ACCOUNTS_PATH, accounts)

    return "", 200


# ============================================================
#  MESSAGES
# ============================================================

@app.route("/api/messages", methods=["POST"])
def messages():
    data = request.get_json(force=True)
    name = data.get("name", "")
    email = data.get("email", "")
    message = data.get("message", "")

    if not message:
        return jsonify({"success": False, "message": "Message required"}), 400

    messages = load_json(MESSAGES_PATH, DEFAULT_MESSAGES)
    messages["messages"].append({
        "name": name,
        "email": email,
        "message": message,
        "timestamp": int(time.time())
    })

    save_json(MESSAGES_PATH, messages)
    return jsonify({"success": True})


# ============================================================
#  STATIC FILES
# ============================================================

@app.route("/public/<path:filename>")
def public_files(filename):
    return send_from_directory(PUBLIC_DIR, filename)


# ============================================================
#  RUN SERVER
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)



