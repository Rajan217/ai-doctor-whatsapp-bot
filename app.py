from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
import sqlite3
from dotenv import load_dotenv
from datetime import datetime
import logging
import requests # ADDED: Import the requests library for API calls
import json # ADDED: Import json for handling API responses

# Configure basic logging for Flask app
logging.basicConfig(level=logging.INFO)

# --- Explicitly load environment variables from .env file in the script's directory ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

app = Flask(__name__)

# --- IMPORTANT: Use environment variables for sensitive data ---
try:
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError("Twilio Account SID or Auth Token not found in environment variables.")
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
except ValueError as e:
    app.logger.error(f"❌ Twilio Client Initialization Error: {e}")
    app.logger.error("Please ensure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are set in your .env file.")
    client = None

# --- Database setup ---
DATABASE_PATH = os.getenv('DATABASE_PATH', 'medical.db')

def init_db():
    """
    Initializes the SQLite database, creating the consultations table
    with all necessary columns. It forces a recreation of the database
    file on each startup to ensure a clean schema.
    """
    try:
        # This is aggressive and means data will be lost on every deploy/restart.
        # For production, you'd use a persistent external database like PostgreSQL.
        if os.path.exists(DATABASE_PATH):
            os.remove(DATABASE_PATH)
            app.logger.info(f"🗑️ Deleted existing database file: {DATABASE_PATH}")

        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE consultations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    symptoms TEXT NOT NULL,
                    diagnosis TEXT,
                    response TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    patient_name TEXT DEFAULT 'Unknown'
                )
            ''')
            app.logger.info("✅ 'consultations' table created.")

            conn.commit()
            app.logger.info("✅ Database initialization complete.")
    except sqlite3.Error as e:
        app.logger.error(f"❌ Database initialization failed: {e}", exc_info=True)

# Initialize database on app startup
init_db()

# --- Gemini API Integration ---
# The API key will be injected by the Canvas environment
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '') # Empty string for Canvas injection
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

def diagnose(symptoms):
    """
    Diagnoses symptoms using the Gemini LLM.
    Provides a disclaimer that it's not medical advice.
    """
    app.logger.info(f"Calling Gemini API for diagnosis with symptoms: '{symptoms}'")

    prompt = f"""
    You are an AI assistant designed to provide general information about symptoms.
    You are NOT a medical doctor and cannot give medical advice.
    Always include a clear disclaimer at the beginning and end of your response stating this.

    Based on the following symptoms, provide a brief, general explanation of what they might indicate,
    and suggest common next steps (e.g., rest, hydration, or when to see a doctor).
    Keep the response concise and suitable for a WhatsApp message (under 160 characters if possible, but prioritize clarity).

    Symptoms: {symptoms}
    """

    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "topP": 0.95,
            "topK": 40,
            "maxOutputTokens": 200 # Limit output length for WhatsApp
        }
    }

    try:
        response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        result = response.json()

        if result and result.get('candidates') and result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts'):
            diagnosis_text = result['candidates'][0]['content']['parts'][0]['text']
            # Add a clear disclaimer at the beginning of the response
            final_response = (
                "⚠️ Disclaimer: I am an AI and cannot provide medical advice. Consult a doctor for health concerns.\n\n"
                f"{diagnosis_text}\n\n"
                "Remember to consult a healthcare professional for diagnosis and treatment."
            )
            return "LLM Diagnosis", final_response
        else:
            app.logger.error(f"Gemini API response structure unexpected: {result}")
            return "LLM Error", "⚠️ AI diagnosis unavailable. Please try again or consult a doctor."

    except requests.exceptions.HTTPError as errh:
        app.logger.error(f"HTTP Error: {errh}", exc_info=True)
        return "LLM Error", "⚠️ AI diagnosis currently unavailable due to a network issue. Please try again later."
    except requests.exceptions.ConnectionError as errc:
        app.logger.error(f"Error Connecting: {errc}", exc_info=True)
        return "LLM Error", "⚠️ AI diagnosis currently unavailable due to a connection issue. Please try again later."
    except requests.exceptions.Timeout as errt:
        app.logger.error(f"Timeout Error: {errt}", exc_info=True)
        return "LLM Error", "⚠️ AI diagnosis currently unavailable due to a timeout. Please try again later."
    except requests.exceptions.RequestException as err:
        app.logger.error(f"General Request Error: {err}", exc_info=True)
        return "LLM Error", "⚠️ AI diagnosis currently unavailable due to an unexpected error. Please try again later."
    except json.JSONDecodeError as e:
        app.logger.error(f"JSON Decode Error: {e} - Response: {response.text}", exc_info=True)
        return "LLM Error", "⚠️ AI diagnosis unavailable due to a response formatting issue. Please try again."
    except Exception as e:
        app.logger.error(f"Unexpected error during Gemini API call: {e}", exc_info=True)
        return "LLM Error", "⚠️ An unexpected AI error occurred. Please try again."


def save_to_db(phone, symptoms, diagnosis, response, patient_name="Unknown"):
    """Safe database operation with context manager"""
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            conn.execute('''INSERT INTO consultations
                            (phone, symptoms, diagnosis, response, patient_name)
                            VALUES (?, ?, ?, ?, ?)''',
                           (phone, symptoms, diagnosis, response, patient_name))
            last_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            app.logger.info(f"💾 Saved consultation ID: {last_id}")
            return True
    except sqlite3.Error as e:
        app.logger.error(f"❌ Database Error during save: {e}", exc_info=True)
        return False

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    # Get incoming data
    phone = request.values.get('From', '')
    incoming_msg = request.values.get('Body', '').strip()

    app.logger.info(f"\n=== INCOMING MESSAGE ===")
    app.logger.info(f"From: {phone}")
    app.logger.info(f"Content: '{incoming_msg}'")

    # Prepare response
    resp = MessagingResponse()
    response_text = ""
    diagnosis_name = None

    if not incoming_msg:
        response_text = "Please describe your symptoms (e.g., 'headache and fever')."
    elif "hello" in incoming_msg.lower():
        response_text = "👋 Hi! Describe your symptoms (e.g. 'headache and fever')"
    elif "history" in incoming_msg.lower():
        # Feature: Retrieve last 3 consultations
        try:
            with sqlite3.connect(DATABASE_PATH) as conn:
                history = conn.execute('''SELECT symptoms, diagnosis, timestamp, patient_name
                                         FROM consultations
                                         WHERE phone = ?
                                         ORDER BY timestamp DESC
                                         LIMIT 3''', (phone,)).fetchall()
                if history:
                    response_text = "📜 Your History:\n" + "\n".join(
                        f"[{row[2]}] {row[3]} - Symptoms: {row[0]} → Diagnosis: {row[1]}" for row in history
                    )
                else:
                    response_text = "No history found for this number."
        except sqlite3.Error as e:
            response_text = "⚠️ Could not retrieve history due to a database error."
            app.logger.error(f"History retrieval Error: {e}", exc_info=True)
    else:
        # Get diagnosis from LLM
        diagnosis_name, diagnosis_response = diagnose(incoming_msg)
        response_text = f"AI Doctor Report:\n\nSymptoms: {incoming_msg}\nDiagnosis: {diagnosis_response}"

    # Determine patient_name (you might want to add a way for users to set this)
    patient_name_for_save = "Unknown"

    # Save to database and send response
    if save_to_db(phone, incoming_msg, diagnosis_name, response_text, patient_name_for_save):
        resp.message(response_text)
    else:
        resp.message("⚠️ System error - your symptoms were not saved. Please try again.")

    return str(resp)

if __name__ == "__main__":
    print(r"""
    _____ _    ___        __  ___          
   / ___/(_) / (_)____/ /_/   |  ________ 
   \__ \/ / / / / ___/ __/ /| | / ___/ _ \\
 ___/ / / / / (__  ) /_/ ___ |(__  )  __/
/____/_/_/_/_/____/\__/_/   |_/____/\___/ 
                                            
AI Doctor System Ready!""")
    app.run(host='0.0.0.0', port=5000, debug=True)