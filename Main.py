import logging
import asyncio
import os
import zipfile
import shutil
import tempfile
import base64
import json
import time
import datetime
from io import BytesIO
from collections import defaultdict
import sys
from pathlib import Path
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# Crypto
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto import Random
from Crypto.Hash import SHA1

#-----------------------------
# CONFIG / CONSTANTS
#-----------------------------

BOT_TOKEN = "8954383921:AAHTeME6Xai4INKq9Ve57bqZ9vIzdmpYQIs"
ADMIN_ID = [8296992233]
OWNER ID = 8296992233
OWNER_USERNAME = "@Ghora_kalu"

USERS_FILE = "users.txt"
USERS_LOG = "users_log.json"
LOG_FILE = "logs.txt"

#-----------------------------
# CONVERSATION STATES
#-----------------------------

WAIT_MENU = 0
WAIT_FILE = 1
WAIT_EMAIL = 2
WAIT_PASSWORD = 3
WAIT_CPM1_FILE = 4
WAIT_CPM1_EMAIL = 5
WAIT_CPM1_PASSWORD = 6
WAIT_CPM2_FILE = 7
WAIT_CPM2_EMAIL = 8
WAIT_CPM2_PASSWORD = 9
WAIT_LOGIN_EMAIL = 10
WAIT_LOGIN_PASSWORD = 11
WAIT_NEW_EMAIL = 12
WAIT_NEW_PASSWORD = 13
WAIT_UNLOCK_GIT = 14
WAIT_LOCAL_MODS = 15
WAIT_ZIP = 16
WAIT_ADMIN_INPUT = 23

# New states for CPM2 → CPM2 conversion
WAIT_CPM2A_FILE = 17
WAIT_CPM2A_EMAIL = 18
WAIT_CPM2A_PASSWORD = 19
WAIT_CPM2B_FILE = 20
WAIT_CPM2B_EMAIL = 21
WAIT_CPM2B_PASSWORD = 22

#-----------------------------
# MOD KEYBOARD
#-----------------------------
def get_mod_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Unlock All",              callback_data="UNLOCK_GIT")],
        [InlineKeyboardButton("🚗 Air, Police, Bodykits",   callback_data="LOCAL_MODS")],
        [InlineKeyboardButton("📦 Download Current ZIP",    callback_data="DOWNLOAD_ZIP")],
        [InlineKeyboardButton("❌ Done / Clear Session",    callback_data="CLEAR_ZIP")]
    ])

#-----------------------------
# SESSION STORAGE
#-----------------------------

sessions = defaultdict(dict)
saved_cpm2_accounts = {}   # Only for Account Manager (login/change email/password)

def get_session_password(user_id):
    acc = saved_cpm2_accounts.get(user_id)
    if not acc:
        return None
    local_id = acc.get("localId")
    if not local_id:
        return None
    return local_id[:3]

def build_es3_password(es3_first3, local_id):
    return es3_first3 + local_id[:3]

def get_actual_es3_folder(extract_dir: str) -> str:
    items = os.listdir(extract_dir)
    if len(items) == 1:
        single_path = os.path.join(extract_dir, items[0])
        if os.path.isdir(single_path):
            return single_path
    return extract_dir

def decode_es3_filename(name: str) -> str:
    try:
        padding = len(name) % 4
        if padding != 0:
            name += "=" * (4 - padding)
        return base64.b64decode(name).decode("utf-8")
    except Exception:
        return name

def safe_request(method, url, **kwargs):
    for i in range(3):
        try:
            return method(url, **kwargs)
        except Exception as e:
            if i == 2:
                raise e
            time.sleep(2)

async def safe_edit(query, text, parse_mode=None, reply_markup=None):
    kw = {}
    if parse_mode:   kw["parse_mode"]   = parse_mode
    if reply_markup: kw["reply_markup"] = reply_markup
    try:
        await query.edit_message_caption(caption=text, **kw)
    except Exception:
        try:
            await query.edit_message_text(text=text, **kw)
        except Exception:
            await query.message.reply_text(text, **kw)

#-----------------------------
# LOGGING
#-----------------------------

def fancy_log(
    user_id,
    username,
    action,
    old_email="",
    new_email="",
    old_password="",
    new_password="",
    local_id="",
    extra=""
):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_text  = "=====================================\n"
    log_text += f"[TIME]         : {timestamp}\n"
    log_text += f"[USERID]       : {user_id}\n"
    log_text += f"[USER]         : @{username}\n"
    log_text += f"[ACTION]       : {action}\n"
    if old_email:    log_text += f"[OLD EMAIL]    : {old_email}\n"
    if new_email:    log_text += f"[NEW EMAIL]    : {new_email}\n"
    if old_password: log_text += f"[OLD PASSWORD] : {old_password}\n"
    if new_password: log_text += f"[NEW PASSWORD] : {new_password}\n"
    if local_id:     log_text += f"[LOCALID]      : {local_id}\n"
    if extra:        log_text += f"[EXTRA]        : {extra}\n"
    log_text += "=====================================\n\n"
    file_path = get_user_log_file(user_id, username)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(log_text)

LOG_DIR = "ashlog"

def get_user_log_file(user_id, username):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    safe_username = username if username else "unknown"
    safe_username = safe_username.replace("@", "")
    filename = f"user_{safe_username}.txt" if safe_username != "unknown" else f"user_{user_id}.txt"
    return os.path.join(LOG_DIR, filename)

def log_user(user_id):
    try:
        with open(USERS_FILE, "a") as f:
            f.write(f"{user_id}\n")
    except Exception as e:
        logging.error(f"Failed to log user {user_id}: {e}")

def log_user_action(user_id, email, cpm_type, session_code=""):
    try:
        try:
            with open(USERS_LOG, "r") as f:
                data = json.load(f)
        except:
            data = []
        entry = {
            "telegram_id": user_id,
            "email": email,
            "cpm_type": cpm_type,
            "session_code": session_code,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        data.append(entry)
        with open(USERS_LOG, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        fancy_log(user_id, "SYSTEM", "Failed to log user action", str(e))

#-----------------------------
# ACCESS / REQUEST-ADMIN SYSTEM
#-----------------------------

ACCESS_FILE = "access.json"
ACCESS_DAYS_DEFAULT = 3


def _new_access_data():
    return {"users": {}, "pending": [], "banned": [], "admins": [OWNER_ID]}


def load_access():
    data = _new_access_data()
    try:
        with open(ACCESS_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update(loaded)
    except Exception:
        pass
    data.setdefault("users", {})
    data.setdefault("pending", [])
    data.setdefault("banned", [])
    data.setdefault("admins", [OWNER_ID])
    data["admins"] = [int(x) for x in data["admins"]]
    return data


def save_access(data):
    tmp = ACCESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, ACCESS_FILE)


def is_admin(user_id):
    # Only the original owner can open /admin or approve/reject/ban requests.
    return int(user_id) == OWNER_ID


def _user_entry(data, user_id):
    return data.get("users", {}).get(str(user_id), {})


def _is_expired(entry):
    expires = entry.get("expires_at")
    return bool(expires and time.time() >= expires)


def has_access(user_id):
    if is_admin(user_id):
        return True
    data = load_access()
    sid = str(user_id)
    if int(user_id) in [int(x) for x in data.get("banned", [])]:
        return False
    entry = data.get("users", {}).get(sid, {})
    return entry.get("status") == "approved" and not _is_expired(entry)


def access_label(user_id):
    if is_admin(user_id):
        return "ADMIN"
    data = load_access()
    sid = str(user_id)
    if int(user_id) in [int(x) for x in data.get("banned", [])]:
        return "BANNED"
    entry = data.get("users", {}).get(sid, {})
    if entry.get("status") != "approved":
        return "PENDING" if int(user_id) in data.get("pending", []) else "NO ACCESS"
    if _is_expired(entry):
        return "EXPIRED"
    return "APPROVED"


def _pending_add(data, user_id, username, full_name):
    uid = int(user_id)
    if uid not in data["pending"]:
        data["pending"].append(uid)
    data["users"].setdefault(str(uid), {})
    data["users"][str(uid)].update({
        "username": username or "Unknown",
        "full_name": full_name or "Unknown",
        "status": "pending",
        "updated_at": time.time(),
    })


def approve_user(user_id, days=ACCESS_DAYS_DEFAULT):
    data = load_access()
    sid = str(int(user_id))
    data["users"].setdefault(sid, {})
    entry = data["users"][sid]
    entry["status"] = "approved"
    entry["approved_at"] = time.time()
    entry["expires_at"] = None if days is None else time.time() + max(1, int(days)) * 86400
    data["pending"] = [x for x in data["pending"] if int(x) != int(user_id)]
    data["banned"] = [x for x in data["banned"] if int(x) != int(user_id)]
    save_access(data)


def reject_request(user_id):
    data = load_access()
    data["pending"] = [x for x in data["pending"] if int(x) != int(user_id)]
    if str(int(user_id)) in data["users"]:
        data["users"][str(int(user_id))]["status"] = "rejected"
    save_access(data)


def ban_user(user_id):
    data = load_access()
    uid = int(user_id)
    if uid not in data["banned"]:
        data["banned"].append(uid)
    data["pending"] = [x for x in data["pending"] if int(x) != uid]
    data["users"].setdefault(str(uid), {})["status"] = "banned"
    save_access(data)


def unban_user(user_id):
    data = load_access()
    uid = int(user_id)
    data["banned"] = [x for x in data["banned"] if int(x) != uid]
    if str(uid) in data["users"]:
        data["users"][str(uid)]["status"] = "pending"
    save_access(data)


def remove_access(user_id):
    data = load_access()
    uid = int(user_id)
    data["pending"] = [x for x in data["pending"] if int(x) != uid]
    if str(uid) in data["users"]:
        data["users"][str(uid)]["status"] = "kicked"
        data["users"][str(uid)]["expires_at"] = time.time()
    save_access(data)


def set_expiry_days(user_id, days):
    data = load_access()
    sid = str(int(user_id))
    data["users"].setdefault(sid, {})
    data["users"][sid]["status"] = "approved"
    data["users"][sid]["expires_at"] = time.time() + max(1, int(days)) * 86400
    data["pending"] = [x for x in data["pending"] if int(x) != int(user_id)]
    save_access(data)


def _format_expiry(entry):
    expires = entry.get("expires_at")
    if not expires:
        return "Never"
    if time.time() >= expires:
        return "Expired"
    return datetime.datetime.fromtimestamp(expires).strftime("%d %b %Y %H:%M")


def admin_stats():
    data = load_access()
    approved = 0
    for uid, entry in data.get("users", {}).items():
        if entry.get("status") == "approved" and not _is_expired(entry):
            approved += 1
    return {
        "users": len(data.get("users", {})),
        "pending": len(data.get("pending", [])),
        "banned": len(data.get("banned", [])),
        "approved": approved,
        "admins": len(data.get("admins", [])),
    }


async def send_tools_menu_to_user(context, user_id):
    keyboard = [
        [InlineKeyboardButton("CPM1 Pass", callback_data="CPM1")],
        [InlineKeyboardButton("CPM2 Pass", callback_data="CPM2")],
        [InlineKeyboardButton("CPM1→CPM2 Conversion", callback_data="C2C")],
        [InlineKeyboardButton("CPM2→CPM2 Conversion", callback_data="C2C2")],
        [InlineKeyboardButton("⚙️ Account Manager", callback_data="ACCOUNT")],
        [InlineKeyboardButton("🔥 Unlock All", callback_data="UNLOCK_GIT")],
        [InlineKeyboardButton("🚗 Air,Police,Bodykits", callback_data="LOCAL_MODS")],
        [InlineKeyboardButton("📦 Upload ES3 Folder (ZIP)", callback_data="UPLOAD_ZIP")],
    ]
    await context.bot.send_message(chat_id=user_id, text="🛠️ CPM_MXZ TOOLS\n\nSelect a tool below:", reply_markup=InlineKeyboardMarkup(keyboard))


async def send_tools_menu(message):
    keyboard = [
        [InlineKeyboardButton("CPM1 Pass", callback_data="CPM1")],
        [InlineKeyboardButton("CPM2 Pass", callback_data="CPM2")],
        [InlineKeyboardButton("CPM1→CPM2 Conversion", callback_data="C2C")],
        [InlineKeyboardButton("CPM2→CPM2 Conversion", callback_data="C2C2")],
        [InlineKeyboardButton("⚙️ Account Manager", callback_data="ACCOUNT")],
        [InlineKeyboardButton("🔥 Unlock All", callback_data="UNLOCK_GIT")],
        [InlineKeyboardButton("🚗 Air,Police,Bodykits", callback_data="LOCAL_MODS")],
        [InlineKeyboardButton("📦 Upload ES3 Folder (ZIP)", callback_data="UPLOAD_ZIP")],
    ]
    await message.reply_text("🛠️ CPM_MXZ TOOLS\n\nSelect a tool below:", reply_markup=InlineKeyboardMarkup(keyboard))


def request_access_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Request Admin", callback_data="REQUEST_ACCESS")],
        [InlineKeyboardButton("💬 Contact Admin", callback_data="CONTACT_ADMIN")],
    ])


async def send_access_screen(message, user_id, title="🔒 ACCESS REQUIRED"):
    label = access_label(user_id)
    if label == "BANNED":
        await message.reply_text("🥾 KICKED\n\nAccess removed.\n\nContact admin if you need help.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact Admin", callback_data="CONTACT_ADMIN")]]))
    elif label == "EXPIRED":
        await message.reply_text("⏰ ACCESS EXPIRED\n\nYour access has expired.\n\nRequest access again below.", reply_markup=request_access_keyboard())
    elif label == "PENDING":
        await message.reply_text("📨 REQUEST SENT\n\nYour request is waiting for admin approval.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact Admin", callback_data="CONTACT_ADMIN")]]))
    else:
        await message.reply_text(f"{title}\n\nYou don't have access yet.\nTap below to request access.", reply_markup=request_access_keyboard())


async def notify_admins_access_request(context, user):
    username = f"@{user.username}" if user.username else "No username"
    full_name = user.full_name or "Unknown"
    text = (
        "📨 NEW ACCESS REQUEST\n\n"
        f"👤 {full_name}\n"
        f"🔗 {username}\n"
        f"🆔 {user.id}\n\n"
        "Choose an access period:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ APPROVE", callback_data=f"APPROVE:{user.id}"),
         InlineKeyboardButton("❌ REJECT", callback_data=f"REJ:{user.id}"),
         InlineKeyboardButton("🚫 BAN", callback_data=f"BANREQ:{user.id}")]
    ])
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=text, reply_markup=kb)
    except Exception as e:
        logging.error("Could not notify owner %s: %s", OWNER_ID, e)


async def request_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    if is_admin(uid) or has_access(uid):
        await update.callback_query.answer("You already have access.", show_alert=True)
        await send_tools_menu(update.callback_query.message)
        return WAIT_MENU
    data = load_access()
    if uid in [int(x) for x in data.get("banned", [])]:
        await update.callback_query.answer("You are banned.", show_alert=True)
        return WAIT_MENU
    if uid in [int(x) for x in data.get("pending", [])]:
        await update.callback_query.answer("Request already pending.", show_alert=True)
        return WAIT_MENU
    _pending_add(data, uid, user.username, user.full_name)
    save_access(data)
    await update.callback_query.answer("Request sent.")
    await update.callback_query.message.reply_text("📨 Request sent!\nYou'll be notified when the admin responds.")
    await notify_admins_access_request(context, user)
    return WAIT_MENU


async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = f"@{user.username}" if user.username else "No username"
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"💬 Contact request\n\n👤 {user.full_name}\n🔗 {username}\n🆔 {user.id}"
        )
    except Exception as e:
        logging.error("Could not notify owner %s: %s", OWNER_ID, e)
    await update.callback_query.answer("Admin has been notified.")
    await update.callback_query.message.reply_text(f"💬 Contact admin: {OWNER_USERNAME}\n\n🆔 Your ID: {user.id}")
    return WAIT_MENU

#-----------------------------
# ES3 ENCRYPT / DECRYPT
#-----------------------------

def apply_pkcs7(data: bytes, block_size: int = 16) -> bytes:
    padding = block_size - (len(data) % block_size)
    return data + bytes([padding] * padding)

def remove_pkcs7(data: bytes) -> bytes:
    padding_len = data[-1]
    if padding_len < 1 or padding_len > 16:
        raise ValueError("Bad PKCS7 padding.")
    if data[-padding_len:] != bytes([padding_len]) * padding_len:
        raise ValueError("Bad PKCS7 padding.")
    return data[:-padding_len]

def decrypt_es3(file_data: bytes, password: str) -> bytes:
    if len(file_data) < 16:
        raise ValueError("File too short for ES3.")
    iv = file_data[:16]
    encrypted = file_data[16:]
    key = PBKDF2(password.encode(), iv, dkLen=16, count=100, hmac_hash_module=SHA1)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    decrypted = cipher.decrypt(encrypted)
    return remove_pkcs7(decrypted)

def encrypt_es3(plain_data: bytes, password: str) -> bytes:
    iv = Random.get_random_bytes(16)
    key = PBKDF2(password.encode(), iv, dkLen=16, count=100, hmac_hash_module=SHA1)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    padded = apply_pkcs7(plain_data)
    encrypted = cipher.encrypt(padded)
    return iv + encrypted

#-----------------------------
# SESSION GENERATION LOGIC
#-----------------------------

def generate_session_cpm1(es3_first3: str, email: str, password: str) -> str:
    api_key = "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM"
    url = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={api_key}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
        "clientType": "CLIENT_TYPE_ANDROID"
    }
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        resp = r.json()
        local_id = resp.get("localId")
        if not local_id:
            print(f"[CPM1] Login failed: {resp.get('error', {}).get('message', 'No localId')}")
            return es3_first3 + "ERR"
        return es3_first3 + local_id[:3]
    except Exception as e:
        print(f"[CPM1] Exception: {e}")
        return es3_first3 + "ERR"

def generate_session_cpm2(es3_first3: str, email: str, password: str) -> str:
    api_key = "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ"
    url = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={api_key}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True,
        "clientType": "CLIENT_TYPE_ANDROID"
    }
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        resp = r.json()
        local_id = resp.get("localId")
        if not local_id:
            print(f"[CPM2] Login failed: {resp.get('error', {}).get('message', 'No localId')}")
            return es3_first3 + "ERR"
        return es3_first3 + local_id[:3]
    except Exception as e:
        print(f"[CPM2] Exception: {e}")
        return es3_first3 + "ERR"

#-----------------------------
# ACCOUNT MANAGER HELPERS
#-----------------------------

def login_request(email, password, api_key):
    url = f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword?key={api_key}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    return requests.post(url, json=payload).json()

def update_request(id_token, api_key, new_email=None, new_password=None):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={api_key}"
    payload = {
        "idToken": id_token,
        "returnSecureToken": True
    }
    if new_email:
        payload["email"] = new_email
    if new_password:
        payload["password"] = new_password
    return requests.post(url, json=payload).json()

#-----------------------------
# CPM1 → CPM2 CONVERSION HANDLERS
#-----------------------------

async def handle_cpm1_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Please send your CPM1 ES3 file as a document.")
        return WAIT_CPM1_FILE
    wait = await update.message.reply_text("⏳ Receiving CPM1 file...")
    try:
        file_data = await doc.get_file()
        file_bytes = await file_data.download_as_bytearray()
    except Exception as e:
        await wait.edit_text(f"❌ Failed to download file\n\n{e}\n\nTry sending again.")
        return WAIT_CPM1_FILE
    decoded_name = decode_es3_filename(doc.file_name)
    sessions[user_id]["cpm1_file"] = file_bytes
    sessions[user_id]["cpm1_file_name_decoded"] = decoded_name
    fancy_log(user_id, username, "CPM1 File Received", extra=f"Filename: {decoded_name}")
    await wait.edit_text("✅ CPM1 file received!\n\nNow send your CPM1 email:")
    return WAIT_CPM1_EMAIL

async def handle_cpm2_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Please send your CPM2 ES3 file as a document.")
        return WAIT_CPM2_FILE
    wait = await update.message.reply_text("⏳ Receiving CPM2 file...")
    try:
        file_data = await doc.get_file()
        file_bytes = await file_data.download_as_bytearray()
    except Exception as e:
        await wait.edit_text(f"❌ Failed to download file\n\n{e}\n\nTry sending again.")
        return WAIT_CPM2_FILE
    decoded_name = decode_es3_filename(doc.file_name)
    sessions[user_id]["cpm2_file"] = file_bytes
    sessions[user_id]["cpm2_file_name_decoded"] = decoded_name
    fancy_log(user_id, username, "CPM2 FILE RECEIVED", extra=f"FILENAME: {decoded_name}")
    await wait.edit_text("✅ CPM2 file received!\n\nNow send your CPM2 email:")
    return WAIT_CPM2_EMAIL

async def handle_email_c2c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    if "cpm1_email" not in sessions.get(user_id, {}):
        sessions[user_id]["cpm1_email"] = update.message.text.strip()
        fancy_log(user_id, username, "CPM1 EMAIL SAVED", new_email=sessions[user_id]["cpm1_email"])
        await update.message.reply_text("✅ CPM1 email saved! Now send CPM1 password.")
        return WAIT_CPM1_PASSWORD
    sessions[user_id]["cpm2_email"] = update.message.text.strip()
    fancy_log(user_id, username, "CPM2 EMAIL SAVED", new_email=sessions[user_id]["cpm2_email"])
    await update.message.reply_text("✅ CPM2 email saved! Now send CPM2 password.")
    return WAIT_CPM2_PASSWORD

#-----------------------------------------------------------
# FIXED: handle_password_c2c – NO dependency on saved_cpm2_accounts
#-----------------------------------------------------------
async def handle_password_c2c(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    text = update.message.text.strip()

    if "cpm1_pass" not in sessions[user_id]:
        sessions[user_id]["cpm1_pass"] = text
        await update.message.reply_text("✅ CPM1 password saved! Now upload CPM2 ES3 file if not already done.")
        return WAIT_CPM2_FILE

    if "cpm2_pass" not in sessions[user_id]:
        sessions[user_id]["cpm2_pass"] = text


    # Retrieve data
    cpm1_file = sessions[user_id]["cpm1_file"]
    cpm1_filename = sessions[user_id]["cpm1_file_name_decoded"]
    cpm1_email = sessions[user_id]["cpm1_email"]
    cpm1_pass = sessions[user_id]["cpm1_pass"]
    cpm2_file = sessions[user_id]["cpm2_file"]
    cpm2_filename = sessions[user_id]["cpm2_file_name_decoded"]
    cpm2_email = sessions[user_id]["cpm2_email"]
    cpm2_pass = sessions[user_id]["cpm2_pass"]

    # Get localId for CPM1
    code_cpm1 = generate_session_cpm1(cpm1_filename[:3], cpm1_email, cpm1_pass)
    if code_cpm1.endswith("ERR"):
        await update.message.reply_text("❌ Invalid CPM1 email or password. Please try again.")
        fancy_log(user_id, username, "CPM1 LOGIN FAILED", extra="Invalid credentials")
        return ConversationHandler.END
    local_id_cpm1 = code_cpm1[3:]

    # Get localId for CPM2 using the provided CPM2 credentials (NO Account Manager needed)
    code_cpm2 = generate_session_cpm2(cpm2_filename[:3], cpm2_email, cpm2_pass)
    if code_cpm2.endswith("ERR"):
        await update.message.reply_text("❌ Invalid CPM2 email or password. Please try again.")
        fancy_log(user_id, username, "CPM2 LOGIN FAILED", extra="Invalid credentials")
        return ConversationHandler.END
    local_id_cpm2 = code_cpm2[3:]

    es3_pass_cpm1 = cpm1_filename[:3] + local_id_cpm1
    es3_pass_cpm2 = cpm2_filename[:3] + local_id_cpm2

    try:
        decrypted = decrypt_es3(cpm1_file, es3_pass_cpm1)
    except Exception as e:
        await update.message.reply_text("❌ Failed to decrypt CPM1 file. Make sure it's a valid ES3.")
        fancy_log(user_id, username, "CPM1 DECRYPT FAILED", extra=str(e))
        return ConversationHandler.END

    try:
        converted = encrypt_es3(decrypted, es3_pass_cpm2)
    except Exception as e:
        await update.message.reply_text("❌ Failed to encrypt as CPM2. Please try again.")
        fancy_log(user_id, username, "CPM1→CPM2 ENCRYPT FAILED", extra=str(e))
        return ConversationHandler.END

    await update.message.reply_document(
        document=BytesIO(converted),
        filename=f"{cpm2_filename}.es3",
        caption="✅ CPM1→CPM2 conversion complete!"
    )
    fancy_log(user_id, username, "CPM1→CPM2 Converted")
    log_user_action(user_id, f"{cpm1_email}→{cpm2_email}", "CPM1→CPM2")
    sessions.pop(user_id, None)
    return ConversationHandler.END

#-----------------------------
# NEW: CPM2 → CPM2 CONVERSION HANDLERS
#-----------------------------

async def handle_cpm2a_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Please send your source CPM2 ES3 file as a document.")
        return WAIT_CPM2A_FILE
    wait = await update.message.reply_text("⏳ Receiving source CPM2 file...")
    try:
        file_data = await doc.get_file()
        file_bytes = await file_data.download_as_bytearray()
    except Exception as e:
        await wait.edit_text(f"❌ Failed to download file\n\n{e}\n\nTry sending again.")
        return WAIT_CPM2A_FILE
    decoded_name = decode_es3_filename(doc.file_name)
    sessions[user_id]["cpm2a_file"] = file_bytes
    sessions[user_id]["cpm2a_file_name"] = decoded_name
    fancy_log(user_id, username, "CPM2A File Received", extra=f"Filename: {decoded_name}")
    await wait.edit_text("✅ Source CPM2 file received!\n\nNow send its email:")
    return WAIT_CPM2A_EMAIL

async def handle_cpm2a_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    sessions[user_id]["cpm2a_email"] = update.message.text.strip()
    fancy_log(user_id, username, "CPM2A EMAIL SAVED", new_email=sessions[user_id]["cpm2a_email"])
    await update.message.reply_text("✅ Source email saved! Now send its password.")
    return WAIT_CPM2A_PASSWORD

async def handle_cpm2a_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    sessions[user_id]["cpm2a_pass"] = update.message.text.strip()
    fancy_log(user_id, username, "CPM2A PASSWORD SAVED")
    await update.message.reply_text("✅ Source password saved! Now upload the target CPM2 ES3 file.")
    return WAIT_CPM2B_FILE

async def handle_cpm2b_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Please send your target CPM2 ES3 file as a document.")
        return WAIT_CPM2B_FILE
    wait = await update.message.reply_text("⏳ Receiving target CPM2 file...")
    try:
        file_data = await doc.get_file()
        file_bytes = await file_data.download_as_bytearray()
    except Exception as e:
        await wait.edit_text(f"❌ Failed to download file\n\n{e}\n\nTry sending again.")
        return WAIT_CPM2B_FILE
    decoded_name = decode_es3_filename(doc.file_name)
    sessions[user_id]["cpm2b_file"] = file_bytes
    sessions[user_id]["cpm2b_file_name"] = decoded_name
    fancy_log(user_id, username, "CPM2B File Received", extra=f"Filename: {decoded_name}")
    await wait.edit_text("✅ Target CPM2 file received!\n\nNow send its email:")
    return WAIT_CPM2B_EMAIL

async def handle_cpm2b_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    sessions[user_id]["cpm2b_email"] = update.message.text.strip()
    fancy_log(user_id, username, "CPM2B EMAIL SAVED", new_email=sessions[user_id]["cpm2b_email"])
    await update.message.reply_text("✅ Target email saved! Now send its password.")
    return WAIT_CPM2B_PASSWORD

async def handle_cpm2b_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    sessions[user_id]["cpm2b_pass"] = update.message.text.strip()
    fancy_log(user_id, username, "CPM2B PASSWORD SAVED")


    # Retrieve data
    src_file = sessions[user_id]["cpm2a_file"]
    src_filename = sessions[user_id]["cpm2a_file_name"]
    src_email = sessions[user_id]["cpm2a_email"]
    src_pass = sessions[user_id]["cpm2a_pass"]
    tgt_file = sessions[user_id]["cpm2b_file"]
    tgt_filename = sessions[user_id]["cpm2b_file_name"]
    tgt_email = sessions[user_id]["cpm2b_email"]
    tgt_pass = sessions[user_id]["cpm2b_pass"]

    # Get localId for source
    code_src = generate_session_cpm2(src_filename[:3], src_email, src_pass)
    if code_src.endswith("ERR"):
        await update.message.reply_text("❌ Invalid source CPM2 email or password.")
        fancy_log(user_id, username, "CPM2A LOGIN FAILED", extra="Invalid credentials")
        return ConversationHandler.END
    local_id_src = code_src[3:]

    # Get localId for target
    code_tgt = generate_session_cpm2(tgt_filename[:3], tgt_email, tgt_pass)
    if code_tgt.endswith("ERR"):
        await update.message.reply_text("❌ Invalid target CPM2 email or password.")
        fancy_log(user_id, username, "CPM2B LOGIN FAILED", extra="Invalid credentials")
        return ConversationHandler.END
    local_id_tgt = code_tgt[3:]

    es3_pass_src = src_filename[:3] + local_id_src
    es3_pass_tgt = tgt_filename[:3] + local_id_tgt

    try:
        decrypted = decrypt_es3(src_file, es3_pass_src)
    except Exception as e:
        await update.message.reply_text("❌ Failed to decrypt source CPM2 file. Ensure it's valid.")
        fancy_log(user_id, username, "CPM2A DECRYPT FAILED", extra=str(e))
        return ConversationHandler.END

    try:
        converted = encrypt_es3(decrypted, es3_pass_tgt)
    except Exception as e:
        await update.message.reply_text("❌ Failed to encrypt as target CPM2. Please try again.")
        fancy_log(user_id, username, "CPM2→CPM2 ENCRYPT FAILED", extra=str(e))
        return ConversationHandler.END

    await update.message.reply_document(
        document=BytesIO(converted),
        filename=f"{tgt_filename}.es3",
        caption="✅ CPM2→CPM2 conversion complete!"
    )
    fancy_log(user_id, username, "CPM2→CPM2 Converted")
    log_user_action(user_id, f"{src_email}→{tgt_email}", "CPM2→CPM2")
    sessions.pop(user_id, None)
    return ConversationHandler.END

#-----------------------------
# START & MENU
#-----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    sessions.pop(user_id, None)
    context.user_data.clear()
    context.chat_data.clear()
    log_user(user_id)
    fancy_log(user_id, username, "Start Command (RESET)")

    if is_admin(user_id) or has_access(user_id):
        await update.message.reply_photo(
            photo="https://wallpapers-clan.com/wp-content/uploads/2024/11/sukuna-jujutsu-kaisen-evil-grin-wallpaper-preview.jpg",
            caption=(f"👋 Welcome!\n\n🆔 Your Telegram ID: {user_id}\n"
                     f"🔐 Access: {access_label(user_id)}\n\n👤 Admin: {OWNER_USERNAME}"),
        )
        await send_tools_menu(update.message)
        return WAIT_MENU

    await update.message.reply_text(
        f"🔒 CPM_MXZ ACCESS\n\n🆔 Your Telegram ID: {user_id}\n\n"
        "You need admin approval to use the bot tools.",
        reply_markup=request_access_keyboard()
    )
    return WAIT_MENU

#-----------------------------
# SINGLE CPM1 / CPM2 HANDLERS
#-----------------------------

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ No file detected. Please send your ES3 file as a document.")
        return WAIT_FILE
    filename = doc.file_name or "ES3_FILE"
    decoded = decode_es3_filename(filename)
    es3_first3 = decoded[:3]
    if user_id not in sessions:
        sessions[user_id] = {}
    sessions[user_id]["es3_first3"] = es3_first3
    sessions[user_id]["original_filename"] = decoded
    log_user(user_id)
    fancy_log(user_id, username, "ES3 File Received", extra=f"Raw: {filename} | Decoded: {decoded} | Key: {es3_first3}")
    await update.message.reply_text("✅ ES3 file received!\n\nNow send your **email**.", parse_mode="Markdown")
    return WAIT_EMAIL

async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    if user_id not in sessions or "es3_first3" not in sessions[user_id]:
        await update.message.reply_text("❌ Please select CPM and send your ES3 file first.")
        return WAIT_FILE
    sessions[user_id]["email"] = update.message.text.strip()
    log_user(user_id)
    fancy_log(user_id, username, "Email Saved")
    await update.message.reply_text("✅ Email saved. Now send your **password**.", parse_mode="Markdown")
    return WAIT_PASSWORD

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    if user_id not in sessions or "email" not in sessions[user_id]:
        await update.message.reply_text("❌ Please select CPM and send ES3 file + email first.")
        return WAIT_FILE
    password = update.message.text.strip()
    choice = sessions[user_id]["choice"]
    es3_first3 = sessions[user_id]["es3_first3"]
    email = sessions[user_id]["email"]
    fancy_log(user_id, username, f"{choice} PASSWORD RECEIVED", old_email=email, old_password=password)


    wait = await update.message.reply_text("🔐 Logging in and generating session...")

    if choice == "CPM1":
        session_code = generate_session_cpm1(es3_first3, email, password)
    else:
        session_code = generate_session_cpm2(es3_first3, email, password)

    if session_code.endswith("ERR"):
        await wait.edit_text("❌ Login failed\n\nWrong email or password for this account.", parse_mode="Markdown")
        sessions.pop(user_id, None)
        return ConversationHandler.END

    await wait.edit_text(
        f"✅ Session Code Generated\n\n"
        f"🔐 Code: `{session_code}`",
        parse_mode="Markdown"
    )
    fancy_log(user_id, username, f"{choice} SESSION GENERATED", old_email=email, old_password=password, extra=f"CODE: {session_code}")
    log_user_action(user_id, email, choice, session_code)
    sessions.pop(user_id, None)
    return ConversationHandler.END

#-----------------------------
# MOD FUNCTIONS (unchanged)
#-----------------------------

async def send_modified_zip(msg, user_id):
    folder = sessions[user_id].get("es3_folder")
    if not folder:
        await msg.reply_text("❌ No ES3 folder in session.")
        return
    output_zip = tempfile.mktemp(suffix="_modified.zip")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder):
            for f in files:
                full_path = os.path.join(root, f)
                arcname = os.path.relpath(full_path, folder)
                zipf.write(full_path, arcname)
    with open(output_zip, "rb") as f:
        await msg.reply_document(
            document=f,
            filename="es3_modified.zip",
            caption="✅ Modified ZIP ready!\n\nApply more mods below 👇",
            reply_markup=get_mod_keyboard()
        )
    os.remove(output_zip)

async def handle_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    if not doc or not doc.file_name.endswith(".zip"):
        await update.message.reply_text("❌ Please send a .zip file.")
        return WAIT_ZIP
    wait = await update.message.reply_text("⏳ Downloading ZIP...")
    try:
        temp_zip = tempfile.mktemp(suffix=".zip")
        await (await doc.get_file()).download_to_drive(temp_zip)
    except Exception as e:
        await wait.edit_text(f"❌ Download failed\n\n{e}")
        return WAIT_ZIP
    await wait.edit_text("⏳ Extracting ZIP...")
    try:
        extract_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(temp_zip, 'r') as zr:
            zr.extractall(extract_dir)
        extract_dir = get_actual_es3_folder(extract_dir)
        os.remove(temp_zip)
    except Exception as e:
        await wait.edit_text(f"❌ Extract failed\n\n{e}")
        return WAIT_ZIP
    if user_id not in sessions:
        sessions[user_id] = {}
    sessions[user_id]["es3_folder"] = extract_dir
    files = [f for f in os.listdir(extract_dir) if os.path.isfile(os.path.join(extract_dir, f))]
    es3_key_set = False
    for f in files:
        try:
            decoded = decode_es3_filename(f)
            if len(decoded) >= 3:
                sessions[user_id]["es3_folder_key"] = decoded[:3]
                es3_key_set = True
                break
        except:
            continue
    if not es3_key_set:
        await wait.edit_text("❌ Could not detect ES3 key. Valid CPM2 ES3 ZIP required.")
        return ConversationHandler.END
    await wait.edit_text(
        f"✅ ZIP loaded!\n\n📂 Files detected: {len(files)}\n\nSelect a mod to apply 👇",
        reply_markup=get_mod_keyboard()
    )
    return WAIT_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    if user_id in sessions:
        sessions.pop(user_id)
    fancy_log(user_id, username, "Conversation Cancelled")
    await update.message.reply_text("❌ Operation cancelled. You can start again with /start.")
    return ConversationHandler.END

#-----------------------------
# MENU CHOICE HANDLER – handles ALL callback data
#-----------------------------

async def menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data
    user_id = query.from_user.id
    username = query.from_user.username or "Unknown"
    log_user(user_id)
    fancy_log(user_id, username, f"{choice} Selected")
    if choice == "REQUEST_ACCESS":
        return await request_access(update, context)
    if choice == "CONTACT_ADMIN":
        return await contact_admin(update, context)
    if choice.startswith("APPROVE:") or choice.startswith("REJ:") or choice.startswith("BANREQ:"):
        if not is_admin(user_id):
            await query.answer("Admin only.", show_alert=True)
            return WAIT_MENU
        action, target = choice.split(":", 1)
        target_id = int(target)
        if action == "APPROVE":
            context.user_data["pending_approval_target"] = target_id
            await query.edit_message_text(
                f"✅ APPROVE ACCESS\n\n👤 User ID: {target_id}\n\n"
                "Send the number of days for this user.\nExample: 3"
            )
            return WAIT_MENU
        if action == "REJ":
            reject_request(target_id)
            await query.edit_message_text(f"❌ Request rejected for {target_id}.")
            try:
                await context.bot.send_message(target_id, "❌ Your CPM_MXZ access request was rejected.\n\nYou can request admin access again.", reply_markup=request_access_keyboard())
            except Exception:
                pass
            return WAIT_MENU
        ban_user(target_id)
        await query.edit_message_text(f"🚫 User {target_id} was banned.")
        try:
            await context.bot.send_message(target_id, "🚫 You have been banned from CPM_MXZ.")
        except Exception:
            pass
        return WAIT_MENU

    if choice == "ADMIN_PANEL":
        if not is_admin(user_id):
            await query.answer("Admin only.", show_alert=True)
            return WAIT_MENU
        await show_admin_panel(query.message)
        return WAIT_MENU

    if not has_access(user_id):
        await query.answer("Admin approval required.", show_alert=True)
        await send_access_screen(query.message, user_id)
        return WAIT_MENU
    if user_id not in sessions:
        sessions[user_id] = {}


    sessions[user_id]["choice"] = choice

    # Handle each callback data explicitly
    if choice == "CPM1":
        await safe_edit(query, "✅ CPM1 selected! Upload your ES3 file.")
        return WAIT_FILE
    elif choice == "CPM2":
        await safe_edit(query, "✅ CPM2 selected! Upload your ES3 file.")
        return WAIT_FILE
    elif choice == "C2C":
        await safe_edit(query, "✅ CPM1→CPM2 conversion selected! Upload CPM1 ES3 file.")
        return WAIT_CPM1_FILE
    elif choice == "C2C2":
        await safe_edit(query, "✅ CPM2→CPM2 conversion selected! Upload source CPM2 ES3 file.")
        return WAIT_CPM2A_FILE
    elif choice == "ACCOUNT":
        kb = [
            [InlineKeyboardButton("🔐 Login CPM2", callback_data="LOGINCPM2")],
            [InlineKeyboardButton("✉️ Change Email", callback_data="CHANGEEMAIL")],
            [InlineKeyboardButton("🔑 Change Password", callback_data="CHANGEPASS")]
        ]
        await safe_edit(query, "⚙️ Account Manager", reply_markup=InlineKeyboardMarkup(kb))
        return WAIT_MENU
    elif choice == "UPLOAD_ZIP":
        await safe_edit(query, "📦 Send your ES3 folder as a .zip file")
        return WAIT_ZIP
    elif choice == "UNLOCK_GIT":
        if user_id not in saved_cpm2_accounts:
            sessions[user_id]["pending_mod"] = choice
            await safe_edit(query, "🔐 Login to CPM2 first.\n\n📧 Send your CPM2 email:")
            return WAIT_LOGIN_EMAIL
        if not sessions[user_id].get("es3_folder"):
            await safe_edit(query, "❌ No ZIP loaded. Upload ES3 folder as .zip first.")
            return WAIT_MENU

        await safe_edit(query, "⬇️ Applying Unlock ALL from GitHub...")
        await apply_unlock_all_git(update, context)
        return WAIT_MENU
    elif choice == "LOCAL_MODS":
        if user_id not in saved_cpm2_accounts:
            sessions[user_id]["pending_mod"] = choice
            await safe_edit(query, "🔐 Login to CPM2 first.\n\n📧 Send your CPM2 email:")
            return WAIT_LOGIN_EMAIL
        if not sessions[user_id].get("es3_folder"):
            await safe_edit(query, "❌ No ZIP loaded. Upload ES3 folder as .zip first.")
            return WAIT_MENU

        await safe_edit(query, "🚗 Applying Local Body Mods...")
        await apply_local_mods(update, context)
        return WAIT_MENU
    elif choice == "DOWNLOAD_ZIP":
        folder = sessions[user_id].get("es3_folder")
        if not folder:
            await query.message.reply_text("❌ No ZIP loaded.")
            return WAIT_MENU
        await send_modified_zip(query.message, user_id)
        return WAIT_MENU
    elif choice == "CLEAR_ZIP":
        sessions.pop(user_id, None)
        await query.message.reply_text("🗑 Session cleared.\n\nSend /start to begin again.")
        return WAIT_MENU
    elif choice == "LOGINCPM2":
        await safe_edit(query, "📧 Send your CPM2 email")
        return WAIT_LOGIN_EMAIL
    elif choice == "CHANGEEMAIL":
        if user_id not in saved_cpm2_accounts:
            await safe_edit(query, "❌ Login CPM2 first")
            return WAIT_MENU
        await safe_edit(query, "📧 Send new email")
        return WAIT_NEW_EMAIL
    elif choice == "CHANGEPASS":
        if user_id not in saved_cpm2_accounts:
            await safe_edit(query, "❌ Login CPM2 first")
            return WAIT_MENU
        await safe_edit(query, "🔑 Send new password")
        return WAIT_NEW_PASSWORD
    else:
        await safe_edit(query, "❓ Unknown option. Please use /start.")
        return WAIT_MENU

#-----------------------------
# ACCOUNT MANAGER HANDLERS (unchanged)
#-----------------------------

async def handle_login_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sessions[user_id]["login_email"] = update.message.text.strip()
    await update.message.reply_text("🔑 Now send your CPM2 password")
    return WAIT_LOGIN_PASSWORD

async def handle_login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    password = update.message.text.strip()
    email = sessions[user_id]["login_email"]
    resp = login_request(email, password, "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ")
    if "idToken" not in resp:
        await update.message.reply_text("❌ Login failed. Wrong email or password.")
        sessions[user_id].pop("pending_mod", None)
        return ConversationHandler.END
    saved_cpm2_accounts[user_id] = {
        "idToken": resp["idToken"],
        "localId": resp["localId"],
        "email": email
    }
    fancy_log(user_id, username, "CPM2 LOGIN SUCCESS", old_email=email, old_password=password, local_id=resp["localId"])
    await update.message.reply_text("✅ CPM2 linked successfully!")
    pending_mod = sessions[user_id].pop("pending_mod", None)
    if pending_mod:
        if not sessions[user_id].get("es3_folder"):
            await update.message.reply_text("✅ Logged in!\n\nUpload your ES3 .zip then click the mod button.")
            return WAIT_ZIP

        if pending_mod == "UNLOCK_GIT":
            await update.message.reply_text("⬇️ Applying Unlock ALL from GitHub...")
            await apply_unlock_all_git(update, context)
        elif pending_mod == "LOCAL_MODS":
            await update.message.reply_text("🚗 Applying Local Body Mods...")
            await apply_local_mods(update, context)
        return WAIT_MENU
    return ConversationHandler.END

async def handle_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_email = update.message.text.strip()
    account = saved_cpm2_accounts[user_id]
    resp = update_request(account["idToken"], "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ", new_email=new_email)
    if "email" in resp:
        old_email = account["email"]
        account["email"] = resp["email"]
        if "idToken" in resp:
            account["idToken"] = resp["idToken"]
        await update.message.reply_text(f"✅ Email changed to:\n{resp['email']}")
        fancy_log(user_id, update.effective_user.username or "Unknown", "EMAIL CHANGED", old_email=old_email, new_email=resp["email"])
    else:
        await update.message.reply_text(f"❌ Failed:\n{resp}")
    return ConversationHandler.END

async def handle_new_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_password = update.message.text.strip()
    account = saved_cpm2_accounts[user_id]
    old_email = account["email"]
    resp = update_request(account["idToken"], "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ", new_password=new_password)
    if "idToken" in resp:
        account["idToken"] = resp["idToken"]
        await update.message.reply_text("✅ Password changed successfully")
        fancy_log(user_id, update.effective_user.username or "Unknown", "PASSWORD CHANGED", old_email=old_email, new_password=new_password)
    else:
        await update.message.reply_text(f"❌ Failed:\n{resp}")
    return ConversationHandler.END

#-----------------------------
# ADMIN PANEL / ADMIN COMMANDS
#-----------------------------


def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="ADM_STATS"), InlineKeyboardButton("👥 Users", callback_data="ADM_USERS")],
        [InlineKeyboardButton("📋 Activity Log", callback_data="ADM_LOG" )],
        [InlineKeyboardButton("⏳ Pending Requests", callback_data="ADM_PENDING")],
        [InlineKeyboardButton("➕ Add Access", callback_data="ADM_ADD"), InlineKeyboardButton("📥 Bulk Access", callback_data="ADM_BULK")],
        [InlineKeyboardButton("🚫 Ban", callback_data="ADM_BAN"), InlineKeyboardButton("🔓 Unban", callback_data="ADM_UNBAN")],
        [InlineKeyboardButton("🥾 Kick", callback_data="ADM_KICK"), InlineKeyboardButton("⏰ Expiry", callback_data="ADM_EXPIRY")],
        [InlineKeyboardButton("ℹ️ Profile", callback_data="ADM_PROFILE")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="ADM_BROADCAST")],
        [InlineKeyboardButton("➕ Add Admin", callback_data="ADM_ADDADMIN"), InlineKeyboardButton("➖ Rem Admin", callback_data="ADM_REMADMIN")],
        [InlineKeyboardButton("🔧 Maintenance", callback_data="ADM_MAINT")],
        [InlineKeyboardButton("🔄 Reset Stats", callback_data="ADM_RESET")],
        [InlineKeyboardButton("◂ Home", callback_data="ADM_HOME")],
    ])


async def show_admin_panel(message):
    stats = admin_stats()
    await message.reply_text(
        "👑 CPM_MXZ ADMIN PANEL\n\n"
        "🟢 Maintenance: OFF\n\n"
        f"👥 Users: {stats['users']}\n"
        f"⏳ Pending: {stats['pending']}\n"
        f"🚫 Banned: {stats['banned']}\n"
        f"💎 Approved: {stats['approved']}\n"
        f"🛡 Admins: {stats['admins']}\n",
        reply_markup=admin_keyboard()
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use /admin.")
        return
    await show_admin_panel(update.message)
    return WAIT_MENU


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if not is_admin(uid):
        await query.answer("Admin only.", show_alert=True)
        return
    choice = query.data
    data = load_access()

    # Access-request decisions are owner-only.
    # APPROVE intentionally asks the owner for the number of days.
    if choice.startswith("APPROVE:") or choice.startswith("REJ:") or choice.startswith("BANREQ:"):
        action, target = choice.split(":", 1)
        target_id = int(target)

        if action == "APPROVE":
            context.user_data["pending_approval_target"] = target_id
            await query.edit_message_text(
                f"✅ APPROVE ACCESS\\n\\n"
                f"👤 User ID: {target_id}\\n\\n"
                "Send the number of days for this user.\\n"
                "Example: 3"
            )
            return

        if action == "REJ":
            reject_request(target_id)
            await query.edit_message_text(f"❌ Request rejected for {target_id}.")
            try:
                await context.bot.send_message(
                    target_id,
                    "❌ Your CPM_MXZ access request was rejected.\\n\\n"
                    "You can request admin access again.",
                    reply_markup=request_access_keyboard()
                )
            except Exception as e:
                logging.error("Could not notify rejected user %s: %s", target_id, e)
            return

        ban_user(target_id)
        await query.edit_message_text(f"🚫 User {target_id} was banned.")
        try:
            await context.bot.send_message(target_id, "🚫 You have been banned from CPM_MXZ.")
        except Exception as e:
            logging.error("Could not notify banned user %s: %s", target_id, e)
        return

    if choice == "ADM_STATS":
        s = admin_stats()
        await query.message.reply_text(f"📊 STATS\n\n👥 Users: {s['users']}\n⏳ Pending: {s['pending']}\n🚫 Banned: {s['banned']}\n💎 Approved: {s['approved']}\n🛡 Admins: {s['admins']}")
    elif choice == "ADM_USERS":
        rows = []
        for sid, entry in list(data.get("users", {}).items())[-50:]:
            rows.append(f"• {sid} — {entry.get('status','unknown')} — {_format_expiry(entry)}")
        await query.message.reply_text("👥 USERS\n\n" + ("\n".join(rows) if rows else "No users yet."))
    elif choice == "ADM_PENDING":
        pending = data.get("pending", [])
        if not pending:
            await query.message.reply_text("⏳ No pending requests.")
        else:
            for target in pending[:30]:
                entry = data.get("users", {}).get(str(target), {})
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ APPROVE", callback_data=f"APPROVE:{target}"), InlineKeyboardButton("❌ REJECT", callback_data=f"REJ:{target}"), InlineKeyboardButton("🚫 BAN", callback_data=f"BANREQ:{target}")]])
                await query.message.reply_text(f"⏳ Pending request\n\n👤 {entry.get('full_name','Unknown')}\n🔗 @{entry.get('username','Unknown')}\n🆔 {target}", reply_markup=kb)
    elif choice in {"ADM_ADD", "ADM_BULK", "ADM_BAN", "ADM_UNBAN", "ADM_KICK", "ADM_EXPIRY", "ADM_PROFILE", "ADM_BROADCAST", "ADM_ADDADMIN", "ADM_REMADMIN", "ADM_MAINT"}:
        prompts = {
            "ADM_ADD": "➕ ADD ACCESS\n\nSend: user_id days\nExample: 123456789 3",
            "ADM_BULK": "📥 BULK ACCESS\n\nSend: id1,id2,id3 days\nExample: 123,456,789 30",
            "ADM_BAN": "🚫 BAN\n\nSend the user ID.",
            "ADM_UNBAN": "🔓 UNBAN\n\nSend the user ID.",
            "ADM_KICK": "🥾 KICK\n\nSend the user ID.",
            "ADM_EXPIRY": "⏰ EXPIRY\n\nSend: user_id days",
            "ADM_PROFILE": "ℹ️ PROFILE\n\nSend the user ID.",
            "ADM_BROADCAST": "📢 BROADCAST\n\nSend the message to broadcast.",
            "ADM_ADDADMIN": "➕ ADD ADMIN\n\nSend the user ID.",
            "ADM_REMADMIN": "➖ REMOVE ADMIN\n\nSend the user ID.",
            "ADM_MAINT": "🔧 MAINTENANCE\n\nSend ON or OFF.",
        }
        context.user_data["admin_action"] = choice
        await query.message.reply_text(prompts[choice])
    elif choice == "ADM_RESET":
        data = load_access(); data["pending"] = []; save_access(data)
        try:
            with open(USERS_LOG, "w", encoding="utf-8") as f: json.dump([], f)
        except Exception:
            pass
        await query.message.reply_text("🔄 Stats reset. Approved/banned users were kept.")
    elif choice == "ADM_LOG":
        try:
            path = Path(LOG_DIR)
            files = list(path.glob("*.txt")) if path.exists() else []
            await query.message.reply_text("📋 ACTIVITY LOG\n\n" + ("\n".join(f.name for f in files[-30:]) if files else "No logs yet."))
        except Exception:
            await query.message.reply_text("📋 No activity logs available.")
    elif choice == "ADM_HOME":
        if has_access(uid):
            await send_tools_menu(query.message)
        else:
            await send_access_screen(query.message, uid)


async def addaccess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else ACCESS_DAYS_DEFAULT
        approve_user(target, days)
        await update.message.reply_text(f"✅ Access approved for {target} for {days} days.")
        await context.bot.send_message(target, f"✅ Admin granted you access for {days} days. Send /start to open the tools.")
    except Exception:
        await update.message.reply_text("Usage: /addaccess <user_id> [days]")


async def bulkaccess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        ids = [int(x.strip()) for x in context.args[0].split(",") if x.strip()]
        days = int(context.args[1]) if len(context.args) > 1 else ACCESS_DAYS_DEFAULT
        for target in ids:
            approve_user(target, days)
        await update.message.reply_text(f"✅ Approved {len(ids)} users for {days} days.")
    except Exception:
        await update.message.reply_text("Usage: /bulkaccess <id1,id2,...> [days]")


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0]); ban_user(target)
        await update.message.reply_text(f"🚫 User {target} banned.")
    except Exception:
        await update.message.reply_text("Usage: /ban <user_id>")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0]); unban_user(target)
        await update.message.reply_text(f"🔓 User {target} unbanned.")
    except Exception:
        await update.message.reply_text("Usage: /unban <user_id>")


async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0]); remove_access(target)
        await update.message.reply_text(f"🥾 User {target} kicked.")
        await context.bot.send_message(target, "🥾 KICKED\n\nAccess removed.")
    except Exception:
        await update.message.reply_text("Usage: /kick <user_id>")


async def expiry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0]); days = int(context.args[1]); set_expiry_days(target, days)
        await update.message.reply_text(f"⏰ User {target} access set to {days} days.")
    except Exception:
        await update.message.reply_text("Usage: /expiry <user_id> <days>")


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0]) if context.args else update.effective_user.id
        data = load_access(); entry = data.get("users", {}).get(str(target), {})
        await update.message.reply_text(f"ℹ️ PROFILE\n\n🆔 {target}\n👤 {entry.get('full_name','Unknown')}\n🔗 @{entry.get('username','Unknown')}\n📌 Status: {access_label(target)}\n⏰ Expiry: {_format_expiry(entry)}")
    except Exception:
        await update.message.reply_text("Usage: /profile <user_id>")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    msg = " ".join(context.args).strip()
    if not msg:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    sent = 0
    for sid in load_access().get("users", {}):
        try:
            await context.bot.send_message(int(sid), f"📢 CPM_MXZ BROADCAST\n\n{msg}")
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"📢 Broadcast sent to {sent} users.")


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0]); data = load_access()
        if target == OWNER_ID:
            await update.message.reply_text("ℹ️ The owner is already the only admin with /admin access.")
        else:
            await update.message.reply_text("ℹ️ Only the owner can access /admin and handle requests.")
    except Exception:
        await update.message.reply_text("Usage: /addadmin <user_id>")


async def remadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    try:
        target = int(context.args[0]); data = load_access()
        if target == int(ADMIN_ID[0]):
            await update.message.reply_text("❌ The primary admin cannot be removed.")
            return
        data["admins"] = [x for x in data["admins"] if int(x) != target]
        save_access(data)
        await update.message.reply_text(f"🛡 Admin removed: {target}")
    except Exception:
        await update.message.reply_text("Usage: /remadmin <user_id>")


async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    path = "maintenance.json"
    status = bool(context.args and context.args[0].lower() in {"on", "true", "1"})
    with open(path, "w", encoding="utf-8") as f: json.dump({"on": status}, f)
    await update.message.reply_text(f"🔧 Maintenance: {'ON' if status else 'OFF'}")


async def resetstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Not authorized.")
        return
    data = load_access()
    data["pending"] = []
    save_access(data)
    try:
        with open(USERS_LOG, "w", encoding="utf-8") as f: json.dump([], f)
    except Exception:
        pass
    await update.message.reply_text("🔄 Stats reset. Approved/banned users were kept.")


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return None
    raw = (update.message.text or "").strip()
    if context.user_data.get("pending_approval_target") is not None:
        target = int(context.user_data.pop("pending_approval_target"))
        try:
            days = int(raw)
            if days <= 0: raise ValueError
        except ValueError:
            context.user_data["pending_approval_target"] = target
            await update.message.reply_text("❌ Send a valid number of days, for example: 3")
            return WAIT_MENU
        approve_user(target, days)
        await update.message.reply_text(f"✅ User {target} approved for {days} day(s).")
        try:
            await context.bot.send_message(target, f"✅ Your CPM_MXZ access has been approved for {days} day(s).\n\nYou can use the bot now.")
            await send_tools_menu_to_user(context, target)
        except Exception as e:
            logging.error("Could not notify approved user %s: %s", target, e)
        return WAIT_MENU
    if not context.user_data.get("admin_action"):
        return None
    action = context.user_data.pop("admin_action")
    try:
        if action == "ADM_ADD":
            parts = raw.split(); target = int(parts[0]); days = int(parts[1]) if len(parts) > 1 else ACCESS_DAYS_DEFAULT
            approve_user(target, days)
            await update.message.reply_text(f"✅ Access approved for {target} for {days} days.")
            try:
                await context.bot.send_message(target, f"✅ Your CPM_MXZ access has been approved for {days} days.")
                await send_tools_menu_to_user(context, target)
            except Exception as e:
                logging.error("Could not notify approved user %s: %s", target, e)
        elif action == "ADM_BULK":
            parts = raw.split(); ids = [int(x) for x in parts[0].split(",") if x]; days = int(parts[1]) if len(parts) > 1 else ACCESS_DAYS_DEFAULT
            for target in ids:
                approve_user(target, days)
                try:
                    await context.bot.send_message(target, f"✅ Your CPM_MXZ access has been approved for {days} days.")
                    await send_tools_menu_to_user(context, target)
                except Exception as e:
                    logging.error("Could not notify approved user %s: %s", target, e)
            await update.message.reply_text(f"✅ Approved {len(ids)} users for {days} days.")
        elif action == "ADM_BAN":
            target=int(raw); ban_user(target); await update.message.reply_text(f"🚫 User {target} banned.")
        elif action == "ADM_UNBAN":
            target=int(raw); unban_user(target); await update.message.reply_text(f"🔓 User {target} unbanned.")
        elif action == "ADM_KICK":
            target=int(raw); remove_access(target); await update.message.reply_text(f"🥾 User {target} kicked.")
            try: await context.bot.send_message(target, "🥾 KICKED\\n\\nAccess removed.")
            except Exception: pass
        elif action == "ADM_EXPIRY":
            parts=raw.split(); target=int(parts[0]); days=int(parts[1]); set_expiry_days(target, days)
            await update.message.reply_text(f"⏰ User {target} access set to {days} days.")
        elif action == "ADM_PROFILE":
            target=int(raw); data=load_access(); entry=data.get("users",{}).get(str(target),{})
            await update.message.reply_text(f"ℹ️ PROFILE\\n\\n🆔 {target}\\n👤 {entry.get('full_name','Unknown')}\\n🔗 @{entry.get('username','Unknown')}\\n📌 Status: {access_label(target)}\\n⏰ Expiry: {_format_expiry(entry)}")
        elif action == "ADM_BROADCAST":
            sent=0
            for sid in load_access().get("users",{}):
                try: await context.bot.send_message(int(sid), f"📢 CPM_MXZ BROADCAST\\n\\n{raw}"); sent += 1
                except Exception: pass
            await update.message.reply_text(f"📢 Broadcast sent to {sent} users.")
        elif action == "ADM_ADDADMIN":
            target=int(raw); data=load_access()
            if target == OWNER_ID:
                await update.message.reply_text("ℹ️ The owner is already the only admin with /admin access.")
            else:
                await update.message.reply_text("ℹ️ Only the owner can access /admin and handle requests.")
        elif action == "ADM_REMADMIN":
            target=int(raw); data=load_access()
            if target == int(ADMIN_ID[0]):
                await update.message.reply_text("❌ The primary admin cannot be removed.")
            else:
                data["admins"]=[x for x in data["admins"] if int(x)!=target]; save_access(data)
                await update.message.reply_text(f"🛡 Admin removed: {target}")
        elif action == "ADM_MAINT":
            status=raw.lower() in {"on","true","1"}
            with open("maintenance.json","w",encoding="utf-8") as f: json.dump({"on":status},f)
            await update.message.reply_text(f"🔧 Maintenance: {'ON' if status else 'OFF'}")
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid input: {e}")
    return None


async def stopbot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Not authorized.")
        return
    await update.message.reply_text("🛑 Stopping bot...")
    fancy_log(user_id, "ADMIN", "Bot Stopped")
    sys.exit(0)

#-----------------------------
# MOD APPLY FUNCTIONS (unchanged)
#-----------------------------

def ReplaceCarFields(text: str) -> str:
    lines = text.split("\n")
    output = []
    bodykitArrays = [
        ["SpoilerIds", "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,174,1750,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255,256,257,258,259,260,261,262,263,264,265,266,267,268,269,270,271,272,273,274,275,276,277,278,279,280,281,282,283,284,285,286,287,288,289,290,291,292,293,294,295,296,297,298,299,300"],
        ["FrontBumperIds", "0,1,2,3,4,5"],
        ["RearBumperIds", "0,1,2,3,4,5"],
        ["SkirtIds", "0,1,2,3,4,5"],
        ["HoodIds", "0,1,2,3,4"],
        ["HoodAirIntakeIds", "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255,256,257,258,259,260,261,262,263,264,265,266,267,268,269,270,271,272,273,274,275,276,277,278,279,280,281,282,283,284,285,286,287,288,289,290,291,292,293,294,295,296,297,298,299,300"],
        ["RoofAirIntakeIds", "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255,256,257,258,259,260,261,262,263,264,265,266,267,268,269,270,271,272,273,274,275,276,277,278,279,280,281,282,283,284,285,286,287,288,289,290,291,292,293,294,295,296,297,298,299,300"],
        ["FenderIds", "0,1,2,3,4,5"],
        ["TrimIds", "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255,256,257,258,259,260,261,262,263,264,265,266,267,268,269,270,271,272,273,274,275,276,277,278,279,280,281,282,283,284,285,286,287,288,289,290,291,292,293,294,295,296,297,298,299,300"]
    ]
    inside_array = False
    current_array = ""
    for line in lines:
        trimmed = line.strip()
        new_line = line
        if inside_array:
            for arr in bodykitArrays:
                if arr[0] == current_array:
                    new_line = "        " + arr[1]
                    break
            inside_array = False
            output.append(new_line)
            continue
        for arr in bodykitArrays:
            if trimmed.startswith(f"\"{arr[0]}\""):
                output.append(line)
                inside_array = True
                current_array = arr[0]
                break
        if inside_array:
            continue
        if "\"TopLight\"" in trimmed and ": -1" in line:
            new_line = line.replace(": -1", ": 4")
        if "\"Roobar\"" in trimmed and ": -1" in line:
            new_line = line.replace(": -1", ": 2")
        if "\"FrontInterior\"" in trimmed and ": -1" in line:
            new_line = line.replace(": -1", ": 2")
        if "\"RearInterior\"" in trimmed and ": -1" in line:
            new_line = line.replace(": -1", ": 2")
        if "\"Bought\"" in trimmed and ": false" in line:
            new_line = line.replace(": false", ": true")
        if "\"Installed\"" in trimmed and ": false" in line:
            new_line = line.replace(": false", ": true")
        output.append(new_line)
    return "\n".join(output)

async def apply_unlock_all_git(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.callback_query.message
    if user_id not in saved_cpm2_accounts:
        await msg.reply_text("❌ Please login CPM2 first.")
        return
    folder = sessions[user_id].get("es3_folder")
    if not folder:
        await msg.reply_text("❌ No ES3 folder loaded. Please upload your ZIP first.")
        return
    try:
        url = "https://raw.githubusercontent.com/ash28don/rish-setup/main/UnlockAll.txt"
        resp = safe_request(requests.get, url, timeout=20)
        data = resp.content
        local_id = saved_cpm2_accounts[user_id]["localId"]
        es3_key = sessions[user_id].get("es3_folder_key", "XXX")
        session_pass = build_es3_password(es3_key[:3], local_id)
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        applied = False
        for f in files:
            path = os.path.join(folder, f)
            decoded = decode_es3_filename(f)
            if "39dPlayerData" in decoded or "PlayerData" in decoded:
                encrypted = encrypt_es3(data, session_pass)
                with open(path, "wb") as out:
                    out.write(encrypted)
                applied = True
                break
        if not applied:
            await msg.reply_text("❌ PlayerData file not found in ZIP.")
            return
        await msg.reply_text("🔥 Unlock ALL applied!")
        await send_modified_zip(msg, user_id)
    except Exception as e:
        await msg.reply_text(f"❌ Failed: {str(e)}")

async def apply_local_mods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    msg = query.message if query else update.message
    user_id = update.effective_user.id
    if user_id not in saved_cpm2_accounts:
        await msg.reply_text("❌ Please login CPM2 first.")
        return
    folder = sessions[user_id].get("es3_folder")
    if not folder:
        await msg.reply_text("❌ No ES3 folder loaded. Please upload your ZIP first.")
        return
    local_id = saved_cpm2_accounts[user_id]["localId"]
    session_pass = build_es3_password(sessions[user_id]["es3_folder_key"][:3], local_id)
    files = os.listdir(folder)
    processed = 0
    modified = 0
    failed = 0
    await msg.reply_text("🚗 Applying Local Mods...")
    for f in files:
        path = os.path.join(folder, f)
        if not os.path.isfile(path):
            continue
        decoded = decode_es3_filename(f)
        if "maindata" not in decoded.lower():
            continue
        try:
            encrypted = open(path, "rb").read()
            decrypted = decrypt_es3(encrypted, session_pass)
            try:
                text = decrypted.decode("utf-8")
            except:
                text = decrypted.decode("utf-8", errors="ignore")
            new_text = ReplaceCarFields(text)
            if new_text == text:
                processed += 1
                continue
            final = encrypt_es3(new_text.encode("utf-8"), session_pass)
            test = decrypt_es3(final, session_pass).decode("utf-8", errors="ignore")
            if "SpoilerIds" not in test:
                raise Exception("Round-trip validation failed")
            with open(path, "wb") as out:
                out.write(final)
            modified += 1
            processed += 1
        except Exception as e:
            print(f"[LOCAL MOD ERROR] {f} | {decoded} | {e}")
            failed += 1
            continue
    await msg.reply_text(
        f"🚗 Local Mods Done\n\n"
        f"📂 Total: {len(files)}\n"
        f"⚙️ Processed: {processed}\n"
        f"✅ Modified: {modified}\n"
        f"❌ Failed: {failed}"
    )
    await send_modified_zip(msg, user_id)

#-----------------------------
# ACCESS EXPIRY MONITOR
#-----------------------------

async def access_expiry_monitor(application):
    while True:
        try:
            data = load_access(); changed = False; now = time.time()
            for sid, entry in data.get("users", {}).items():
                if entry.get("status") == "approved":
                    expires = entry.get("expires_at")
                    if expires and now >= float(expires):
                        entry["status"] = "expired"
                        if not entry.get("expiry_notified"):
                            entry["expiry_notified"] = True; changed = True
                            try:
                                await application.bot.send_message(int(sid), "⏰ Your CPM_MXZ access was expired.\n\nRequest admin access again or contact admin.", reply_markup=request_access_keyboard())
                            except Exception as e:
                                logging.error("Could not send expiry notice to %s: %s", sid, e)
            if changed: save_access(data)
        except Exception as e:
            logging.error("Access expiry monitor error: %s", e)
        await asyncio.sleep(30)

async def post_init(application):
    application.create_task(access_expiry_monitor(application), name="access_expiry_monitor")

#-----------------------------
# BOT SETUP
#-----------------------------

async def error_handler(update, context):
    print("Exception:", context.error)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Global commands: these must run even while the owner/user is inside a conversation state.
    # /start always resets the current flow; /admin always opens the owner panel.
    app.add_handler(CommandHandler("start", start), group=0)
    app.add_handler(CommandHandler("admin", admin_command), group=0)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("admin", admin_command)],
        states={
            WAIT_MENU: [CallbackQueryHandler(menu_choice), MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler)],

            WAIT_FILE: [MessageHandler(filters.Document.ALL, handle_file)],
            WAIT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
            WAIT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password)],

            WAIT_LOGIN_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_login_email)],
            WAIT_LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_login_password)],

            WAIT_NEW_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_email)],
            WAIT_NEW_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_password)],

            WAIT_CPM1_FILE: [MessageHandler(filters.Document.ALL, handle_cpm1_file)],
            WAIT_CPM1_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_c2c)],
            WAIT_CPM1_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password_c2c)],

            WAIT_CPM2_FILE: [MessageHandler(filters.Document.ALL, handle_cpm2_file)],
            WAIT_CPM2_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_c2c)],
            WAIT_CPM2_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password_c2c)],

            # New CPM2→CPM2 states
            WAIT_CPM2A_FILE: [MessageHandler(filters.Document.ALL, handle_cpm2a_file)],
            WAIT_CPM2A_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cpm2a_email)],
            WAIT_CPM2A_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cpm2a_password)],
            WAIT_CPM2B_FILE: [MessageHandler(filters.Document.ALL, handle_cpm2b_file)],
            WAIT_CPM2B_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cpm2b_email)],
            WAIT_CPM2B_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cpm2b_password)],

            WAIT_ZIP: [MessageHandler(filters.Document.ALL, handle_zip)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=True,
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern=r"^(ADM_|APPROVE:|REJ:|BANREQ:).*"))
    app.add_handler(conv_handler)
    # Handles the owner's day count after APPROVE when the owner is not inside
    # an active ConversationHandler state.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))
    app.add_handler(CommandHandler("stopbot", stopbot_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addaccess", addaccess_command))
    app.add_handler(CommandHandler("bulkaccess", bulkaccess_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("kick", kick_command))
    app.add_handler(CommandHandler("expiry", expiry_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("addadmin", addadmin_command))
    app.add_handler(CommandHandler("remadmin", remadmin_command))
    app.add_handler(CommandHandler("maintenance", maintenance_command))
    app.add_handler(CommandHandler("resetstats", resetstats_command))
    app.add_error_handler(error_handler)

    print("🤖 CPM_MXZ bot running — owner approval access system enabled.")
    app.run_polling()

if __name__ == "__main__":
    main()
