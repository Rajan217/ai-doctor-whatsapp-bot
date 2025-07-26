# AI Doctor WhatsApp Bot  
MADE BY RAJAN PANDIT 

## Features  
- Symptom diagnosis via WhatsApp  
- Simulated ML training notebook  

## How to Run  
1. Install dependencies:  
   ```bash
   pip install -r requirements.txt
   Here are the steps to interact with your deployed AI Doctor WhatsApp bot:

1.  **Ensure Your Render Service is Live:**
    * Go to your Render Dashboard: [https://dashboard.render.com/](https://dashboard.render.com/)
    * Navigate to your `ai-doctor-whatsapp-bot` service.
    * Confirm that its status is **"Live"**. If it's not, check the deployment logs for any errors and resolve them, then trigger a manual deploy.

2.  **Verify Twilio Webhook Configuration:**
    * Go to your Twilio Console: [https://www.twilio.com/console](https://www.twilio.com/console)
    * Navigate to **Develop > Messaging > Try it out > WhatsApp Sandbox**.
    * In the "WHEN A MESSAGE COMES IN" field, ensure it is set to your Render URL followed by `/whatsapp`:
        `https://ai-doctor-whatsapp-bot.onrender.com/whatsapp`
    * Ensure the dropdown next to it is set to `HTTP POST`.
    * Click **"Save"** if you make any changes.

3.  **Send a Message from WhatsApp:**
    * Open WhatsApp on your phone.
    * Send a message to your Twilio Sandbox number (`whatsapp:+14155238886`).
    * **Try these messages:**
        * `hello` (should get a greeting)
        * `fever and headache` (should get a diagnosis from the AI)
        * `nausea and vomiting` (should get a diagnosis from the AI)
        * `history` (should retrieve your last few consultations)
        * `my arm hurts` (should get a general AI response)

4.  **Check Render Logs (for debugging/monitoring):**
    * After sending messages, go back to your Render Dashboard.
    * Navigate to your `ai-doctor-whatsapp-bot` service.
    * Click on the **"Logs"** tab on the left-hand side.
    * You should see entries like:
        * `INFO:app:=== INCOMING MESSAGE ===`
        * `INFO:app:From: whatsapp:+[Your WhatsApp Number]`
        * `INFO:app:Content: '[Your Message]'`
        * `INFO:app:Calling Gemini API for diagnosis...` (if you send symptoms)
        * `INFO:app:💾 Saved consultation ID: [number]` (confirming database save)
        * Any `ERROR:app:` messages if something went wrong during processing.

Your bot is now fully deployed and ready to interact with via WhatsApp!
