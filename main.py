import os
import requests
import json
from datetime import datetime, timedelta
from discord_interactions import InteractionType, InteractionResponseType, verify_key_decorator, InteractionResponse

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
CLASH_API_TOKEN = os.environ["CLASH_API_TOKEN"]

API_BASE = "https://proxy.royaleapi.dev/v1/"
headers = {"Authorization": f"Bearer {CLASH_API_TOKEN}"}

# Local player data store
DATA_FILE = "player_data.json"
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_player_data(tag: str):
    tag = tag.strip("#").upper()
    r = requests.get(f"{API_BASE}/players/%23{tag}", headers=headers)
    return r.json() if r.status_code == 200 else None

def get_account_age(badges):
    for b in badges:
        if b["name"] == "YearsPlayed":
            # Each level = 1 year; progress ~ days since level
            years = b["level"]
            days_into = b.get("progress", 0)
            return f"{years} years, {days_into} days"
    return "Unknown"

def get_winrate(data):
    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    total = wins + losses
    return round((wins / total) * 100, 2) if total > 0 else 0

def make_stats_message(data):
    deck = [c["name"] for c in data.get("currentDeck", [])]
    trophies = data["trophies"]
    arena = data["arena"]["name"]
    winrate = get_winrate(data)
    account_age = get_account_age(data.get("badges", []))
    name = data["name"]
    tag = data["tag"]

    msg = f"**{name}** ({tag})\n"
    msg += f"🏆 **Trophies:** {trophies}\n"
    msg += f"🎖 **Arena:** {arena}\n"
    msg += f"⚔️ **Winrate:** {winrate}%\n"
    msg += f"📆 **Account Age:** {account_age}\n"
    msg += "\n🃏 **Deck:** " + ", ".join(deck) if deck else "\n🃏 Deck: Unknown"
    return msg


# ---- Discord Interaction handler ----
@verify_key_decorator(DISCORD_PUBLIC_KEY)
def handler(request):
    body = request.json
    if body["type"] == InteractionType.PING:
        return {"type": InteractionResponseType.PONG}

    data = load_data()
    user_id = str(body["member"]["user"]["id"])
    command = body["data"]["name"]
    options = body["data"].get("options", [])

    if command == "register":
        player_tag = options[0]["value"]
        data[user_id] = {"tag": player_tag, "history": {}}
        save_data(data)
        content = f"✅ Registered `{player_tag}` to your account."

    elif command == "unlink":
        if user_id in data:
            del data[user_id]
            save_data(data)
            content = "🗑️ Unlinked your account."
        else:
            content = "⚠️ You don't have an account linked."

    elif command == "stats":
        target = options[0]["value"] if options else None
        tag = None
        if target:
            if target.startswith("<@") and target.endswith(">"):
                user_id_target = target.strip("<@>")
                tag = data.get(user_id_target, {}).get("tag")
            else:
                tag = target
        else:
            tag = data.get(user_id, {}).get("tag")

        if not tag:
            content = "⚠️ No linked account or invalid player tag."
        else:
            player_data = get_player_data(tag)
            content = make_stats_message(player_data) if player_data else "❌ Could not fetch player data."

    elif command == "gains":
        if user_id not in data or "tag" not in data[user_id]:
            content = "⚠️ You need to `/register` first."
        else:
            tag = data[user_id]["tag"]
            player_data = get_player_data(tag)
            if not player_data:
                content = "❌ Could not fetch player data."
            else:
                trophies = player_data["trophies"]
                winrate = get_winrate(player_data)
                prev = data[user_id].get("history", {})

                diff = trophies - prev.get("trophies", trophies)
                wdiff = round(winrate - prev.get("winrate", winrate), 2)

                data[user_id]["history"] = {"trophies": trophies, "winrate": winrate}
                save_data(data)

                content = f"🏆 Trophies: {trophies} ({'+' if diff>=0 else ''}{diff})\n⚔️ Winrate change: {'+' if wdiff>=0 else ''}{wdiff}%"

    else:
        content = "Unknown command."

    return {
        "type": InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
        "data": {"content": content}
    }
