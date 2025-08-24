import os
import asyncio
import requests
import certifi
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserIsBlocked, PeerIdInvalid

# ------------------- #
# CONFIGURATION       #
# ------------------- #
API_ID = 24776094
API_HASH = "3e64a4ff715d8050835678609de1b1e2"
BOT_TOKEN = "8155988361:AAFajtRD626b2839Ze3YMY1IICbhCbtV6Cc"
MONGO_URI = "mongodb+srv://r03764346:dFRzCwvYTV59MV5g@cluster0.xcrhdwc.mongodb.net/?retryWrites=true&w=majority"
ADMIN_ID = 7922285746

# Constants
INITIAL_CREDITS = 5
REFERRAL_BONUS = 10
LOOKUP_COST = 1

# Initialize Bot
app = Client("vehicle_info_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize MongoDB with SSL fix
mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
db = mongo_client.vehicle_bot
users = db.users
user_states = {}

# ------------------- #
# DATABASE HELPERS    #
# ------------------- #
def add_user(user_id: int, name: str, referred_by: int = None):
    if users.find_one({"user_id": user_id}):
        return
    users.insert_one({
        "user_id": user_id, "first_name": name, "credits": INITIAL_CREDITS,
        "referred_by": referred_by, "referrals": 0, "lookups_done": 0,
        "is_banned": False, "is_premium": False
    })
    if referred_by:
        users.update_one({"user_id": referred_by}, {"$inc": {"credits": REFERRAL_BONUS, "referrals": 1}})

def get_user(uid: int):
    return users.find_one({"user_id": uid})

def update_credits(uid: int, premium: bool):
    if premium:
        users.update_one({"user_id": uid}, {"$inc": {"lookups_done": 1}})
    else:
        users.update_one({"user_id": uid}, {"$inc": {"credits": -LOOKUP_COST, "lookups_done": 1}})

# ------------------- #
# VEHICLE LOOKUP      #
# ------------------- #
def fetch_vehicle(rc: str) -> dict:
    url = f"https://vahanx.in/rc-search/{rc.strip().upper()}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        return {"error": str(e)}

    def val(label):
        try:
            return soup.find("span", string=label).find_parent("div").find("p").get_text(strip=True)
        except:
            return None

    return {
        "Owner Name": val("Owner Name"),
        "Model Name": val("Model Name"),
        "Fuel Type": val("Fuel Type"),
        "Registration Date": val("Registration Date"),
        "Insurance Upto": val("Insurance Upto"),
        "Registered RTO": val("Registered RTO"),
        "Address": val("Address"),
        "Owner": "@userbahi"
    }

# ------------------- #
# MENUS               #
# ------------------- #
async def main_menu(target):
    text = f"👋 Welcome, {target.from_user.first_name}!"
    kb = [[InlineKeyboardButton("🔍 Vehicle Lookup", callback_data="lookup")],
          [InlineKeyboardButton("👥 Referral", callback_data="ref"), InlineKeyboardButton("💰 Credits", callback_data="credits")],
          [InlineKeyboardButton("📊 Stats", callback_data="stats"), InlineKeyboardButton("ℹ️ Help", callback_data="help")]]
    if target.from_user.id == ADMIN_ID:
        kb.append([InlineKeyboardButton("👑 Admin", callback_data="admin")])

    reply = InlineKeyboardMarkup(kb)
    if isinstance(target, Message):
        await target.reply_text(text, reply_markup=reply)
    else:
        await target.message.edit_text(text, reply_markup=reply)

# ------------------- #
# COMMANDS            #
# ------------------- #
@app.on_message(filters.command("start"))
async def start(_, m: Message):
    ref = int(m.command[1]) if len(m.command) > 1 and m.command[1].isdigit() else None
    add_user(m.from_user.id, m.from_user.first_name, ref)
    await main_menu(m)

@app.on_message(filters.command(["ban", "unban", "premium", "unpremium"]))
async def admin_toggle(_, m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    if len(m.command) < 2:
        return await m.reply_text("Usage: /ban <id>")

    uid = int(m.command[1])
    field = m.command[0]
    val = field in ["unban", "unpremium"]
    update = {"ban": {"is_banned": True}, "unban": {"is_banned": False},
              "premium": {"is_premium": True}, "unpremium": {"is_premium": False}}[field]
    users.update_one({"user_id": uid}, {"$set": update})
    await m.reply_text(f"✅ User {uid} updated.")

@app.on_message(filters.command("addcredit"))
async def add_credit(_, m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    if len(m.command) < 3:
        return await m.reply_text("Usage: /addcredit <id> <amt>")
    uid, amt = int(m.command[1]), int(m.command[2])
    users.update_one({"user_id": uid}, {"$inc": {"credits": amt}})
    await m.reply_text(f"✅ Added {amt} credits to {uid}.")

@app.on_message(filters.command("broadcast"))
async def broadcast(_, m: Message):
    if m.from_user.id != ADMIN_ID or not m.reply_to_message:
        return
    msg, sent, fail = await m.reply_text("📢 Broadcasting..."), 0, 0
    async for u in users.find({"is_banned": False}):
        try:
            await m.reply_to_message.copy(u["user_id"])
            sent += 1
        except (UserIsBlocked, PeerIdInvalid):
            fail += 1
        await asyncio.sleep(0.05)
    await msg.edit_text(f"✅ Done! Sent: {sent}, Failed: {fail}")

# ------------------- #
# CALLBACK HANDLER    #
# ------------------- #
@app.on_callback_query()
async def cb(_, q: CallbackQuery):
    u = get_user(q.from_user.id)
    if not u:
        add_user(q.from_user.id, q.from_user.first_name)
        u = get_user(q.from_user.id)

    back = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
    
    if q.data == "lookup":
        await q.message.edit_text("➡️ Send a vehicle number:", reply_markup=back)
        user_states[q.from_user.id] = "awaiting"
    elif q.data == "ref":
        link = f"https://t.me/{(await app.get_me()).username}?start={q.from_user.id}"
        await q.message.edit_text(f"👥 Refer friends & earn {REFERRAL_BONUS} credits!\nLink: `{link}`", reply_markup=back)
    elif q.data == "credits":
        cr = "Unlimited" if u.get("is_premium") else u.get("credits", 0)
        await q.message.edit_text(f"💰 You have **{cr}** credits.", reply_markup=back)
    elif q.data == "stats":
        await q.message.edit_text(f"📊 Stats:\nReferrals: {u.get('referrals',0)}\nLookups: {u.get('lookups_done',0)}", reply_markup=back)
    elif q.data == "help":
        await q.message.edit_text("ℹ️ Send a vehicle number after choosing Lookup.", reply_markup=back)
    elif q.data == "back":
        await main_menu(q)
    elif q.data == "admin" and q.from_user.id == ADMIN_ID:
        stats = {"Users": users.count_documents({}),
                 "Premium": users.count_documents({"is_premium": True}),
                 "Banned": users.count_documents({"is_banned": True}),
                 "Lookups": sum(x.get("lookups_done",0) for x in users.find({}))}
        text = "👑 Admin Panel:\n" + "\n".join([f"{k}: {v}" for k,v in stats.items()])
        await q.message.edit_text(text, reply_markup=back)
    await q.answer()

# ------------------- #
# VEHICLE INPUT       #
# ------------------- #
@app.on_message(filters.text)
async def vehicle(_, m: Message):
    uid = m.from_user.id
    if user_states.get(uid) != "awaiting":
        return
    user_states.pop(uid, None)
    u = get_user(uid)
    if u.get("is_banned"):
        return await m.reply_text("❌ You are banned.")
    if not u.get("is_premium") and u.get("credits",0) < LOOKUP_COST:
        return await m.reply_text("❌ Not enough credits.")

    msg = await m.reply_text("🔍 Searching...")
    data = fetch_vehicle(m.text)
    if data.get("error") or not any(data.values()):
        return await msg.edit_text("❌ No details found.")
    update_credits(uid, u.get("is_premium"))
    u = get_user(uid)
    cr = "Unlimited" if u.get("is_premium") else u.get("credits",0)
    text = "\n".join([f"**{k}:** `{v}`" for k,v in data.items() if v])
    await msg.edit_text(f"✅ Details for `{m.text.upper()}`:\n\n{text}\n\nCredits left: {cr}")

# ------------------- #
# RUN BOT             #
# ------------------- #
if __name__ == "__main__":
    print("🚀 Bot starting...")
    app.run()
