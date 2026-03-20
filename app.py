from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
from datetime import datetime

app = Flask(__name__)

def get_workbook():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDS_JSON")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("snacks adda 19-03-26")

def get_menu_sheet():
    return get_workbook().sheet1

def get_orders_sheet():
    wb = get_workbook()
    try:
        return wb.worksheet("Orders")
    except:
        sheet = wb.add_worksheet(title="Orders", rows="1000", cols="8")
        sheet.append_row(["Order ID", "Phone", "Name", "Items", "Total", "Status", "Timestamp"])
        return sheet

def get_customers_sheet():
    wb = get_workbook()
    try:
        return wb.worksheet("Customers")
    except:
        sheet = wb.add_worksheet(title="Customers", rows="1000", cols="3")
        sheet.append_row(["Phone", "Name", "Joined"])
        return sheet

def get_customer_name(phone):
    try:
        sheet = get_customers_sheet()
        records = sheet.get_all_values()
        for row in records[1:]:
            if row[0] == phone:
                return row[1]
    except:
        pass
    return None

def save_customer(phone, name):
    try:
        sheet = get_customers_sheet()
        records = sheet.get_all_values()
        for i, row in enumerate(records[1:], start=2):
            if row[0] == phone:
                sheet.update_cell(i, 2, name)
                return
        sheet.append_row([phone, name, datetime.now().strftime("%Y-%m-%d %H:%M")])
    except Exception as e:
        print(f"Error saving customer: {e}")

def get_menu_items():
    sheet = get_menu_sheet()
    rows = sheet.get_all_values()
    items = []
    for row in rows[1:]:
        if len(row) >= 5:
            name = row[1].strip()
            category = row[2].strip().lower()
            price = row[3].strip()
            status = row[4].strip().lower()
            if status == "active" and name:
                items.append({"name": name, "category": category, "price": int(price)})
    return items

# In-memory session store
sessions = {}

def get_session(phone):
    if phone not in sessions:
        sessions[phone] = {"state": "idle", "order": [], "name": None}
    return sessions[phone]

def save_order(phone, name, order_items):
    try:
        sheet = get_orders_sheet()
        all_orders = sheet.get_all_values()
        order_id = f"ORD{len(all_orders):04d}"
        items_str = ", ".join([f"{i['name']} x{i['qty']} (₹{i['price']*i['qty']})" for i in order_items])
        total = sum(i['price'] * i['qty'] for i in order_items)
        sheet.append_row([order_id, phone, name, items_str, total, "Pending", datetime.now().strftime("%Y-%m-%d %H:%M")])
        return order_id, total
    except Exception as e:
        print(f"Error saving order: {e}")
        return None, 0

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.form.get("Body", "").strip()
    phone = request.form.get("From", "")
    resp = MessagingResponse()
    session = get_session(phone)
    msg_lower = msg.lower()

    try:
        # Check if customer has a saved name
        if session["name"] is None:
            session["name"] = get_customer_name(phone) or "Friend"

        name = session["name"]

        # ── REGISTRATION: asking for name ──
        if session["state"] == "awaiting_name":
            session["name"] = msg.strip()
            save_customer(phone, msg.strip())
            session["state"] = "idle"
            reply = f"Nice to meet you, *{msg.strip()}*! 😊\nType *menu* to see our items.\nType *help* for all commands."
            resp.message(reply)
            return str(resp)

        # ── ORDER FLOW ──
        if session["state"] == "ordering":
            if msg_lower == "done":
                if not session["order"]:
                    reply = "Your cart is empty! Type an item name to add it."
                else:
                    summary = "🧾 *Order Summary:*\n"
                    total = 0
                    for item in session["order"]:
                        subtotal = item['price'] * item['qty']
                        total += subtotal
                        summary += f"• {item['name']} x{item['qty']} = ₹{subtotal}\n"
                    summary += f"\n*Total: ₹{total}*\n\nType *confirm* to place order or *cancel* to cancel."
                    session["state"] = "confirming"
                    reply = summary
            elif msg_lower == "cancel":
                session["order"] = []
                session["state"] = "idle"
                reply = "❌ Order cancelled. Type *menu* to start again."
            elif msg_lower == "cart":
                if not session["order"]:
                    reply = "🛒 Your cart is empty.\nType item names to add them."
                else:
                    cart = "🛒 *Your Cart:*\n"
                    total = 0
                    for item in session["order"]:
                        subtotal = item['price'] * item['qty']
                        total += subtotal
                        cart += f"• {item['name']} x{item['qty']} = ₹{subtotal}\n"
                    cart += f"\n*Total: ₹{total}*\nType *done* to checkout or *cancel* to cancel."
                    reply = cart
            else:
                # Try to match item
                items = get_menu_items()
                matched = None
                qty = 1

                # Check if message ends with a number e.g. "Veggie Momo 2"
                parts = msg.rsplit(" ", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    search_name = parts[0].lower()
                    qty = int(parts[1])
                else:
                    search_name = msg_lower

                for item in items:
                    if search_name in item["name"].lower():
                        matched = item
                        break

                if matched:
                    # Check if already in cart
                    found = False
                    for cart_item in session["order"]:
                        if cart_item["name"] == matched["name"]:
                            cart_item["qty"] += qty
                            found = True
                            break
                    if not found:
                        session["order"].append({"name": matched["name"], "price": matched["price"], "qty": qty})
                    reply = f"✅ Added *{matched['name']} x{qty}* to cart!\nType more items, *cart* to view, or *done* to checkout."
                else:
                    reply = f"❌ Item not found. Please check the name and try again.\nType *menu* to see available items."

            resp.message(reply)
            return str(resp)

        if session["state"] == "confirming":
            if msg_lower == "confirm":
                order_id, total = save_order(phone, name, session["order"])
                session["order"] = []
                session["state"] = "idle"
                reply = f"🎉 *Order Placed!*\nOrder ID: *{order_id}*\nTotal: *₹{total}*\nWe'll prepare your order shortly! 🍽️"
            elif msg_lower == "cancel":
                session["order"] = []
                session["state"] = "idle"
                reply = "❌ Order cancelled."
            else:
                reply = "Type *confirm* to place your order or *cancel* to cancel."
            resp.message(reply)
            return str(resp)

        # ── MAIN COMMANDS ──
        if msg_lower == "menu":
            items = get_menu_items()
            reply = f"🍽️ *Apli Snack Adda Menu:*\n\n"
            current_cat = ""
            for item in items:
                if item["category"] != current_cat:
                    current_cat = item["category"]
                    reply += f"\n*{current_cat.upper()}*\n"
                reply += f"• {item['name']} - ₹{item['price']}\n"
            reply += "\nType *order* to start ordering!"

        elif msg_lower == "order":
            session["state"] = "ordering"
            session["order"] = []
            items = get_menu_items()
            reply = f"🛒 *Start your order, {name}!*\n\nType item names to add them.\nE.g: _Veggie Momo_ or _Veggie Momo 2_ for quantity\n\nType *cart* to view cart\nType *done* to checkout\nType *cancel* to cancel"

        elif msg_lower.startswith("momo") or msg_lower.startswith("burger") or msg_lower.startswith("sandwich") or msg_lower.startswith("frankie") or msg_lower.startswith("shake"):
            # Category filter
            items = get_menu_items()
            category = msg_lower.strip()
            filtered = [i for i in items if category in i["category"]]
            if filtered:
                reply = f"🍽️ *{category.upper()} Menu:*\n\n"
                for item in filtered:
                    reply += f"• {item['name']} - ₹{item['price']}\n"
                reply += "\nType *order* to start ordering!"
            else:
                reply = f"No items found for *{category}*."

        elif msg_lower.startswith("under "):
            # Budget filter
            try:
                budget = int(msg_lower.replace("under ", "").strip())
                items = get_menu_items()
                filtered = [i for i in items if i["price"] <= budget]
                if filtered:
                    reply = f"🍽️ *Items under ₹{budget}:*\n\n"
                    for item in filtered:
                        reply += f"• {item['name']} - ₹{item['price']}\n"
                    reply += "\nType *order* to start ordering!"
                else:
                    reply = f"No items available under ₹{budget}."
            except:
                reply = "Please type like: *under 60*"

        elif msg_lower == "myname":
            session["state"] = "awaiting_name"
            reply = "Please tell me your name 😊"

        elif msg_lower == "help":
            reply = ("🤖 *Available Commands:*\n\n"
                    "*menu* - View full menu\n"
                    "*order* - Start ordering\n"
                    "*momo* - View momo items\n"
                    "*burger* - View burger items\n"
                    "*sandwich* - View sandwich items\n"
                    "*frankie* - View frankie items\n"
                    "*under 60* - Items under ₹60\n"
                    "*myname* - Update your name\n"
                    "*help* - Show this list")

        elif name == "Friend":
            session["state"] = "awaiting_name"
            reply = f"👋 Welcome to *Apli Snack Adda!*\nWhat's your name? 😊"

        else:
            reply = f"👋 Hi *{name}*! Type *menu* to see our items or *help* for all commands."

    except Exception as e:
        print(f"Error: {e}")
        reply = "Something went wrong. Please try again."

    resp.message(reply)
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
