from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

app = Flask(__name__)

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDS_JSON")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("snacks adda 19-03-26").sheet1
    return sheet

@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    msg = request.form.get("Body", "").strip().lower()
    resp = MessagingResponse()

    try:
        if msg == "menu":
            sheet = get_sheet()
            rows = sheet.get_all_values()
            reply = "🍽️ Apli Snack Adda Menu:\n\n"
            items = []
            for row in rows[1:]:
                if len(row) >= 5:
                    name = row[1].strip()
                    price = row[3].strip()
                    status = row[4].strip().lower()
                    if status == "active" and name:
                        items.append(f"{name} - ₹{price}")
            if items:
                reply += "\n".join(items)
            else:
                reply += "No items available right now."
        else:
            reply = "Welcome to Apli Snack Adda! 😊\nType *menu* to see today's items."
    except Exception as e:
        reply = "Something went wrong. Please try again."
        print(f"Error: {e}")

    resp.message(reply)
    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
