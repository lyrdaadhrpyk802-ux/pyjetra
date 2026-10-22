"""Probe which Jetra Bot API methods actually exist."""
import requests
import json

BOT_TOKEN = "1780246392:n-vWgk3R4nE1EAv6hMxTfjYQ0EX1uKSHxuu"
BASE_URL = f"https://jetra.ir/bot{BOT_TOKEN}/"

# Methods to probe (all of them)
methods_to_test = [
    # These we KNOW exist (from docs) — will show as reference
    ("getMe", {}),
    ("getMyCommands", {}),
    # --- SUSPICIOUS: undocumented in public docs ---
    ("forwardMessage", {"chat_id": 1, "from_chat_id": 1, "message_id": 1}),
    ("copyMessage", {"chat_id": 1, "from_chat_id": 1, "message_id": 1}),
    ("pinChatMessage", {"chat_id": 1, "message_id": 1}),
    ("unpinChatMessage", {"chat_id": 1, "message_id": 1}),
    ("sendPoll", {"chat_id": 1, "question": "test?", "options": ["a", "b"]}),
    ("leaveChat", {"chat_id": 1}),
    ("getChatMember", {"chat_id": 1, "user_id": 1}),
    ("getChatMemberCount", {"chat_id": 1}),
    ("sendChatAction", {"chat_id": 1, "action": "typing"}),
    ("sendMediaGroup", {"chat_id": 1, "media": []}),
    ("getUserProfilePhotos", {"user_id": 1}),
    ("sendDice", {"chat_id": 1}),
    ("sendGame", {"chat_id": 1, "game_short_name": "test"}),
    ("answerInlineQuery", {"inline_query_id": "1", "results": []}),
    ("setChatTitle", {"chat_id": 1, "title": "test"}),
    ("setChatDescription", {"chat_id": 1, "description": "test"}),
    ("exportChatInviteLink", {"chat_id": 1}),
    ("approveChatJoinRequest", {"chat_id": 1, "user_id": 1}),
    # --- These we ADDED (also undocumented) ---
    ("banChatMember", {"chat_id": 1, "user_id": 1}),
    ("unbanChatMember", {"chat_id": 1, "user_id": 1}),
    ("restrictChatMember", {"chat_id": 1, "user_id": 1, "permissions": {}}),
    ("promoteChatMember", {"chat_id": 1, "user_id": 1}),
    ("getChat", {"chat_id": 1}),
    ("getChatAdministrators", {"chat_id": 1}),
]

print(f"{'Method':<28} {'Status':<12} {'Result / Error'}")
print("=" * 80)

for method, params in methods_to_test:
    url = BASE_URL + method
    try:
        r = requests.post(url, json=params, timeout=15)
        try:
            data = r.json()
        except Exception:
            print(f"{method:<28} {'HTTP ' + str(r.status_code):<12} {r.text[:60]}")
            continue
        
        if data.get("ok") is True:
            print(f"{method:<28} {'✅ WORKS':<12} result={str(data.get('result'))[:40]}")
        else:
            desc = data.get("description", "")
            # If the method doesn't exist, Jetra returns 404-like error.
            # If it exists but params are wrong, it returns a specific error.
            if any(word in desc.lower() for word in ["not found", "unknown method", "invalid method", "404"]):
                print(f"{method:<28} {'❌ MISSING':<12} {desc[:40]}")
            else:
                print(f"{method:<28} {'⚠️ EXISTS':<12} (params wrong) {desc[:40]}")
    except Exception as e:
        print(f"{method:<28} {'❌ ERROR':<12} {str(e)[:40]}")

print("=" * 80)
