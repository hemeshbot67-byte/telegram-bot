import telebot
from telebot import types
import pyzipper
from datetime import datetime, timezone, timedelta
import random
import os
import io
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import firebase_admin
from firebase_admin import credentials, db
import time

TOKEN = os.environ.get("BOT_TOKEN", "9046269011:AAGKD0jYHyf79UVozWtTUo1j6rVM5QuDeNE")
bot = telebot.TeleBot(TOKEN)

ADMIN_IDS = [8516400686, 6911427937]
ADMIN_PASSWORD = "101010"

def is_admin(user_id):
    return int(user_id) in [int(admin_id) for admin_id in ADMIN_IDS]

firebase_config_json = os.environ.get("FIREBASE_CONFIG_JSON")

if firebase_config_json:
    cred_dict = json.loads(firebase_config_json)
    cred = credentials.Certificate(cred_dict)
else:
    cred = credentials.Certificate("firebase_credentials.json")

firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://telegrambotdb-e08fd-default-rtdb.firebaseio.com'
})

DEFAULT_DATABASE = {
    "user_amounts": {},
    "user_states": {},
    "user_balances": {},
    "user_purchases": {},
    "user_deposits": {},
    "used_txids": [],
    "user_languages": {},
    "all_users": [],
    "support_admin": "@tianpeng7777",
    "product_inventory": {
        "Telegram Protocol": {
            "type": "countries",
            "items": {
                "Bangladesh": {"code": "+880", "price": 1.50, "accounts": [], "zip_files": []},
                "India": {"code": "+91", "price": 1.20, "accounts": [], "zip_files": []},
                "Usa": {"code": "+1", "price": 3.00, "accounts": [], "zip_files": []},
                "Brazil": {"code": "+55", "price": 2.00, "accounts": [], "zip_files": []}
            }
        },
        "Telegram Premium": {"type": "direct", "price": 5.00, "accounts": []},
        "Google Voice": {"type": "sub_categories", "items": {}},
        "Gmail": {"type": "sub_categories", "items": {}},
        "VPN": {"type": "sub_categories", "items": {}}
    }
}

def load_database():
    try:
        ref = db.reference('/')
        data = ref.get()
        if not data:
            ref.set(DEFAULT_DATABASE)
            return DEFAULT_DATABASE
        return data
    except Exception as e:
        print(f"Error loading database from Firebase: {e}")
        return DEFAULT_DATABASE

def _async_save(path, data):
    try:
        db.reference(path).set(data)
    except Exception as e:
        print(f"Error saving to Firebase ({path}): {e}")

def save_database(path="/", data=None):
    if data is None:
        data = {
            "user_amounts": {str(k): v for k, v in user_amounts.items()},
            "user_states": {str(k): v for k, v in user_states.items()},
            "user_balances": {str(k): v for k, v in user_balances.items()},
            "user_purchases": {str(k): v for k, v in user_purchases.items()},
            "user_deposits": {str(k): v for k, v in user_deposits.items()},
            "used_txids": list(used_txids),
            "user_languages": {str(k): v for k, v in user_languages.items()},
            "all_users": [str(u) for u in all_users],
            "support_admin": support_admin_username,
            "product_inventory": product_inventory
        }
    threading.Thread(target=_async_save, args=(path, data), daemon=True).start()

db_data = load_database()
user_amounts = {int(k): v for k, v in db_data.get("user_amounts", {}).items()}
user_states = {int(k): v for k, v in db_data.get("user_states", {}).items()}
user_balances = {int(k): v for k, v in db_data.get("user_balances", {}).items()}

raw_purchases = db_data.get("user_purchases", {})
user_purchases = {}
for k, v in raw_purchases.items():
    uid = int(k)
    user_purchases[uid] = []
    for item in v:
        if isinstance(item, dict):
            user_purchases[uid].append(item)
        else:
            user_purchases[uid].append({"text": str(item), "timestamp": time.time()})

raw_deposits = db_data.get("user_deposits", {})
user_deposits = {}
for k, v in raw_deposits.items():
    uid = int(k)
    user_deposits[uid] = []
    for item in v:
        if isinstance(item, dict):
            user_deposits[uid].append(item)
        else:
            user_deposits[uid].append({"text": str(item), "timestamp": time.time()})

used_txids = set(db_data.get("used_txids", []))
user_languages = {int(k): v for k, v in db_data.get("user_languages", {}).items()}
all_users = set(int(u) for u in db_data.get("all_users", []))
support_admin_username = db_data.get("support_admin", "@tianpeng7777")
product_inventory = db_data.get("product_inventory", DEFAULT_DATABASE["product_inventory"])
temp_admin_data = {}

def background_cleanup_job():
    while True:
        try:
            now = time.time()
            thirty_hours_seconds = 30 * 60 * 60
            updated = False
            for uid in list(user_purchases.keys()):
                filtered_purchases = [p for p in user_purchases[uid] if (now - p.get("timestamp", now)) < thirty_hours_seconds]
                if len(filtered_purchases) != len(user_purchases[uid]):
                    user_purchases[uid] = filtered_purchases
                    updated = True
            for uid in list(user_deposits.keys()):
                filtered_deposits = [d for d in user_deposits[uid] if (now - d.get("timestamp", now)) < thirty_hours_seconds]
                if len(filtered_deposits) != len(user_deposits[uid]):
                    user_deposits[uid] = filtered_deposits
                    updated = True
            if updated:
                save_database()
                print("Old history older than 30 hours successfully cleaned up.")
        except Exception as e:
            print(f"Error in background cleanup job: {e}")
        time.sleep(86400)

LANG = {
    "en": {
        "welcome": "Welcome, {user_name}.\n\n────────────────────────\n◆ **OUR BUSINESS** ◆\nAll kinds of daily needs, digital and physical products — wholesale / retail!\n\n‣ **First time buying from us?** Please purchase a small test batch before ordering in bulk, to avoid unnecessary disputes. Thank you for your cooperation!\n\n‣ **Disclaimer:** All products are verified for quality and testing purposes only, not for any illegal activity. Please comply with your local laws and regulations.\n────────────────────────\n‣ Use the menu below to get started.",
        "dashboard": "📊 **Dashboard & Price List**\n\nHere is the current inventory and price list of all products:",
        "products": "📁 **Select a product category:**",
        "account": "◆ **ACCOUNT**\n────────────────────────\nUser ID  ·  `{user_id}`\nUsername  ·  {username}\nBalance  ·  ${balance:.2f}\nPurchased  ·  {purchased_total}",
        "deposit": "Select amount (USDT):",
        "history": "目 **HISTORY MENU**\n──────────────────────\nPlease select which history you want to view:",
        "support": "📞 **Support Center**\n\nFor any help, issues or assistance, please contact our support admin:\n👉 {support_user}",
        "search": "🔍 **Search Products**\n\nEnter product name, country, or phone code (e.g., USA, Bangladesh, +880):",
        "language": "🌐 **Language Settings / 语言设置**\n\nPlease select your preferred language:",
        "admin": "🛠️ **Welcome to Admin Panel**\n\nChoose an option below:",
        "menu_dashboard": "📊 Dashboard",
        "menu_products": "◆ Products",
        "menu_account": "◆ My Account",
        "menu_deposit": "▲ Deposit",
        "menu_history": "目 History",
        "menu_support": "Support",
        "menu_lang": "🌐 Language",
        "menu_search": "🔍 Search",
        "menu_admin": "🛠️ Admin Panel",
        "select_qty": "🔢 **Select Quantity:**\n\nChoose how many items you want to buy:",
        "select_country": "🌍 **Select a country & phone code:**",
        "back": "< Back",
        "main_menu": "< Main Menu",
        "other_amt": "Other Amount",
        "cancel": "< Cancel",
        "stock": "Stock"
    },
    "zh": {
        "welcome": "欢迎, {user_name}。\n\n────────────────────────\n◆ **我们的业务** ◆\n各种日常需求、数字和实体产品——批发/零售！\n\n‣ **第一次在我们这里购买？** 批量订购前请购买小额测试批次，以免产生不必要的纠纷。感谢您的合作！\n\n‣ **免责声明：** 所有产品均经过质量和测试目的验证，不得用于任何非法活动。请遵守您当地的法律法规。\n────────────────────────\n‣ 使用下方的菜单开始。",
        "dashboard": "📊 **仪表盘与价格表**\n\n以下是所有产品的当前库存和价格表：",
        "products": "📁 **选择产品类别：**",
        "account": "◆ **账户信息**\n────────────────────────\n用户 ID  ·  `{user_id}`\n用户名  ·  {username}\n余额  ·  ${balance:.2f}\n已购总额  ·  ${purchased_total}",
        "deposit": "选择金额 (USDT)：",
        "history": "目 **历史记录菜单**\n──────────────────────\n请选择您要查看的历史记录类型：",
        "support": "📞 **支持中心**\n\n如有任何帮助、问题或协助，请直接联系我们的支持管理员：\n👉 {support_user}",
        "search": "🔍 **搜索产品**\n\n输入产品名称、国家或电话区号（例如：USA, Bangladesh, +880）：",
        "language": "🌐 **语言设置 / Language Settings**\n\n请选择您的首选语言：",
        "admin": "🛠️ **欢迎来到管理面板**\n\n在下方选择一个选项：",
        "menu_dashboard": "📊 仪表盘",
        "menu_products": "◆ 产品中心",
        "menu_account": "◆ 我的账户",
        "menu_deposit": "▲ 充值",
        "menu_history": "目 历史记录",
        "menu_support": "客服支持",
        "menu_lang": "🌐 语言设置",
        "menu_search": "🔍 搜索产品",
        "menu_admin": "🛠️ 管理面板",
        "select_qty": "🔢 **选择数量：**\n\n请选择您要购买的数量：",
        "select_country": "🌍 **选择国家及电话区号：**",
        "back": "< 返回",
        "main_menu": "< 主菜单",
        "other_amt": "其他金额",
        "cancel": "< 取消",
        "stock": "库存"
    }
}

def get_lang(user_id):
    return user_languages.get(user_id, "en")

def set_bot_commands(bot_instance):
    commands = [telebot.types.BotCommand("/start", "Re-start Bot & Open Menu")]
    bot_instance.set_my_commands(commands)

def get_main_menu_keyboard(user_id):
    lang_code = get_lang(user_id)
    t = LANG[lang_code]
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton(t["menu_dashboard"]),
        types.KeyboardButton(t["menu_products"]),
        types.KeyboardButton(t["menu_account"]),
        types.KeyboardButton(t["menu_deposit"]),
        types.KeyboardButton(t["menu_history"]),
        types.KeyboardButton(t["menu_support"]),
        types.KeyboardButton(t["menu_lang"]),
        types.KeyboardButton(t["menu_search"])
    )
    if is_admin(user_id):
        markup.add(types.KeyboardButton(t["menu_admin"]))
    return markup

def get_select_amount_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("2", callback_data="amt_2"),
        types.InlineKeyboardButton("3", callback_data="amt_3"),
        types.InlineKeyboardButton("10", callback_data="amt_10"),
        types.InlineKeyboardButton("20", callback_data="amt_20"),
        types.InlineKeyboardButton("50", callback_data="amt_50"),
        types.InlineKeyboardButton("100", callback_data="amt_100"),
        types.InlineKeyboardButton(t["other_amt"], callback_data="amt_other"),
        types.InlineKeyboardButton(t["cancel"], callback_data="dep_cancel")
    )
    return markup

def get_payment_methods_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💛 Binance UID (Min $2)", callback_data="pay_binance"),
        types.InlineKeyboardButton("💎 Tron Network (Min $3)", callback_data="pay_tron_menu"),
        types.InlineKeyboardButton("🪙 Bsc Network (BEP20) (Min $3)", callback_data="pay_bsc_menu"),
        types.InlineKeyboardButton(t["cancel"], callback_data="dep_cancel")
    )
    return markup

def get_tron_subfolders_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💵 USDT (TRC20) — Min $3", callback_data="order_usdt_trc20"),
        types.InlineKeyboardButton("💎 TRX (Tron) — Min $3", callback_data="order_trx"),
        types.InlineKeyboardButton(t["back"], callback_data="dep_confirm")
    )
    return markup

def get_bsc_subfolders_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💵 USDT (BEP20) — Min $3", callback_data="order_usdt_bep20"),
        types.InlineKeyboardButton("🪙 BNB (BEP20) — Min $3", callback_data="order_bnb"),
        types.InlineKeyboardButton(t["back"], callback_data="dep_confirm")
    )
    return markup

def get_order_created_keyboard(net_code, order_id, user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📤 Send Order Id / TxID", callback_data=f"send_order_id_{order_id}"))
    if net_code == "tron":
        markup.add(types.InlineKeyboardButton(t["back"], callback_data="pay_tron_menu"))
    elif net_code == "bsc":
        markup.add(types.InlineKeyboardButton(t["back"], callback_data="pay_bsc_menu"))
    else:
        markup.add(types.InlineKeyboardButton(t["back"], callback_data="dep_confirm"))
    markup.add(types.InlineKeyboardButton(t["main_menu"], callback_data="go_main_menu"))
    return markup

def get_quantity_keyboard(item_key, user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("1", callback_data=f"qty_{item_key}_1"),
        types.InlineKeyboardButton("2", callback_data=f"qty_{item_key}_2"),
        types.InlineKeyboardButton("3", callback_data=f"qty_{item_key}_3"),
        types.InlineKeyboardButton("5", callback_data=f"qty_{item_key}_5"),
        types.InlineKeyboardButton("10", callback_data=f"qty_{item_key}_10"),
        types.InlineKeyboardButton("Other Quantity", callback_data=f"qty_other_{item_key}"),
        types.InlineKeyboardButton(t["back"], callback_data="back_to_products_menu")
    )
    return markup

def get_history_menu_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📦 Purchase History", callback_data="hist_purchase"),
        types.InlineKeyboardButton("💰 Deposit History", callback_data="hist_deposit"),
        types.InlineKeyboardButton(t["main_menu"], callback_data="go_main_menu")
    )
    return markup

def get_products_categories_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cat_name in product_inventory.keys():
        if cat_name == "Telegram Protocol":
            emoji = "📱"; cb = "prod_telegram_acc"
        elif cat_name == "Telegram Premium":
            emoji = "⭐"; cb = "prod_telegram_prem_support"
        elif cat_name == "Google Voice":
            emoji = "📞"; cb = f"prod_subcat_menu_{cat_name}"
        elif cat_name == "Gmail":
            emoji = "✉️"; cb = f"prod_subcat_menu_{cat_name}"
        elif cat_name == "VPN":
            emoji = "🛡️"; cb = f"prod_subcat_menu_{cat_name}"
        else:
            emoji = "📦"; cb = f"prod_subcat_menu_{cat_name}"
        markup.add(types.InlineKeyboardButton(f"{emoji} {cat_name}", callback_data=cb))
    markup.add(types.InlineKeyboardButton(t["main_menu"], callback_data="go_main_menu"))
    return markup

def get_products_countries_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    if "Telegram Protocol" in product_inventory and "items" in product_inventory["Telegram Protocol"]:
        for country, data in product_inventory["Telegram Protocol"]["items"].items():
            c_code = data.get("code", "")
            zip_stock_count = sum(len(zf.get("extracted_files", [])) for zf in data.get("zip_files", []))
            total_stock = len(data.get("accounts", [])) + zip_stock_count
            btn_text = f"🌐 {country} ({c_code}) — {t['stock']}: {total_stock}"
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"select_country_{country}"))
    markup.add(types.InlineKeyboardButton(t["back"], callback_data="back_to_products_menu"))
    return markup

def get_language_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        types.InlineKeyboardButton("🇨🇳 China (中文)", callback_data="lang_zh")
    )
    markup.add(types.InlineKeyboardButton(t["main_menu"], callback_data="go_main_menu"))
    return markup

def get_admin_panel_keyboard(user_id):
    t = LANG[get_lang(user_id)]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast_start"),
        types.InlineKeyboardButton("👥 Management (Users & Balance)", callback_data="admin_management"),
        types.InlineKeyboardButton("➕ Add New Product Category", callback_data="admin_add_category"),
        types.InlineKeyboardButton("📦 Add Stock & Price", callback_data="admin_add_accounts"),
        types.InlineKeyboardButton("✏️ Edit / Delete Categories", callback_data="admin_edit_delete_cat_menu"),
        types.InlineKeyboardButton("📞 Change Support Username", callback_data="admin_change_support"),
        types.InlineKeyboardButton(t["main_menu"], callback_data="go_main_menu")
    )
    return markup

def get_management_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    total_users = len(all_users)
    total_balance = sum(user_balances.get(int(u), 0.0) for u in all_users)
    markup.add(types.InlineKeyboardButton(f"👥 All Users List ({total_users})", callback_data="mgmt_users_0"))
    markup.add(types.InlineKeyboardButton("🔍 Search User by ID", callback_data="mgmt_search_user"))
    markup.add(types.InlineKeyboardButton("💰 Top Balance Users", callback_data="mgmt_top_balance"))
    markup.add(types.InlineKeyboardButton("🛠️ Back to Admin Panel", callback_data="admin_back"))
    return markup

def get_users_list_keyboard(page=0, per_page=10):
    markup = types.InlineKeyboardMarkup(row_width=1)
    users_sorted = sorted(list(all_users), reverse=True)
    total = len(users_sorted)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = start + per_page
    for uid in users_sorted[start:end]:
        bal = user_balances.get(int(uid), 0.0)
        crown = " 👑" if is_admin(uid) else ""
        markup.add(types.InlineKeyboardButton(f"👤 {uid}{crown} | 💰 ${bal:.2f}", callback_data=f"mgmt_user_{uid}"))
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️ Prev", callback_data=f"mgmt_users_{page-1}"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("Next ➡️", callback_data=f"mgmt_users_{page+1}"))
    if nav:
        markup.add(*nav)
    markup.add(types.InlineKeyboardButton(f"📄 Page {page+1}/{total_pages} | Total: {total}", callback_data="noop"))
    markup.add(types.InlineKeyboardButton("🔙 Back to Management", callback_data="admin_management"))
    return markup, total_pages, total

def get_user_detail_keyboard(target_uid):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add Balance", callback_data=f"mgmt_bal_add_{target_uid}"),
        types.InlineKeyboardButton("➖ Subtract Balance", callback_data=f"mgmt_bal_sub_{target_uid}"),
        types.InlineKeyboardButton("✏️ Set Balance", callback_data=f"mgmt_bal_set_{target_uid}"),
        types.InlineKeyboardButton("🔄 Reset to $0", callback_data=f"mgmt_bal_reset_{target_uid}"),
    )
    markup.add(
        types.InlineKeyboardButton("📦 Purchase History", callback_data=f"mgmt_hist_pur_{target_uid}"),
        types.InlineKeyboardButton("💰 Deposit History", callback_data=f"mgmt_hist_dep_{target_uid}"),
    )
    markup.add(types.InlineKeyboardButton("🔙 Back to Users List", callback_data="mgmt_users_0"))
    markup.add(types.InlineKeyboardButton("🛠️ Back to Admin Panel", callback_data="admin_back"))
    return markup

def get_user_detail_text(target_uid):
    bal = user_balances.get(int(target_uid), 0.0)
    pur = user_purchases.get(int(target_uid), [])
    dep = user_deposits.get(int(target_uid), [])
    lang = user_languages.get(int(target_uid), "en")
    is_adm = "Yes 👑" if is_admin(target_uid) else "No"
    text = (
        f"👤 **User Management**\n"
        f"──────────────────────\n"
        f"🆔 User ID: `{target_uid}`\n"
        f"💰 Balance: **${bal:.2f}**\n"
        f"🌐 Language: `{lang}`\n"
        f"👑 Admin: {is_adm}\n"
        f"📦 Total Purchases: `{len(pur)}`\n"
        f"💰 Total Deposits: `{len(dep)}`\n"
        f"──────────────────────\n"
        f"নিচ থেকে Balance Edit করুন:"
    )
    return text

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    all_users.add(user_id)
    save_database()
    user_name = message.from_user.first_name or "User"
    lang_code = get_lang(user_id)
    welcome_text = LANG[lang_code]["welcome"].format(user_name=user_name)
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    if is_admin(user_id):
        user_states[user_id] = "waiting_for_admin_password"
        save_database()
        bot.send_message(message.chat.id, "🔐 Please enter admin password to access Admin Panel:")
    else:
        bot.send_message(message.chat.id, "❌ You are not authorized to access the Admin Panel.")

@bot.message_handler(commands=['cancel'])
def cancel_operation(message):
    user_states.pop(message.from_user.id, None)
    save_database()
    bot.send_message(message.chat.id, "❌ Current operation cancelled.", reply_markup=get_main_menu_keyboard(message.from_user.id))

@bot.message_handler(content_types=['document'])
def handle_document_uploads(message):
    user_id = message.from_user.id
    if is_admin(user_id) and user_states.get(user_id) == "waiting_for_zip_file":
        country_name = temp_admin_data.get(user_id)
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        if country_name in product_inventory["Telegram Protocol"]["items"]:
            temp_admin_data[f"zip_bytes_{user_id}"] = list(downloaded_file)
            user_states[user_id] = "waiting_for_zip_2fa"
            response_msg = (
                f"✅ ZIP File uploaded successfully for **{country_name}**!\n\n"
                f"🔐 Now, please send the **Password / 2FA Code** for this ZIP file so it can be verified and read properly:"
            )
            bot.send_message(message.chat.id, response_msg, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ Invalid country selected.")
            user_states.pop(user_id, None)

@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'audio'])
def handle_all_messages(message):
    user_id = message.from_user.id
    all_users.add(user_id)
    if user_id not in user_balances:
        user_balances[user_id] = 0.00
    if user_id not in user_purchases:
        user_purchases[user_id] = []
    if user_id not in user_deposits:
        user_deposits[user_id] = []
    save_database()
    lang_code = get_lang(user_id)
    t = LANG[lang_code]

    if user_states.get(user_id) == "waiting_for_mgmt_search":
        if is_admin(user_id):
            user_states.pop(user_id, None)
            save_database()
            try:
                target = int(message.text.strip())
            except:
                bot.send_message(message.chat.id, "❌ Invalid User ID! শুধু সংখ্যা দিন, যেমন: `123456789`", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
                return
            if target not in all_users:
                all_users.add(target)
                if target not in user_balances:
                    user_balances[target] = 0.0
                save_database()
            bot.send_message(message.chat.id, get_user_detail_text(target), parse_mode="Markdown", reply_markup=get_user_detail_keyboard(target))
        return

    if user_states.get(user_id, "").startswith("waiting_for_mgmt_bal_"):
        if is_admin(user_id):
            state = user_states.get(user_id)
            parts = state.replace("waiting_for_mgmt_bal_", "").split("_")
            action = parts[0]
            target_uid = int(parts[1])
            try:
                amount = float(message.text.strip())
            except:
                bot.send_message(message.chat.id, "❌ Invalid amount! যেমন: `10` বা `5.50` দিন")
                return
            old_bal = user_balances.get(target_uid, 0.0)
            if action == "add":
                new_bal = old_bal + amount
                msg_action = f"➕ Added ${amount:.2f}"
            elif action == "sub":
                new_bal = old_bal - amount
                if new_bal < 0:
                    new_bal = 0.0
                msg_action = f"➖ Subtracted ${amount:.2f}"
            elif action == "set":
                new_bal = amount
                msg_action = f"✏️ Set to ${amount:.2f}"
            else:
                new_bal = old_bal
                msg_action = ""
            user_balances[target_uid] = round(new_bal, 2)
            user_states.pop(user_id, None)
            save_database()
            bot.send_message(
                message.chat.id,
                f"✅ **Balance Updated!**\n\n👤 User ID: `{target_uid}`\n{msg_action}\n💰 Old Balance: `${old_bal:.2f}`\n💰 New Balance: **${new_bal:.2f}**",
                parse_mode="Markdown", reply_markup=get_user_detail_keyboard(target_uid)
            )
            try:
                bot.send_message(target_uid, f"💰 **Your balance has been updated by Admin!**\n\nNew Balance: **${new_bal:.2f}**", parse_mode="Markdown")
            except:
                pass
        return

    if user_states.get(user_id) == "waiting_for_admin_password":
        if is_admin(user_id):
            entered_pass = message.text.strip()
            user_states.pop(user_id, None)
            save_database()
            if entered_pass == ADMIN_PASSWORD:
                bot.send_message(message.chat.id, "✅ Password correct!\n\n" + t["admin"], parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            else:
                bot.send_message(message.chat.id, "❌ Incorrect password! Access denied.", reply_markup=get_main_menu_keyboard(user_id))
        return

    if user_states.get(user_id) == "waiting_for_new_support_username":
        if is_admin(user_id):
            global support_admin_username
            new_support = message.text.strip()
            if not new_support.startswith("@"):
                new_support = "@" + new_support
            support_admin_username = new_support
            user_states.pop(user_id, None)
            save_database()
            bot.send_message(message.chat.id, f"✅ Support admin username successfully updated to: **{support_admin_username}**", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
        return

    if user_states.get(user_id) == "waiting_for_new_category_name":
        if is_admin(user_id):
            new_cat_name = message.text.strip()
            if new_cat_name in product_inventory:
                bot.send_message(message.chat.id, f"⚠️ Category **{new_cat_name}** already exists!")
            else:
                product_inventory[new_cat_name] = {"type": "sub_categories", "items": {}}
                save_database()
                bot.send_message(message.chat.id, f"✅ Successfully added new product category: **{new_cat_name}**", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            user_states.pop(user_id, None)
            save_database()
        return

    if user_states.get(user_id, "").startswith("waiting_for_protocol_price_"):
        if is_admin(user_id):
            country_name = user_states.get(user_id).replace("waiting_for_protocol_price_", "")
            try:
                new_price = float(message.text.strip())
                if country_name in product_inventory["Telegram Protocol"]["items"]:
                    product_inventory["Telegram Protocol"]["items"][country_name]["price"] = new_price
                    save_database()
                    bot.send_message(message.chat.id, f"✅ Successfully updated price for **{country_name}** to **${new_price:.2f}**!", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
                else:
                    bot.send_message(message.chat.id, "❌ Country not found.")
            except ValueError:
                bot.send_message(message.chat.id, "❌ Invalid price! Please enter a valid number (e.g., `1.50`).")
            user_states.pop(user_id, None)
            save_database()
        return

    if user_states.get(user_id, "").startswith("waiting_for_rename_country_"):
        if is_admin(user_id):
            old_country = user_states.get(user_id).replace("waiting_for_rename_country_", "")
            new_country = message.text.strip().capitalize()
            proto_items = product_inventory["Telegram Protocol"]["items"]
            if new_country in proto_items:
                bot.send_message(message.chat.id, f"⚠️ Country **{new_country}** already exists!")
            elif old_country in proto_items:
                proto_items[new_country] = proto_items.pop(old_country)
                save_database()
                bot.send_message(message.chat.id, f"✅ Successfully renamed country **{old_country}** to **{new_country}**!", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            else:
                bot.send_message(message.chat.id, "❌ Country not found.")
            user_states.pop(user_id, None)
            save_database()
        return

    if user_states.get(user_id, "").startswith("waiting_for_subcat_name_"):
        if is_admin(user_id):
            parent_cat = user_states.get(user_id).replace("waiting_for_subcat_name_", "")
            sub_name = message.text.strip()
            if parent_cat in product_inventory:
                if "items" not in product_inventory[parent_cat]:
                    product_inventory[parent_cat]["items"] = {}
                if sub_name in product_inventory[parent_cat]["items"]:
                    bot.send_message(message.chat.id, f"⚠️ Sub-folder **{sub_name}** already exists inside {parent_cat}!")
                else:
                    product_inventory[parent_cat]["items"][sub_name] = {"price": 1.00, "accounts": []}
                    save_database()
                    bot.send_message(message.chat.id, f"✅ Successfully created sub-folder **{sub_name}** inside **{parent_cat}**!", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            user_states.pop(user_id, None)
            save_database()
        return

    if user_states.get(user_id, "").startswith("waiting_for_rename_cat_"):
        if is_admin(user_id):
            old_name = user_states.get(user_id).replace("waiting_for_rename_cat_", "")
            new_name = message.text.strip()
            if new_name in product_inventory:
                bot.send_message(message.chat.id, f"⚠️ Category **{new_name}** already exists!")
            elif old_name in product_inventory:
                product_inventory[new_name] = product_inventory.pop(old_name)
                save_database()
                bot.send_message(message.chat.id, f"✅ Successfully renamed **{old_name}** to **{new_name}**!", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            else:
                bot.send_message(message.chat.id, "❌ Category not found.")
            user_states.pop(user_id, None)
            save_database()
        return

    if user_states.get(user_id, "").startswith("waiting_for_rename_subcat_"):
        if is_admin(user_id):
            parts = user_states.get(user_id).replace("waiting_for_rename_subcat_", "").split("___")
            parent_cat = parts[0]
            old_sub = parts[1]
            new_sub = message.text.strip()
            if parent_cat in product_inventory and "items" in product_inventory[parent_cat]:
                if new_sub in product_inventory[parent_cat]["items"]:
                    bot.send_message(message.chat.id, f"⚠️ Sub-folder **{new_sub}** already exists!")
                elif old_sub in product_inventory[parent_cat]["items"]:
                    product_inventory[parent_cat]["items"][new_sub] = product_inventory[parent_cat]["items"].pop(old_sub)
                    save_database()
                    bot.send_message(message.chat.id, f"✅ Successfully renamed sub-folder **{old_sub}** to **{new_sub}**!", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
                else:
                    bot.send_message(message.chat.id, "❌ Sub-folder not found.")
            user_states.pop(user_id, None)
            save_database()
        return

    if user_states.get(user_id) == "waiting_for_accounts_input":
        if is_admin(user_id):
            target_key = temp_admin_data.get(user_id)
            parent_cat = temp_admin_data.get(f"parent_{user_id}")
            lines = message.text.split("\n")
            try:
                price_val = float(lines[0].replace("Price:", "").strip())
                added_count = 0
                if parent_cat and parent_cat in product_inventory:
                    target_dict = product_inventory[parent_cat]["items"][target_key]
                else:
                    target_dict = product_inventory[target_key]
                target_dict["price"] = price_val
                if "accounts" not in target_dict:
                    target_dict["accounts"] = []
                for line in lines[1:]:
                    if line.strip():
                        acc_info = line.strip()
                        target_dict["accounts"].append({"number": acc_info, "2fa": "Included in Details"})
                        added_count += 1
                save_database()
                bot.send_message(message.chat.id, f"✅ Successfully updated **{target_key}**!\n💰 Price: ${price_val:.2f}\n📦 Added Items: {added_count}", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            except Exception:
                bot.send_message(message.chat.id, "❌ Format error! First line must be price (e.g., `2.50`) and following lines should be account details.")
            user_states.pop(user_id, None)
            temp_admin_data.pop(user_id, None)
            temp_admin_data.pop(f"parent_{user_id}", None)
            save_database()
        return

    if user_states.get(user_id) == "waiting_for_broadcast_message":
        if is_admin(user_id):
            user_states.pop(user_id, None)
            success_count = 0
            fail_count = 0
            bot.send_message(message.chat.id, "⏳ Broadcasting message to all users, please wait...")
            for uid in all_users:
                if is_admin(uid):
                    continue
                try:
                    bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
                    success_count += 1
                except Exception:
                    fail_count += 1
            save_database()
            bot.send_message(message.chat.id, f"✅ **Broadcast Completed!**\n\n👥 Successfully sent: `{success_count}` users\n❌ Failed (Blocked bot): `{fail_count}` users", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        return

    if user_states.get(user_id) == "waiting_for_search_query":
        query = message.text.strip().lower() if message.text else ""
        user_states.pop(user_id, None)
        save_database()
        markup = types.InlineKeyboardMarkup(row_width=1)
        found_any = False
        for country, data in product_inventory["Telegram Protocol"]["items"].items():
            if query in country.lower() or query in data.get("code", "").lower():
                zip_stock_count = sum(len(zf.get("extracted_files", [])) for zf in data.get("zip_files", []))
                stock_count = len(data.get("accounts", [])) + zip_stock_count
                price = data.get("price", 1.00)
                markup.add(types.InlineKeyboardButton(f"🌐 {country} ({data.get('code', '')}) — Price: ${price:.2f} | Stock: {stock_count}", callback_data=f"select_country_{country}"))
                found_any = True
        for p_name, p_data in product_inventory.items():
            if p_name != "Telegram Protocol" and query in p_name.lower():
                if p_data.get("type") == "sub_categories" or "items" in p_data:
                    for sub_name in p_data.get("items", {}).keys():
                        if query in sub_name.lower():
                            markup.add(types.InlineKeyboardButton(f"📂 {p_name} -> {sub_name}", callback_data=f"prod_sub_buy_{p_name}_{sub_name}"))
                            found_any = True
                else:
                    stock_count = len(p_data.get("accounts", []))
                    price = p_data.get("price", 1.00)
                    markup.add(types.InlineKeyboardButton(f"📦 {p_name} — Price: ${price:.2f} | Stock: {stock_count}", callback_data=f"prod_custom_{p_name}"))
                    found_any = True
        if found_any:
            markup.add(types.InlineKeyboardButton(t["main_menu"], callback_data="go_main_menu"))
            bot.send_message(message.chat.id, f"🔍 **Search Results for '{query}':**", parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, f"❌ No products or countries found matching '{query}'.", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        return

    if user_states.get(user_id) == "waiting_for_new_country":
        if is_admin(user_id):
            c_name = message.text.strip().capitalize()
            if c_name not in product_inventory["Telegram Protocol"]["items"]:
                temp_admin_data[user_id] = c_name
                user_states[user_id] = "waiting_for_country_code"
                save_database()
                bot.send_message(message.chat.id, f"📱 Now enter country phone code for **{c_name}** (e.g., `+880`):", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, f"⚠️ Country **{c_name}** already exists.")
                user_states.pop(user_id, None)
                save_database()
        return

    if user_states.get(user_id) == "waiting_for_country_code":
        if is_admin(user_id):
            c_code = message.text.strip()
            c_name = temp_admin_data.get(user_id)
            if c_name:
                product_inventory["Telegram Protocol"]["items"][c_name] = {"code": c_code, "price": 1.00, "accounts": [], "zip_files": []}
                save_database()
                bot.send_message(message.chat.id, f"✅ Country **{c_name} ({c_code})** added successfully!", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            user_states.pop(user_id, None)
            save_database()
        return

    if user_states.get(user_id, "").startswith("waiting_for_custom_qty_"):
        item_key = user_states.get(user_id).replace("waiting_for_custom_qty_", "")
        parts = item_key.split("___")
        if len(parts) == 2:
            p_cat, s_item = parts
            qty_key = f"{p_cat}___{s_item}"
        else:
            qty_key = item_key
        try:
            qty = int(message.text.strip())
            if qty <= 0:
                bot.send_message(message.chat.id, "❌ Please enter a valid quantity greater than 0:")
                return
            user_states.pop(user_id, None)
            save_database()
            process_product_purchase(message.chat.id, user_id, qty_key, qty)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Invalid number! Please enter a valid integer (e.g., 2, 5):")
        return

    if user_states.get(user_id) == "waiting_for_custom_amount":
        try:
            custom_amount = float(message.text.strip())
            selected_method = user_states.get("current_method", "general")
            min_limit = 2.00 if selected_method == "binance" else 3.00
            if custom_amount < min_limit:
                bot.send_message(message.chat.id, f"❌ Minimum deposit amount is ${min_limit:.2f}. Please enter again:")
                return
            user_amounts[user_id] = custom_amount
            user_states[user_id] = "waiting_for_payment_method"
            save_database()
            payment_text = f"💰 **Selected Amount:** ${custom_amount:.2f}\n\nPlease select your preferred payment method:"
            bot.send_message(message.chat.id, payment_text, parse_mode="Markdown", reply_markup=get_payment_methods_keyboard(user_id))
        except ValueError:
            bot.send_message(message.chat.id, "❌ Invalid amount. Please enter a valid number (e.g., 5 or 10):")
        return

    if user_states.get(user_id) == "waiting_for_payment_proof":
        proof_text = message.text.strip() if message.text else "Media Proof"
        if proof_text in used_txids:
            bot.send_message(message.chat.id, "❌ **This Order ID / TxID has already been used!** Each ID can only be used once for a deposit.", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
            user_states.pop(user_id, None)
            temp_admin_data.pop(f"order_info_{user_id}", None)
            return
        order_data = temp_admin_data.get(f"order_info_{user_id}", {})
        order_id = order_data.get("order_id", "N/A")
        method_name = order_data.get("method", "General Deposit")
        current_amount = user_amounts.get(user_id, 2.00)
        admin_alert = (
            f"🔔 **New Deposit Verification Request!**\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"💳 Method: **{method_name}**\n"
            f"💵 Amount to Credit: `${current_amount:.2f}`\n"
            f"🔖 Order ID: `{order_id}`\n"
            f"📝 User Proof / TxID: `{proof_text}`"
        )
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Accept Deposit", callback_data=f"dep_accept_{user_id}_{current_amount}_{proof_text}"),
            types.InlineKeyboardButton("❌ Reject Deposit", callback_data=f"dep_reject_{user_id}_{current_amount}")
        )
        for adm in ADMIN_IDS:
            try:
                bot.send_message(adm, admin_alert, parse_mode="Markdown", reply_markup=admin_markup)
                if message.content_type != 'text':
                    bot.copy_message(chat_id=adm, from_chat_id=message.chat.id, message_id=message.message_id)
            except Exception:
                pass
        bot.send_message(message.chat.id, "📤 Your payment proof / Order ID has been sent to the admin successfully. Please wait for verification.", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        user_states.pop(user_id, None)
        temp_admin_data.pop(f"order_info_{user_id}", None)
        save_database()
        return

    if user_states.get(user_id) == "waiting_for_zip_2fa":
        if is_admin(user_id):
            tfa_code = message.text.strip() if message.text else ""
            country_name = temp_admin_data.get(user_id)
            zip_bytes_list = temp_admin_data.get(f"zip_bytes_{user_id}")
            if country_name and zip_bytes_list and tfa_code:
                zip_bytes = io.BytesIO(bytes(zip_bytes_list))
                try:
                    with pyzipper.AESZipFile(zip_bytes, 'r') as zf:
                        zf.setpassword(tfa_code.encode('utf-8'))
                        file_list = zf.namelist()
                        valid_files = [f for f in file_list if not f.endswith('/')]
                        if "zip_files" not in product_inventory["Telegram Protocol"]["items"][country_name]:
                            product_inventory["Telegram Protocol"]["items"][country_name]["zip_files"] = []
                        product_inventory["Telegram Protocol"]["items"][country_name]["zip_files"].append({
                            "zip_bytes": zip_bytes_list,
                            "2fa": tfa_code,
                            "extracted_files": valid_files
                        })
                        save_database()
                        bot.send_message(message.chat.id, f"✅ Successfully added ZIP stock for **{country_name}**!\n📁 Total valid files: `{len(valid_files)}`\n🔐 Password / 2FA: `{tfa_code}`", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
                except Exception as e:
                    bot.send_message(message.chat.id, f"❌ **Password Error!** The password you provided is incorrect or the ZIP file is corrupted.\nError details: `{str(e)}`\nPlease upload the ZIP file again and enter the correct password.", parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            user_states.pop(user_id, None)
            temp_admin_data.pop(user_id, None)
            temp_admin_data.pop(f"zip_bytes_{user_id}", None)
        return

    text = message.text if message.text else ""
    
    # Check menu button clicks by matching with both English and Chinese keys
    is_dashboard = text in [LANG["en"]["menu_dashboard"], LANG["zh"]["menu_dashboard"]]
    is_products = text in [LANG["en"]["menu_products"], LANG["zh"]["menu_products"]]
    is_account = text in [LANG["en"]["menu_account"], LANG["zh"]["menu_account"]]
    is_deposit = text in [LANG["en"]["menu_deposit"], LANG["zh"]["menu_deposit"]]
    is_history = text in [LANG["en"]["menu_history"], LANG["zh"]["menu_history"]]
    is_support = text in [LANG["en"]["menu_support"], LANG["zh"]["menu_support"]]
    is_lang = text in [LANG["en"]["menu_lang"], LANG["zh"]["menu_lang"]]
    is_search = text in [LANG["en"]["menu_search"], LANG["zh"]["menu_search"]]
    is_admin_menu = text in [LANG["en"]["menu_admin"], LANG["zh"]["menu_admin"]]

    if any([is_dashboard, is_products, is_account, is_deposit, is_history, is_support, is_lang, is_search, is_admin_menu]):
        user_states.pop(user_id, None)
        save_database()

    if is_admin_menu:
        if is_admin(user_id):
            user_states[user_id] = "waiting_for_admin_password"
            save_database()
            bot.send_message(message.chat.id, "🔐 Please enter admin password to access Admin Panel:")
        else:
            bot.send_message(message.chat.id, "❌ Access denied.")
        return
    elif is_dashboard:
        dashboard_text = t["dashboard"] + "\n\n"
        for cat_name, cat_data in product_inventory.items():
            dashboard_text += f"📂 **{cat_name}**\n"
            if cat_name == "Telegram Protocol" and "items" in cat_data:
                for c_name, c_info in cat_data["items"].items():
                    zip_st = sum(len(zf.get("extracted_files", [])) for zf in c_info.get("zip_files", []))
                    total_st = len(c_info.get("accounts", [])) + zip_st
                    dashboard_text += f"  • {c_name} ({c_info.get('code', '')}) — Price: ${c_info.get('price', 1.00):.2f} | {t['stock']}: {total_st}\n"
            elif "items" in cat_data:
                for sub_n, sub_inf in cat_data["items"].items():
                    sub_st = len(sub_inf.get("accounts", []))
                    dashboard_text += f"  • {sub_n} — Price: ${sub_inf.get('price', 1.00):.2f} | {t['stock']}: {sub_st}\n"
            elif "price" in cat_data:
                st_count = len(cat_data.get("accounts", []))
                dashboard_text += f"  • Price: ${cat_data.get('price', 1.00):.2f} | {t['stock']}: {st_count}\n"
            dashboard_text += "\n"
        bot.send_message(message.chat.id, dashboard_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
    elif is_products:
        bot.send_message(message.chat.id, t["products"], parse_mode="Markdown", reply_markup=get_products_categories_keyboard(user_id))
    elif is_deposit:
        user_states[user_id] = "waiting_for_deposit"
        save_database()
        bot.send_message(message.chat.id, t["deposit"], parse_mode="Markdown", reply_markup=get_select_amount_keyboard(user_id))
    elif is_history:
        bot.send_message(message.chat.id, t["history"], parse_mode="Markdown", reply_markup=get_history_menu_keyboard(user_id))
    elif is_account:
        user = message.from_user
        username = f"@{user.username}" if user.username else "N/A"
        balance_val = user_balances.get(user_id, 0.00)
        purchased_total = len(user_purchases.get(user_id, []))
        account_text = t["account"].format(user_id=user.id, username=username, balance=balance_val, purchased_total=purchased_total)
        bot.send_message(message.chat.id, account_text, parse_mode="Markdown")
    elif is_lang:
        bot.send_message(message.chat.id, t["language"], parse_mode="Markdown", reply_markup=get_language_keyboard(user_id))
    elif is_search:
        user_states[user_id] = "waiting_for_search_query"
        save_database()
        bot.send_message(message.chat.id, t["search"], parse_mode="Markdown")
    elif is_support:
        support_msg = t["support"].format(support_user=support_admin_username)
        bot.send_message(message.chat.id, support_msg, parse_mode="Markdown")

def process_product_purchase(chat_id, user_id, item_key, qty):
    is_protocol = item_key in product_inventory["Telegram Protocol"]["items"] if "Telegram Protocol" in product_inventory else False
    parts = item_key.split("___") if "___" in item_key else []
    is_sub = len(parts) == 2
    if is_protocol:
        c_data = product_inventory["Telegram Protocol"]["items"][item_key]
        price_per_unit = c_data.get("price", 1.00)
        zip_list = c_data.get("zip_files", [])
        accounts_list = c_data.get("accounts", [])
    elif is_sub:
        p_cat, s_item = parts
        c_data = product_inventory[p_cat]["items"][s_item]
        price_per_unit = c_data.get("price", 1.00)
        zip_list = []
        accounts_list = c_data.get("accounts", [])
    else:
        if item_key not in product_inventory:
            bot.send_message(chat_id, "❌ Product not found.")
            return
        c_data = product_inventory[item_key]
        price_per_unit = c_data.get("price", 1.00)
        zip_list = []
        accounts_list = c_data.get("accounts", [])
    zip_total_files = sum(len(zf.get("extracted_files", [])) for zf in zip_list)
    total_stock = len(accounts_list) + zip_total_files
    if total_stock < qty:
        bot.send_message(chat_id, f"❌ Insufficient stock! Available stock: {total_stock} items.", reply_markup=get_main_menu_keyboard(user_id))
        return
    total_price = price_per_unit * qty
    user_balance = user_balances.get(user_id, 0.00)
    if user_balance < total_price:
        bot.send_message(chat_id, f"❌ Insufficient balance!\nRequired: ${total_price:.2f}\nYour Balance: ${user_balance:.2f}\nPlease deposit first.", reply_markup=get_main_menu_keyboard(user_id))
        return
    user_balances[user_id] = user_balance - total_price
    if is_protocol:
        for _ in range(qty):
            while len(zip_list) > 0 and len(zip_list[0].get("extracted_files", [])) == 0:
                zip_list.pop(0)
            if len(zip_list) > 0:
                zip_item = zip_list[0]
                orig_zip_bytes = bytes(zip_item["zip_bytes"])
                tfa_code = zip_item["2fa"]
                files_in_zip = zip_item["extracted_files"]
                target_file_name = files_in_zip.pop(0)
                single_zip_buffer = io.BytesIO()
                with pyzipper.AESZipFile(single_zip_buffer, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as new_zip:
                    new_zip.setpassword(tfa_code.encode('utf-8'))
                    with pyzipper.AESZipFile(io.BytesIO(orig_zip_bytes), 'r') as orig_zip:
                        orig_zip.setpassword(tfa_code.encode('utf-8'))
                        file_data = orig_zip.read(target_file_name)
                        new_zip.writestr(os.path.basename(target_file_name), file_data)
                single_zip_buffer.seek(0)
                if len(files_in_zip) == 0:
                    zip_list.pop(0)
                purchase_text = f"Bought {item_key} Protocol (ZIP file) for ${price_per_unit:.2f}"
                if user_id not in user_purchases:
                    user_purchases[user_id] = []
                user_purchases[user_id].append({"text": purchase_text, "timestamp": time.time()})
                save_database()
                file_short_name = os.path.basename(target_file_name)
                bot.send_document(chat_id, document=single_zip_buffer, visible_file_name=f"{item_key}_{file_short_name}.zip", caption=f"✅ **Purchase Successful!**\n\n🌍 Country: {item_key}\n📦 File: `{file_short_name}`\n🔐 2FA & ZIP Password: `{tfa_code}`\n💵 Paid: ${price_per_unit:.2f}\n\nRemaining Balance: ${user_balances[user_id]:.2f}", parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
            elif len(accounts_list) > 0:
                purchased_item = accounts_list.pop(0)
                acc_num = purchased_item.get("number", "N/A")
                acc_2fa = purchased_item.get("2fa", "N/A")
                purchase_text = f"Bought {item_key}: `{acc_num}` for ${price_per_unit:.2f}"
                if user_id not in user_purchases:
                    user_purchases[user_id] = []
                user_purchases[user_id].append({"text": purchase_text, "timestamp": time.time()})
                save_database()
                success_text = f"✅ **Purchase Successful!**\n\n🌍 Country: {item_key}\n📱 Telegram Number: `{acc_num}`\n🔐 2FA Code: `{acc_2fa}`\n💵 Paid: ${price_per_unit:.2f}\n\nRemaining Balance: ${user_balances[user_id]:.2f}"
                bot.send_message(chat_id, success_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        save_database()
    elif is_sub:
        p_cat, s_item = parts
        sub_dict = product_inventory[p_cat]["items"][s_item]
        for _ in range(qty):
            if len(sub_dict.get("accounts", [])) > 0:
                item = sub_dict["accounts"].pop(0)
                num = item.get("number", "N/A")
                purchase_text = f"Bought {p_cat} -> {s_item}: `{num}` for ${price_per_unit:.2f}"
                if user_id not in user_purchases:
                    user_purchases[user_id] = []
                user_purchases[user_id].append({"text": purchase_text, "timestamp": time.time()})
                save_database()
                success_text = f"✅ **Purchase Successful!**\n\n📦 Product: {p_cat} -> {s_item}\n🔑 Account / Details:\n`{num}`\n\n💵 Paid: ${price_per_unit:.2f}\n\nRemaining Balance: ${user_balances[user_id]:.2f}"
                bot.send_message(chat_id, success_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        save_database()
    else:
        for _ in range(qty):
            if len(accounts_list) > 0:
                item = accounts_list.pop(0)
                num = item.get("number", "N/A")
                purchase_text = f"Bought {item_key}: `{num}` for ${price_per_unit:.2f}"
                if user_id not in user_purchases:
                    user_purchases[user_id] = []
                user_purchases[user_id].append({"text": purchase_text, "timestamp": time.time()})
                save_database()
                success_text = f"✅ **Purchase Successful!**\n\n📦 Product: {item_key}\n🔑 Account / Details:\n`{num}`\n\n💵 Paid: ${price_per_unit:.2f}\n\nRemaining Balance: ${user_balances[user_id]:.2f}"
                bot.send_message(chat_id, success_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard(user_id))
        save_database()

@bot.callback_query_handler(func=lambda call: True)
def handle_inline_clicks(call):
    user_id = call.from_user.id
    all_users.add(user_id)
    if user_id not in user_balances:
        user_balances[user_id] = 0.00
    if user_id not in user_purchases:
        user_purchases[user_id] = []
    if user_id not in user_deposits:
        user_deposits[user_id] = []
    save_database()
    lang_code = get_lang(user_id)
    t = LANG[lang_code]

    if call.data == "admin_management":
        if is_admin(user_id):
            bot.answer_callback_query(call.id, "Management")
            total_users = len(all_users)
            total_bal = sum(user_balances.get(int(u), 0.0) for u in all_users)
            text = (
                f"👥 **Management**\n"
                f"──────────────────────\n"
                f"👥 Total Users: `{total_users}`\n"
                f"💰 Total Balance in System: **${total_bal:.2f}**\n"
                f"──────────────────────\n"
                f"নিচ থেকে User List / Search করুন:"
            )
            try:
                bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_management_keyboard(user_id))
            except:
                bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=get_management_keyboard(user_id))
        return

    if call.data.startswith("mgmt_users_"):
        if is_admin(user_id):
            try:
                page = int(call.data.replace("mgmt_users_", ""))
            except:
                page = 0
            bot.answer_callback_query(call.id, f"Page {page+1}")
            markup, total_pages, total = get_users_list_keyboard(page)
            text = f"👥 **All Users List**\n──────────────────────\nTotal Users: `{total}`\nকোনো User এ ক্লিক করে Balance Edit করুন:"
            try:
                bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except:
                pass
        return

    if call.data == "mgmt_search_user":
        if is_admin(user_id):
            user_states[user_id] = "waiting_for_mgmt_search"
            save_database()
            bot.answer_callback_query(call.id, "Search User")
            try:
                bot.edit_message_text("🔍 **Search User**\n\nUser ID পাঠান (যেমন: `123456789`):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except:
                pass
        return

    if call.data == "mgmt_top_balance":
        if is_admin(user_id):
            bot.answer_callback_query(call.id, "Top Balance")
            top = sorted(all_users, key=lambda u: user_balances.get(int(u), 0.0), reverse=True)[:10]
            markup = types.InlineKeyboardMarkup(row_width=1)
            for uid in top:
                bal = user_balances.get(int(uid), 0.0)
                markup.add(types.InlineKeyboardButton(f"👤 {uid} | 💰 ${bal:.2f}", callback_data=f"mgmt_user_{uid}"))
            markup.add(types.InlineKeyboardButton("🔙 Back to Management", callback_data="admin_management"))
            try:
                bot.edit_message_text("💰 **Top 10 Balance Users:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except:
                pass
        return

    if call.data.startswith("mgmt_user_"):
        if is_admin(user_id):
            target_uid = int(call.data.replace("mgmt_user_", ""))
            bot.answer_callback_query(call.id, f"User {target_uid}")
            try:
                bot.edit_message_text(get_user_detail_text(target_uid), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_user_detail_keyboard(target_uid))
            except:
                bot.send_message(call.message.chat.id, get_user_detail_text(target_uid), parse_mode="Markdown", reply_markup=get_user_detail_keyboard(target_uid))
        return

    if call.data.startswith("mgmt_bal_add_") or call.data.startswith("mgmt_bal_sub_") or call.data.startswith("mgmt_bal_set_"):
        if is_admin(user_id):
            rest = call.data.replace("mgmt_bal_", "")
            action, target_uid = rest.split("_")
            user_states[user_id] = f"waiting_for_mgmt_bal_{action}_{target_uid}"
            save_database()
            old_bal = user_balances.get(int(target_uid), 0.0)
            label = {"add": "➕ Add Balance", "sub": "➖ Subtract Balance", "set": "✏️ Set Balance"}[action]
            bot.answer_callback_query(call.id, label)
            try:
                bot.edit_message_text(
                    f"{label}\n\n👤 User ID: `{target_uid}`\n💰 Current Balance: **${old_bal:.2f}**\n\n💵 Amount পাঠান (যেমন: `10`):",
                    call.message.chat.id, call.message.message_id, parse_mode="Markdown"
                )
            except:
                pass
        return

    if call.data.startswith("mgmt_bal_reset_"):
        if is_admin(user_id):
            target_uid = int(call.data.replace("mgmt_bal_reset_", ""))
            old_bal = user_balances.get(target_uid, 0.0)
            user_balances[target_uid] = 0.0
            save_database()
            bot.answer_callback_query(call.id, "Balance Reset to $0", show_alert=True)
            try:
                bot.edit_message_text(
                    f"✅ **Balance Reset!**\n\n👤 User ID: `{target_uid}`\n💰 Old: `${old_bal:.2f}` → New: **$0.00**",
                    call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_user_detail_keyboard(target_uid)
                )
            except:
                pass
            try:
                bot.send_message(target_uid, f"💰 **Your balance has been reset to $0.00 by Admin.**", parse_mode="Markdown")
            except:
                pass
        return

    if call.data.startswith("mgmt_hist_pur_"):
        if is_admin(user_id):
            target_uid = int(call.data.replace("mgmt_hist_pur_", ""))
            pur = user_purchases.get(target_uid, [])
            txt = "\n".join([p.get("text", "") if isinstance(p, dict) else str(p) for p in pur[-20:]]) or "No purchases yet."
            bot.answer_callback_query(call.id, "Purchase History")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"mgmt_user_{target_uid}"))
            try:
                bot.edit_message_text(f"📦 **Purchase History - {target_uid}**\n──────────────────────\n{txt}", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except:
                pass
        return

    if call.data.startswith("mgmt_hist_dep_"):
        if is_admin(user_id):
            target_uid = int(call.data.replace("mgmt_hist_dep_", ""))
            dep = user_deposits.get(target_uid, [])
            txt = "\n".join([d.get("text", "") if isinstance(d, dict) else str(d) for d in dep[-20:]]) or "No deposits yet."
            bot.answer_callback_query(call.id, "Deposit History")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"mgmt_user_{target_uid}"))
            try:
                bot.edit_message_text(f"💰 **Deposit History - {target_uid}**\n──────────────────────\n{txt}", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except:
                pass
        return

    if call.data == "lang_en":
        user_languages[user_id] = "en"
        save_database()
        bot.answer_callback_query(call.id, "Language changed to English!")
        # Automatically update message reply keyboard & text instantly without restarting
        new_t = LANG["en"]
        try:
            bot.edit_message_text(
                "🌐 **Language Settings / 语言设置**\n\nLanguage successfully changed to **English**!",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_language_keyboard(user_id)
            )
        except Exception:
            pass
        try:
            bot.send_message(call.message.chat.id, "👇 Main menu updated:", reply_markup=get_main_menu_keyboard(user_id))
        except Exception:
            pass
        return

    elif call.data == "lang_zh":
        user_languages[user_id] = "zh"
        save_database()
        bot.answer_callback_query(call.id, "语言已更改为中文！")
        # Automatically update message reply keyboard & text instantly without restarting
        new_t = LANG["zh"]
        try:
            bot.edit_message_text(
                "🌐 **语言设置 / Language Settings**\n\n语言已成功切换为 **中文**！",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_language_keyboard(user_id)
            )
        except Exception:
            pass
        try:
            bot.send_message(call.message.chat.id, "👇 主菜单已更新：", reply_markup=get_main_menu_keyboard(user_id))
        except Exception:
            pass
        return

    if call.data.startswith("qty_"):
        remainder = call.data.replace("qty_", "")
        if remainder.startswith("other_"):
            item_key = remainder.replace("other_", "")
            user_states[user_id] = f"waiting_for_custom_qty_{item_key}"
            save_database()
            bot.answer_callback_query(call.id, "Enter quantity")
            try:
                bot.edit_message_text(f"🔢 Enter your desired quantity for **{item_key}** (e.g., 4, 7, 15):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        else:
            last_underscore = remainder.rfind("_")
            item_key = remainder[:last_underscore]
            qty = int(remainder[last_underscore + 1:])
            bot.answer_callback_query(call.id, f"Selected {qty} qty")
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except Exception:
                pass
            process_product_purchase(call.message.chat.id, user_id, item_key, qty)
        return

    if call.data == "prod_telegram_prem_support":
        bot.answer_callback_query(call.id, "Redirecting to Support...")
        support_text = t["support"].format(support_user=support_admin_username)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(t["back"], callback_data="back_to_products_menu"))
        try:
            bot.edit_message_text(support_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            bot.send_message(call.message.chat.id, support_text, parse_mode="Markdown", reply_markup=markup)
        return

    if call.data == "admin_change_support":
        if is_admin(user_id):
            user_states[user_id] = "waiting_for_new_support_username"
            save_database()
            bot.answer_callback_query(call.id, "Change Support Username")
            try:
                bot.edit_message_text(f"📞 Current support username is: **{support_admin_username}**\n\nPlease send the new support username (e.g., `@newsupport`):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    if call.data == "admin_add_category":
        if is_admin(user_id):
            user_states[user_id] = "waiting_for_new_category_name"
            save_database()
            bot.answer_callback_query(call.id, "Add Category")
            try:
                bot.edit_message_text("➕ Enter the new product category name (e.g., `Netflix`):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data.startswith("prod_subcat_menu_"):
        cat_name = call.data.replace("prod_subcat_menu_", "")
        bot.answer_callback_query(call.id, cat_name)
        markup = types.InlineKeyboardMarkup(row_width=1)
        sub_items = product_inventory.get(cat_name, {}).get("items", {})
        if not sub_items:
            bot.answer_callback_query(call.id, "No sub-folders available yet! Please add stock or sub-folder from admin panel.", show_alert=True)
            return
        for sub_name, sub_data in sub_items.items():
            stock = len(sub_data.get("accounts", []))
            price = sub_data.get("price", 1.00)
            markup.add(types.InlineKeyboardButton(f"📂 {sub_name} — Price: ${price:.2f} | {t['stock']}: {stock}", callback_data=f"prod_sub_buy_{cat_name}_{sub_name}"))
        markup.add(types.InlineKeyboardButton(t["back"], callback_data="back_to_products_menu"))
        try:
            bot.edit_message_text(f"📁 **Select sub-folder under {cat_name}:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass
        return

    elif call.data.startswith("prod_sub_buy_"):
        data_parts = call.data.replace("prod_sub_buy_", "").split("_")
        p_cat = data_parts[0]
        s_item = "_".join(data_parts[1:])
        combined_key = f"{p_cat}___{s_item}"
        bot.answer_callback_query(call.id, s_item)
        try:
            bot.edit_message_text(f"🔢 **Select Quantity for {p_cat} -> {s_item}:**\n\nChoose how many items you want to buy:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_quantity_keyboard(combined_key, user_id))
        except Exception:
            pass
        return

    elif call.data == "prod_telegram_acc":
        bot.answer_callback_query(call.id, "Telegram Protocol")
        try:
            bot.edit_message_text(t["select_country"], call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_products_countries_keyboard(user_id))
        except Exception:
            bot.send_message(call.message.chat.id, t["select_country"], parse_mode="Markdown", reply_markup=get_products_countries_keyboard(user_id))
        return

    elif call.data.startswith("select_country_"):
        country = call.data.replace("select_country_", "")
        bot.answer_callback_query(call.id, country)
        c_data = product_inventory["Telegram Protocol"]["items"].get(country, {})
        price = c_data.get("price", 1.00)
        c_code = c_data.get("code", "")
        zip_stock_count = sum(len(zf.get("extracted_files", [])) for zf in c_data.get("zip_files", []))
        stock_count = len(c_data.get("accounts", [])) + zip_stock_count
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🛒 Select Quantity", callback_data=f"buy_protocol_{country}"),
            types.InlineKeyboardButton(t["back"], callback_data="prod_telegram_acc")
        )
        try:
            bot.edit_message_text(f"🌐 **Country:** {country} ({c_code})\n\n💰 **Price:** `${price:.2f}`\n📦 **Available {t['stock']}:** `{stock_count}` items\n\nClick below to proceed to quantity selection:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass
        return

    elif call.data.startswith("buy_protocol_"):
        country = call.data.replace("buy_protocol_", "")
        bot.answer_callback_query(call.id, country)
        try:
            bot.edit_message_text(f"🔢 **Select Quantity for Telegram Protocol ({country}):**\n\nChoose how many items you want to buy:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_quantity_keyboard(country, user_id))
        except Exception:
            pass
        return

    if call.data == "admin_add_accounts":
        if is_admin(user_id):
            markup = types.InlineKeyboardMarkup(row_width=1)
            for p_name in product_inventory.keys():
                if p_name != "Telegram Protocol" and p_name != "Telegram Premium":
                    if product_inventory[p_name].get("type") != "sub_categories":
                        product_inventory[p_name]["type"] = "sub_categories"
                        if "items" not in product_inventory[p_name]:
                            product_inventory[p_name]["items"] = {}
                    for sub_name in product_inventory[p_name].get("items", {}).keys():
                        markup.add(types.InlineKeyboardButton(f"📦 {p_name} -> {sub_name}", callback_data=f"select_sub_for_acc_{p_name}___{sub_name}"))
            markup.add(types.InlineKeyboardButton(t["back"], callback_data="admin_back"))
            bot.answer_callback_query(call.id, "Add Stock Menu")
            try:
                bot.edit_message_text("Select sub-folder to add stock & price:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                pass
        return

    elif call.data.startswith("select_sub_for_acc_"):
        if is_admin(user_id):
            raw_target = call.data.replace("select_sub_for_acc_", "")
            parts = raw_target.split("___")
            parent_cat = parts[0]
            target_sub = parts[1]
            temp_admin_data[user_id] = target_sub
            temp_admin_data[f"parent_{user_id}"] = parent_cat
            user_states[user_id] = "waiting_for_accounts_input"
            save_database()
            bot.answer_callback_query(call.id, target_sub)
            format_instruction = f"📦 Adding stock/price for **{parent_cat} -> {target_sub}**\n\nSend message in this format:\nLine 1: Price (e.g., `2.50`)\nLine 2+: Account details (Email, Password, Recovery, 2FA etc.)"
            try:
                bot.edit_message_text(format_instruction, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    if call.data == "admin_edit_delete_cat_menu":
        if is_admin(user_id):
            markup = types.InlineKeyboardMarkup(row_width=1)
            for cat_name in product_inventory.keys():
                markup.add(types.InlineKeyboardButton(f"📁 📂 [{cat_name}] Manage", callback_data=f"admin_manage_cat_{cat_name}"))
            markup.add(types.InlineKeyboardButton(t["back"], callback_data="admin_back"))
            bot.answer_callback_query(call.id, "Categories Management")
            try:
                bot.edit_message_text("📁 **Manage Product Categories & Sub-Folders:**\nSelect a category below to manage its sub-folders or edit/delete it:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                pass
        return

    elif call.data.startswith("admin_manage_cat_"):
        if is_admin(user_id):
            cat_name = call.data.replace("admin_manage_cat_", "")
            markup = types.InlineKeyboardMarkup(row_width=1)
            if cat_name == "Telegram Protocol":
                markup.add(types.InlineKeyboardButton("➕ Add New Country Telegram (Protocol)", callback_data="admin_add_country"))
                markup.add(types.InlineKeyboardButton("🗂️ Add Zip File Stock (Protocol)", callback_data="admin_add_zip_menu"))
                markup.add(types.InlineKeyboardButton("✏️ Edit & Delete Countries", callback_data="admin_edit_delete_countries_menu"))
                markup.add(types.InlineKeyboardButton("─── Country Prices Manage ───", callback_data="noop"))
                for c_name in product_inventory["Telegram Protocol"]["items"].keys():
                    markup.add(types.InlineKeyboardButton(f"💵 Edit Price: {c_name}", callback_data=f"admin_edit_protocol_price_{c_name}"))
            else:
                markup.add(
                    types.InlineKeyboardButton(f"➕ Add New Sub-Folder in {cat_name}", callback_data=f"admin_sub_add_{cat_name}"),
                    types.InlineKeyboardButton(f"✏️ Rename Category ({cat_name})", callback_data=f"admin_rename_cat_{cat_name}"),
                    types.InlineKeyboardButton(f"❌ Delete Category ({cat_name})", callback_data=f"admin_delete_cat_{cat_name}")
                )
                sub_items = product_inventory.get(cat_name, {}).get("items", {})
                if sub_items:
                    markup.add(types.InlineKeyboardButton("─── Sub-Folders List ───", callback_data="noop"))
                    for sub_name in sub_items.keys():
                        markup.add(
                            types.InlineKeyboardButton(f"✏️ Rename Sub: {sub_name}", callback_data=f"admin_rename_sub_{cat_name}___{sub_name}"),
                            types.InlineKeyboardButton(f"❌ Delete Sub: {sub_name}", callback_data=f"admin_delete_sub_{cat_name}___{sub_name}")
                        )
            markup.add(types.InlineKeyboardButton(t["back"], callback_data="admin_edit_delete_cat_menu"))
            bot.answer_callback_query(call.id, cat_name)
            try:
                bot.edit_message_text(f"📁 **Category:** `{cat_name}`\nChoose an action:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                pass
        return

    elif call.data == "admin_edit_delete_countries_menu":
        if is_admin(user_id):
            markup = types.InlineKeyboardMarkup(row_width=1)
            proto_items = product_inventory.get("Telegram Protocol", {}).get("items", {})
            if proto_items:
                for c_name in proto_items.keys():
                    markup.add(
                        types.InlineKeyboardButton(f"✏️ Rename: {c_name}", callback_data=f"admin_rename_country_{c_name}"),
                        types.InlineKeyboardButton(f"❌ Delete: {c_name}", callback_data=f"admin_delete_country_{c_name}")
                    )
            markup.add(types.InlineKeyboardButton(t["back"], callback_data="admin_manage_cat_Telegram Protocol"))
            bot.answer_callback_query(call.id, "Countries Edit/Delete")
            try:
                bot.edit_message_text("🌐 **Manage Telegram Protocol Countries:**\nSelect a country to Rename or Delete:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                pass
        return

    elif call.data.startswith("admin_rename_country_"):
        if is_admin(user_id):
            country_name = call.data.replace("admin_rename_country_", "")
            user_states[user_id] = f"waiting_for_rename_country_{country_name}"
            save_database()
            bot.answer_callback_query(call.id, f"Rename {country_name}")
            try:
                bot.edit_message_text(f"✏️ Enter new name for country **{country_name}**:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data.startswith("admin_delete_country_"):
        if is_admin(user_id):
            country_name = call.data.replace("admin_delete_country_", "")
            proto_items = product_inventory.get("Telegram Protocol", {}).get("items", {})
            if country_name in proto_items:
                del proto_items[country_name]
                save_database()
                bot.answer_callback_query(call.id, f"Deleted {country_name}")
                markup = types.InlineKeyboardMarkup(row_width=1)
                for c in proto_items.keys():
                    markup.add(
                        types.InlineKeyboardButton(f"✏️ Rename: {c}", callback_data=f"admin_rename_country_{c}"),
                        types.InlineKeyboardButton(f"❌ Delete: {c}", callback_data=f"admin_delete_country_{c}")
                    )
                markup.add(types.InlineKeyboardButton(t["back"], callback_data="admin_manage_cat_Telegram Protocol"))
                try:
                    bot.edit_message_text(f"✅ Country **{country_name}** deleted successfully!\n\n🌐 **Manage Telegram Protocol Countries:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
                except Exception:
                    pass
            else:
                bot.answer_callback_query(call.id, "Country not found", show_alert=True)
        return

    elif call.data.startswith("admin_edit_protocol_price_"):
        if is_admin(user_id):
            country_name = call.data.replace("admin_edit_protocol_price_", "")
            user_states[user_id] = f"waiting_for_protocol_price_{country_name}"
            save_database()
            bot.answer_callback_query(call.id, country_name)
            try:
                bot.edit_message_text(f"💵 Enter new price for **Telegram Protocol ({country_name})** (e.g., `1.50`):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data.startswith("admin_sub_add_"):
        if is_admin(user_id):
            parent_cat = call.data.replace("admin_sub_add_", "")
            user_states[user_id] = f"waiting_for_subcat_name_{parent_cat}"
            save_database()
            bot.answer_callback_query(call.id, "Add Sub-Folder")
            try:
                bot.edit_message_text(f"📁 Enter new sub-folder name for **{parent_cat}**:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data.startswith("admin_rename_cat_"):
        if is_admin(user_id):
            cat_name = call.data.replace("admin_rename_cat_", "")
            user_states[user_id] = f"waiting_for_rename_cat_{cat_name}"
            save_database()
            bot.answer_callback_query(call.id, f"Rename {cat_name}")
            try:
                bot.edit_message_text(f"✏️ Enter new name for category **{cat_name}**:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data.startswith("admin_delete_cat_"):
        if is_admin(user_id):
            cat_name = call.data.replace("admin_delete_cat_", "")
            if cat_name in product_inventory:
                del product_inventory[cat_name]
                save_database()
                bot.answer_callback_query(call.id, f"Deleted {cat_name}")
                try:
                    bot.edit_message_text(f"✅ Category **{cat_name}** has been deleted successfully!", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
                except Exception:
                    pass
            else:
                bot.answer_callback_query(call.id, "Category not found", show_alert=True)
        return

    elif call.data.startswith("admin_rename_sub_"):
        if is_admin(user_id):
            raw_data = call.data.replace("admin_rename_sub_", "")
            parts = raw_data.split("___")
            parent_cat = parts[0]
            sub_name = parts[1]
            user_states[user_id] = f"waiting_for_rename_subcat_{parent_cat}___{sub_name}"
            save_database()
            bot.answer_callback_query(call.id, f"Rename {sub_name}")
            try:
                bot.edit_message_text(f"✏️ Enter new name for sub-folder **{sub_name}** (under {parent_cat}):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data.startswith("admin_delete_sub_"):
        if is_admin(user_id):
            raw_data = call.data.replace("admin_delete_sub_", "")
            parts = raw_data.split("___")
            parent_cat = parts[0]
            sub_name = parts[1]
            if parent_cat in product_inventory and "items" in product_inventory[parent_cat]:
                if sub_name in product_inventory[parent_cat]["items"]:
                    del product_inventory[parent_cat]["items"][sub_name]
                    save_database()
                    bot.answer_callback_query(call.id, f"Deleted {sub_name}")
                    try:
                        bot.edit_message_text(f"✅ Sub-folder **{sub_name}** deleted successfully from **{parent_cat}**!", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
                    except Exception:
                        pass
                else:
                    bot.answer_callback_query(call.id, "Sub-folder not found", show_alert=True)
        return

    elif call.data == "noop":
        bot.answer_callback_query(call.id)
        return

    elif call.data.startswith("dep_accept_"):
        if is_admin(user_id):
            try:
                parts = call.data.split("_")
                target_user_id = int(parts[2])
                amount = float(parts[3])
                txid_val = parts[4] if len(parts) > 4 else ""
                if txid_val:
                    used_txids.add(txid_val)
                if target_user_id not in user_balances:
                    user_balances[target_user_id] = 0.00
                user_balances[target_user_id] += amount
                save_database()
                bot.answer_callback_query(call.id, "Deposit Accepted!")
                try:
                    bot.edit_message_text(f"✅ **Deposit Approved & Credited!**\nUser ID: `{target_user_id}`\nAmount: `${amount:.2f}`\nTxID: `{txid_val}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                except Exception:
                    pass
                bot.send_message(target_user_id, f"🎉 **Your deposit of ${amount:.2f} has been approved and added to your balance!**", parse_mode="Markdown")
            except Exception as e:
                bot.answer_callback_query(call.id, "Error processing approval", show_alert=True)
        return

    elif call.data.startswith("dep_reject_"):
        if is_admin(user_id):
            try:
                parts = call.data.split("_")
                target_user_id = int(parts[2])
                amount = float(parts[3])
                bot.answer_callback_query(call.id, "Deposit Rejected!")
                try:
                    bot.edit_message_text(f"❌ **Deposit Rejected!**\nUser ID: `{target_user_id}`\nAmount: `${amount:.2f}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                except Exception:
                    pass
                bot.send_message(target_user_id, f"❌ **Your deposit request of ${amount:.2f} has been rejected by admin.**", parse_mode="Markdown")
            except Exception:
                bot.answer_callback_query(call.id, "Error processing rejection", show_alert=True)
        return

    elif call.data.startswith("send_order_id_"):
        order_id = call.data.replace("send_order_id_", "")
        bot.answer_callback_query(call.id)
        user_states[user_id] = "waiting_for_payment_proof"
        order_info = temp_admin_data.get(f"order_temp_{user_id}", {"order_id": order_id, "method": "Deposit"})
        temp_admin_data[f"order_info_{user_id}"] = order_info
        save_database()
        prompt_text = "Now please send your payment Proof / Trx Order ID / Screenshot:"
        try:
            bot.send_message(call.message.chat.id, prompt_text, parse_mode="Markdown")
        except Exception:
            pass
        return

    if call.data == "btn_deposit_open" or call.data == "dep_confirm" or call.data == "▲ Deposit":
        try:
            bot.answer_callback_query(call.id, "Loading...")
            bot.edit_message_text(t["deposit"], call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_select_amount_keyboard(user_id))
        except Exception:
            bot.send_message(call.message.chat.id, t["deposit"], parse_mode="Markdown", reply_markup=get_select_amount_keyboard(user_id))
        return

    elif call.data.startswith("amt_"):
        if call.data == "amt_other":
            user_states[user_id] = "waiting_for_custom_amount"
            save_database()
            bot.answer_callback_query(call.id, "Enter custom amount")
            bot.send_message(call.message.chat.id, "Enter custom deposit amount (USDT, Min $2):", parse_mode="Markdown")
        else:
            try:
                selected_val = float(call.data.split("_")[1])
                user_amounts[user_id] = selected_val
                user_states[user_id] = "waiting_for_payment_method"
                save_database()
                payment_text = f"💰 **Selected Amount:** ${selected_val:.2f}\n\nPlease select your preferred payment method:"
                bot.answer_callback_query(call.id, f"Selected ${selected_val:.2f}")
                bot.edit_message_text(payment_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_payment_methods_keyboard(user_id))
            except Exception:
                pass
        return

    elif call.data == "pay_binance":
        current_amount = user_amounts.get(user_id, 2.00)
        if current_amount < 2.00:
            bot.answer_callback_query(call.id, "❌ Minimum deposit for Binance UID is $2.00!", show_alert=True)
            return
        calculated_binance = current_amount * (10.082 / 10.0)
        send_val_str = f"{calculated_binance:.3f} USDT"
        order_id = f"ORD-B{random.randint(10000000, 99999999):X}"
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        temp_admin_data[f"order_temp_{user_id}"] = {"order_id": order_id, "method": "Binance UID · USDT"}
        deposit_text = f"Order: `{order_id}` | Amt: `${current_amount:.2f}` (Binance UID) | Time: {current_time}"
        if user_id not in user_deposits:
            user_deposits[user_id] = []
        user_deposits[user_id].append({"text": deposit_text, "timestamp": time.time()})
        save_database()
        binance_order_text = (
            "[ ORDER CREATED ]  Binance UID · USDT\n"
            "──────────────────────\n"
            f"  Send     ·  `{send_val_str}`\n"
            f"  Credit   ·  ${current_amount:.2f}\n"
            f"  Order    ·  `{order_id}`\n"
            "  Network  ·  Binance UID\n"
            f"  Pay ID   ·  `1271852493`\n"
            "  Name     ·  onwerTGselling\n"
            f"  Expires  ·  {current_time}\n"
            "──────────────────────\n"
            f"Send exactly `{send_val_str}`, including all decimals. The extra decimals only identify your payment; ${current_amount:.2f} is credited.\n"
            "Your balance will be credited by admin once verified."
        )
        bot.answer_callback_query(call.id, "Selected Binance UID")
        try:
            bot.edit_message_text(binance_order_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_order_created_keyboard("binance", order_id, user_id))
        except Exception:
            bot.send_message(call.message.chat.id, binance_order_text, parse_mode="Markdown", reply_markup=get_order_created_keyboard("binance", order_id, user_id))
        return

    elif call.data == "pay_tron_menu":
        bot.answer_callback_query(call.id, "Tron Network selected")
        try:
            bot.edit_message_text(f"💎 **Tron Network** (Min Deposit: $3)\n\nSelected Amount: ${user_amounts.get(user_id, 3.00):.2f}\n\nPlease select token/coin type:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_tron_subfolders_keyboard(user_id))
        except Exception:
            pass
        return

    elif call.data == "pay_bsc_menu":
        bot.answer_callback_query(call.id, "Bsc Network selected")
        try:
            bot.edit_message_text(f"🪙 **Bsc Network (BEP20)** (Min Deposit: $3)\n\nSelected Amount: ${user_amounts.get(user_id, 3.00):.2f}\n\nPlease select token/coin type:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_bsc_subfolders_keyboard(user_id))
        except Exception:
            pass
        return

    elif call.data in ["order_usdt_trc20", "order_trx", "order_usdt_bep20", "order_bnb"]:
        current_amount = user_amounts.get(user_id, 3.00)
        if current_amount < 3.0:
            bot.answer_callback_query(call.id, "❌ Minimum deposit for this network is $3.00!", show_alert=True)
            return
        order_id = f"ORD-{random.randint(100000, 999999)}"
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if call.data == "order_usdt_trc20":
            calculated_val = current_amount * (10.016 / 10.0)
            send_val = f"{calculated_val:.3f} USDT"
            credit_val = f"${current_amount:.2f}"
            currency_type = "USDT · TRC20"
            wallet_address = "TMDf93NV9zM5sAS9mXc5FWmRC5qLbwM4EV"
            network_name = "Tron(Trc20)"
            net_code = "tron"
        elif call.data == "order_trx":
            calculated_trx = current_amount * (31.495 / 10.0)
            send_val = f"{calculated_trx:.3f} TRX"
            credit_val = f"${current_amount:.2f}"
            currency_type = "TRX · TRON"
            wallet_address = "TMDf93NV9zM5sAS9mXc5FWmRC5qLbwM4EV"
            network_name = "TRON"
            net_code = "tron"
        elif call.data == "order_usdt_bep20":
            calculated_val = current_amount * (10.076 / 10.0)
            send_val = f"{calculated_val:.3f} USDT"
            credit_val = f"${current_amount:.2f}"
            currency_type = "USDT · BEP20"
            wallet_address = "0x4388fd8ff1278b4d9ddfc770875a731379a061b6"
            network_name = "BNB Smart Chain (BEP20)"
            net_code = "bsc"
        else:
            calculated_bnb = current_amount * (0.014249 / 10.0)
            send_val = f"{calculated_bnb:.6f} BNB"
            credit_val = f"${current_amount:.2f}"
            currency_type = "BNB · BSC"
            wallet_address = "0x4388fd8ff1278b4d9ddfc770875a731379a061b6"
            network_name = "BNB Smart Chain (BEP20)"
            net_code = "bsc"
        temp_admin_data[f"order_temp_{user_id}"] = {"order_id": order_id, "method": currency_type}
        deposit_text = f"Order: `{order_id}` | Amt: `${current_amount:.2f}` ({currency_type}) | Time: {current_time}"
        if user_id not in user_deposits:
            user_deposits[user_id] = []
        user_deposits[user_id].append({"text": deposit_text, "timestamp": time.time()})
        save_database()
        order_text = (
            "[ ORDER CREATED ]  " + currency_type + "\n"
            "──────────────────────\n"
            f"  Send     ·  `{send_val}`\n"
            f"  Credit   ·  {credit_val}\n"
            f"  Order    ·  `{order_id}`\n"
            f"  Network  ·  {network_name}\n"
            f"  Address  ·  `{wallet_address}`\n"
            f"  Expires  ·  {current_time}\n"
            "──────────────────────\n"
            f"Send exactly `{send_val}`, including all decimals. This amount was converted from ${current_amount:.2f} at the Binance price when the order was created and ends in a unique identifier; ${current_amount:.2f} is credited when it arrives.\n"
            f"Send native assets/tokens on the {network_name} network only.\n"
            "Your balance will be credited by admin once verified."
        )
        bot.answer_callback_query(call.id, "Order Generated!")
        try:
            bot.edit_message_text(order_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_order_created_keyboard(net_code, order_id, user_id))
        except Exception:
            bot.send_message(call.message.chat.id, order_text, parse_mode="Markdown", reply_markup=get_order_created_keyboard(net_code, order_id, user_id))
        return

    elif call.data == "hist_purchase":
        bot.answer_callback_query(call.id, "Purchase History")
        purchases = user_purchases.get(user_id, [])
        formatted_purchases = []
        for p in purchases:
            if isinstance(p, dict):
                formatted_purchases.append(p.get("text", ""))
            else:
                formatted_purchases.append(str(p))
        hist_text = "📦 **PURCHASE HISTORY (Last 30 Hours)**\n──────────────────────\n" + ("\n".join(formatted_purchases) if formatted_purchases else "No purchases yet or records older than 30 hours cleared.")
        try:
            bot.edit_message_text(hist_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(t["back"], callback_data="back_to_history_menu")))
        except Exception:
            pass
        return

    elif call.data == "hist_deposit":
        bot.answer_callback_query(call.id, "Deposit History")
        deposits = user_deposits.get(user_id, [])
        formatted_deposits = []
        for d in deposits:
            if isinstance(d, dict):
                formatted_deposits.append(d.get("text", ""))
            else:
                formatted_deposits.append(str(d))
        dep_text = "💰 **DEPOSIT HISTORY (Last 30 Hours)**\n──────────────────────\n" + ("\n".join(formatted_deposits) if formatted_deposits else "No deposit orders yet or records older than 30 hours cleared.")
        try:
            bot.edit_message_text(dep_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(t["back"], callback_data="back_to_history_menu")))
        except Exception:
            pass
        return

    elif call.data == "back_to_history_menu":
        bot.answer_callback_query(call.id, "History Menu")
        history_main_text = t["history"]
        try:
            bot.edit_message_text(history_main_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_history_menu_keyboard(user_id))
        except Exception:
            pass
        return

    if call.data == "admin_broadcast_start":
        if is_admin(user_id):
            user_states[user_id] = "waiting_for_broadcast_message"
            save_database()
            bot.answer_callback_query(call.id, "Broadcast Mode")
            try:
                bot.edit_message_text("📢 **Broadcast System**\n\nPlease send the message, photo, video or file that you want to send to all users:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    if call.data == "admin_add_country":
        if is_admin(user_id):
            user_states[user_id] = "waiting_for_new_country"
            save_database()
            bot.answer_callback_query(call.id, "Add Country")
            try:
                bot.edit_message_text("🌍 Enter new country name for Telegram Protocol (e.g., Canada):", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data == "back_to_products_menu":
        bot.answer_callback_query(call.id, "Products Menu")
        try:
            bot.edit_message_text(t["products"], call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_products_categories_keyboard(user_id))
        except Exception:
            pass
        return

    elif call.data == "admin_add_zip_menu":
        if is_admin(user_id):
            markup = types.InlineKeyboardMarkup(row_width=1)
            for c in product_inventory["Telegram Protocol"]["items"].keys():
                markup.add(types.InlineKeyboardButton(f"🗂️ Protocol Country ({c})", callback_data=f"select_zip_country_{c}"))
            markup.add(types.InlineKeyboardButton(t["back"], callback_data="admin_edit_delete_cat_menu"))
            bot.answer_callback_query(call.id, "ZIP Menu")
            try:
                bot.edit_message_text("Select country to upload ZIP file stock:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
            except Exception:
                pass
        return

    elif call.data.startswith("select_zip_country_"):
        if is_admin(user_id):
            country_name = call.data.replace("select_zip_country_", "")
            temp_admin_data[user_id] = country_name
            user_states[user_id] = "waiting_for_zip_file"
            save_database()
            bot.answer_callback_query(call.id, country_name)
            try:
                bot.edit_message_text(f"📁 Please send the **.zip file** containing session/json/tdata for **{country_name}**:", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            except Exception:
                pass
        return

    elif call.data == "admin_back":
        if is_admin(user_id):
            try:
                bot.edit_message_text("🛠️ **Welcome to Admin Panel**\n\nChoose an option below:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_admin_panel_keyboard(user_id))
            except Exception:
                pass
        return

    elif call.data == "go_main_menu" or call.data == "dep_cancel":
        bot.answer_callback_query(call.id, "MainMenu")
        user_states.pop(user_id, None)
        save_database()
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        send_welcome(call.message)

class SimpleHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        try:
            json_string = post_data.decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
        except Exception as e:
            print(f"Error processing update: {e}")
        self.send_response(200)
        self.end_headers()
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive via Webhook!")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    server.serve_forever()

if __name__ == '__main__':
    threading.Thread(target=background_cleanup_job, daemon=True).start()
    threading.Thread(target=run_web_server, daemon=True).start()
    set_bot_commands(bot)
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
    if RENDER_URL:
        bot.remove_webhook()
        bot.set_webhook(url=f"{RENDER_URL}/")
        print(f"Webhook set to: {RENDER_URL}/")
    else:
        print("RENDER_EXTERNAL_URL not found, please check your Render environment variables.")
    print("Bot is running with Webhook and Firebase Realtime Database...")
    while True:
        time.sleep(10)
