from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os
import sqlite3
from dotenv import load_dotenv
from datetime import datetime
import logging # ADDED: Import logging module

# Configure basic logging for Flask app
# This helps capture errors in Render logs more clearly
logging.basicConfig(level=logging.INFO) # Set to INFO for general messages, DEBUG for more verbosity

# --- Explicitly load environment variables from .env file in the script's directory ---
# This helps ensure the .env file is found regardless of the current working directory
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

app = Flask(__name__)

# --- IMPORTANT: Use environment variables for sensitive data ---
# Initialize Twilio client using environment variables
# Ensure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are set in your .env file
try:
    # --- FIX: Pass the NAMES of the environment variables, not the values ---
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError("Twilio Account SID or Auth Token not found in environment variables.")
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
except ValueError as e:
    app.logger.error(f"❌ Twilio Client Initialization Error: {e}") # Use app.logger
    app.logger.error("Please ensure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are set in your .env file.") # Use app.logger
    client = None # Set client to None to prevent further errors if credentials are missing

# --- Database setup ---
# Use an environment variable for the database path for better flexibility
DATABASE_PATH = os.getenv('DATABASE_PATH', 'medical.db') # Default to medical.db if not set

def init_db():
    """
    Initializes the SQLite database, creating the consultations table
    and adding the patient_name column if they don't exist.
    """
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()

            # Create the consultations table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS consultations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT NOT NULL,
                    symptoms TEXT NOT NULL,
                    diagnosis TEXT,
                    response TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            app.logger.info("✅ 'consultations' table checked/created.") # Use app.logger

            # Add the patient_name column if it doesn't exist
            try:
                cursor.execute("ALTER TABLE consultations ADD COLUMN patient_name TEXT DEFAULT 'Unknown'")
                app.logger.info("✅ Added 'patient_name' column to 'consultations' table.") # Use app.logger
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    app.logger.info("ℹ️ 'patient_name' column already exists. Skipping addition.") # Use app.logger
                else:
                    raise # Re-raise other unexpected operational errors

            conn.commit()
            app.logger.info("✅ Database initialization complete.") # Use app.logger
    except sqlite3.Error as e:
        app.logger.error(f"❌ Database initialization failed: {e}", exc_info=True) # Log full traceback
        # Note: If init_db fails, subsequent DB operations will also fail.
        # Consider a more robust error handling for app startup if this is critical.

# Initialize database on app startup
init_db()

def diagnose(symptoms):
    """
    Enhanced diagnosis logic with symptom scoring.
    In a real application, this would be replaced by a more sophisticated
    AI model (e.g., an LLM or a machine learning model trained on medical data).
    """
    symptoms_lower = symptoms.lower()

    conditions = {
        "flu": {
            "keywords": ["fever", "headache", "body ache", "chills"],
            "response": "🤒 Likely Influenza (85% match)\n• Rest and fluids\n• Antivirals if <48hrs\n• Contagious 7 days"
        },
        "cold": {
            "keywords": ["cough", "sore throat", "runny nose"],
            "response": "🤧 Likely Common Cold (75% match)\n• OTC cold medicine\n• Rest\n• Contagious 10 days"
        },
        "allergy": {
            "keywords": ["sneezing", "itchy eyes", "runny nose", "congestion"],
            "response": "🤧 Likely Allergies (70% match)\n• Antihistamines\n• Avoid triggers\n• Not contagious"
        },
        "stomach bug": {
            "keywords": ["nausea", "vomiting", "diarrhea", "stomach ache"],
            "response": "🤢 Likely Stomach Bug (Gastroenteritis) (80% match)\n• Hydrate with electrolytes\n• Bland diet\n• Rest"
        }
    }

    # Find best matching condition
    best_match_response = "🩺 Please consult a doctor for evaluation. Your symptoms are complex or don't match common conditions."
    highest_score = 0
    best_match_diagnosis_name = "Undetermined"

    for condition_name, data in conditions.items():
        match_score = sum(1 for keyword in data["keywords"] if keyword in symptoms_lower)
        if match_score > highest_score:
            highest_score = match_score
            best_match_response = data["response"]
            best_match_diagnosis_name = condition_name

    # Only return a specific diagnosis if at least two keywords match
    if highest_score >= 2:
        return best_match_diagnosis_name, best_match_response
    else:
        return best_match_diagnosis_name, "🩺 Please consult a doctor for evaluation. Your symptoms are complex or don't match common conditions."


def save_to_db(phone, symptoms, diagnosis, response, patient_name="Unknown"):
    """Safe database operation with context manager"""
    try:
        with sqlite3.connect(DATABASE_PATH) as conn:
            conn.execute('''INSERT INTO consultations
                            (phone, symptoms, diagnosis, response, patient_name)
                            VALUES (?, ?, ?, ?, ?)''',
                           (phone, symptoms, diagnosis, response, patient_name))
            last_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            app.logger.info(f"💾 Saved consultation ID: {last_id}") # Use app.logger
            return True
    except sqlite3.Error as e:
        app.logger.error(f"❌ Database Error during save: {e}", exc_info=True) # Log full traceback
        return False

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    # Get incoming data
    phone = request.values.get('From', '')
    incoming_msg = request.values.get('Body', '').strip()

    app.logger.info(f"\n=== INCOMING MESSAGE ===") # Use app.logger
    app.logger.info(f"From: {phone}") # Use app.logger
    app.logger.info(f"Content: '{incoming_msg}'") # Use app.logger

    # Prepare response
    resp = MessagingResponse()
    response_text = "" # Initialize response_text
    diagnosis_name = None # Initialize diagnosis_name

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
            app.logger.error(f"History retrieval Error: {e}", exc_info=True) # Log full traceback
    else:
        # Get diagnosis
        diagnosis_name, diagnosis_response = diagnose(incoming_msg)
        response_text = f"AI Doctor Report:\n\nSymptoms: {incoming_msg}\nDiagnosis: {diagnosis_response}"

    # Determine patient_name (you might want to add a way for users to set this)
    # For now, it defaults to 'Unknown' or can be extracted from a future command
    patient_name_for_save = "Unknown" # Placeholder, implement logic to get patient name if needed

    # Save to database and send response
    # Pass diagnosis_name to save_to_db, which will be None if not diagnosed
    if save_to_db(phone, incoming_msg, diagnosis_name, response_text, patient_name_for_save):
        resp.message(response_text)
    else:
        resp.message("⚠️ System error - your symptoms were not saved. Please try again.")

    return str(resp)

if __name__ == "__main__":
    # The 'r' prefix makes this a raw string, preventing SyntaxWarning for backslashes
    print(r"""
    _____ _    ___        __  ___          
   / ___/(_) / (_)____/ /_/   |  ________ 
   \__ \/ / / / / ___/ __/ /| | / ___/ _ \\
 ___/ / / / / (__  ) /_/ ___ |(__  )  __/
/____/_/_/_/_/____/\__/_/   |_/____/\___/ 
                                            
AI Doctor System Ready!""")
    # Set debug=False for production environments
    app.run(host='0.0.0.0', port=5000, debug=True)