import html
import json
import os
import streamlit as st
from google import genai
from google.genai import types

from prompts import (
    QUICK_PROMPTS,
    SUMMARY_REQUEST_PROMPT,
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
)

# ---------------------------------------------------------
# Page Configuration & Modern Theme Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="Snap & Study 🎓 | AI Study Tutor",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    /* Modern Glassmorphic & Academic Aesthetic */
    .stApp {
        background: radial-gradient(circle at 15% 15%, rgba(99, 102, 241, 0.08) 0%, transparent 40%),
                    radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.06) 0%, transparent 40%);
    }
    .hero-card {
        padding: 1.25rem 1.5rem;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(139, 92, 246, 0.25);
        border-radius: 16px;
        backdrop-filter: blur(12px);
        margin-bottom: 1.25rem;
    }
    .badge {
        display: inline-block;
        font-size: 0.75rem;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        background: rgba(99, 102, 241, 0.15);
        color: #818cf8;
        border: 1px solid rgba(99, 102, 241, 0.3);
        font-weight: 600;
        margin-right: 0.5rem;
    }
    .channel-tag {
        font-size: 0.8rem;
        color: #94a3b8;
    }
    .quick-pill {
        border-radius: 20px !important;
        font-size: 0.8rem !important;
        padding: 0.3rem 0.8rem !important;
    }
    div[data-testid="stChatMessage"] {
        border-radius: 14px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.75rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Helper: Secrets & Credentials Resolver
# ---------------------------------------------------------
def get_secret(key: str, default: str = "") -> str:
    """Safely retrieves a configuration key from st.secrets or environment."""
    if hasattr(st, "secrets") and key in st.secrets:
        return str(st.secrets[key])
    return os.environ.get(key, default)


GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
MODEL_NAME = get_secret("GEMINI_MODEL", "gemini-2.5-flash")


@st.cache_resource
def get_gemini_client(api_key: str):
    """Initializes and caches the official Google GenAI client."""
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------
# Dispatch Engine: WhatsApp, Telegram & Email
# ---------------------------------------------------------
def clean_text_for_export(text: str, max_chars: int = 1500) -> str:
    """Cleans up whitespace and safely limits length for chat delivery."""
    if not text:
        return "No study summary notes available."
    cleaned = " ".join(text.split())
    if len(cleaned) > max_chars:
        return cleaned[: max_chars - 3] + "..."
    return cleaned


def send_whatsapp(to_number: str, user_name: str, summary: str):
    """Dispatches study summary to WhatsApp via Twilio (Content API or direct)."""
    account_sid = get_secret("TWILIO_ACCOUNT_SID")
    auth_token = get_secret("TWILIO_AUTH_TOKEN")
    from_number = get_secret("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    content_sid = get_secret("TWILIO_CONTENT_SID", "").strip()

    if not account_sid or not auth_token:
        return False, "Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) not found in secrets.toml."

    try:
        from twilio.rest import Client as TwilioClient

        twilio_client = TwilioClient(account_sid, auth_token)
        clean_summary = clean_text_for_export(summary, max_chars=1500)
        formatted_to = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number

        if content_sid:
            content_vars = json.dumps({"1": user_name, "2": clean_summary}, ensure_ascii=False)
            message = twilio_client.messages.create(
                from_=from_number,
                to=formatted_to,
                content_sid=content_sid,
                content_variables=content_vars,
            )
        else:
            body_text = f"🎓 Snap & Study Summary for {user_name}:\n\n{clean_summary}"
            message = twilio_client.messages.create(
                from_=from_number,
                to=formatted_to,
                body=body_text,
            )
        return True, message.sid
    except ImportError:
        return False, "Twilio library not installed. Run 'pip install twilio'."
    except Exception as error:
        return False, str(error)


def send_telegram(chat_id: str, user_name: str, summary: str):
    """Dispatches study summary to Telegram via Telegram Bot API."""
    bot_token = get_secret("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False, "TELEGRAM_BOT_TOKEN not configured in secrets.toml."

    import requests

    text = f"🎓 *Snap & Study: Revision Notes for {user_name}*\n\n{summary}"
    if len(text) > 4000:
        text = text[:3980] + "\n\n...(truncated)"

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        response = requests.post(url, json=payload, timeout=12)
        data = response.json()
        if data.get("ok"):
            return True, f"Message ID {data['result']['message_id']}"
        # Fallback to plain text if Markdown parsing failed
        payload["parse_mode"] = ""
        response = requests.post(url, json=payload, timeout=12)
        data = response.json()
        if data.get("ok"):
            return True, f"Message ID {data['result']['message_id']}"
        return False, data.get("description", "Unknown Telegram API response")
    except Exception as error:
        return False, str(error)


def send_email(to_email: str, user_name: str, summary: str):
    """Dispatches study summary via standard SMTP (Gmail, Outlook, or custom)."""
    smtp_server = get_secret("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(get_secret("SMTP_PORT", "587"))
    smtp_email = get_secret("SMTP_EMAIL")
    smtp_password = get_secret("SMTP_PASSWORD")
    sender_name = get_secret("SMTP_SENDER_NAME", "Snap & Study AI")

    if not smtp_email or not smtp_password:
        return False, "SMTP_EMAIL or SMTP_PASSWORD not configured in secrets.toml."

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎓 Snap & Study: Your Revision Notes for {user_name}"
        msg["From"] = f"{sender_name} <{smtp_email}>"
        msg["To"] = to_email

        body_plain = (
            f"Hey {user_name}!\n\n"
            "Here are your synthesized revision notes from your recent Snap & Study session:\n\n"
            f"{summary}\n\n"
            "Keep up the great study momentum!\n"
            "— Snap & Study 🎓"
        )
        msg.attach(MIMEText(body_plain, "plain", "utf-8"))

        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, [to_email], msg.as_string())

        return True, "Email delivered successfully"
    except Exception as error:
        return False, str(error)


def dispatch_summary(channel: str, destination: str, user_name: str, summary: str):
    """Routes export to the student's chosen delivery channel."""
    if channel == "WhatsApp":
        return send_whatsapp(destination, user_name, summary)
    elif channel == "Telegram":
        return send_telegram(destination, user_name, summary)
    elif channel == "Email":
        return send_email(destination, user_name, summary)
    return False, f"Unknown delivery channel: {channel}"


# ---------------------------------------------------------
# Sidebar: Settings & Channel Management
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### 🎓 Snap & Study Settings")
    st.caption("Customize your tutor and export preferences.")

    # API Key override if not present in secrets
    active_api_key = GEMINI_API_KEY
    if not active_api_key:
        active_api_key = st.text_input(
            "Gemini API Key",
            type="password",
            help="Get your free key from https://aistudio.google.com",
        )
        if active_api_key:
            st.session_state["gemini_api_key_override"] = active_api_key

    if "gemini_api_key_override" in st.session_state:
        active_api_key = st.session_state["gemini_api_key_override"]

    selected_model = st.selectbox(
        "Gemini Model",
        options=["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"],
        index=0,
    )

    if "onboarded" in st.session_state:
        st.divider()
        st.markdown("**Your Profile & Delivery:**")
        st.write(f"👤 Name: **{st.session_state.name}**")
        st.write(f"📡 Channel: **{st.session_state.channel}**")
        st.write(f"🎯 Target: `{st.session_state.destination}`")

        if st.button("✏️ Edit Profile / Channel", use_container_width=True):
            del st.session_state["onboarded"]
            st.rerun()

        if st.button("🗑️ Reset Chat Session", use_container_width=True):
            st.session_state.messages = []
            if active_api_key:
                client = get_gemini_client(active_api_key)
                st.session_state.chat = client.chats.create(
                    model=selected_model,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
                )
            st.rerun()


# ---------------------------------------------------------
# Step 1: Onboarding Gate
# ---------------------------------------------------------
if "onboarded" not in st.session_state:
    st.markdown(
        """
        <div class="hero-card">
            <span class="badge">AI Study Companion</span>
            <h1 style="margin: 0.5rem 0 0.25rem 0;">🎓 Snap & Study</h1>
            <p style="color: #94a3b8; margin: 0; font-size: 1.05rem;">
                Photograph any tricky problem, textbook diagram, or handwritten notes.
                Get crystal-clear explanations & text the study notes to your phone.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not active_api_key:
        st.warning("⚠️ Please provide a Gemini API Key in `.streamlit/secrets.toml` or the sidebar to begin.")

    with st.form("student_onboarding_form"):
        col1, col2 = st.columns([1, 1])
        with col1:
            name = st.text_input("Your Name", placeholder="e.g. Alex")
        with col2:
            channel = st.selectbox(
                "Export Notes Via",
                options=["WhatsApp", "Telegram", "Email"],
                index=0,
            )

        if channel == "WhatsApp":
            destination = st.text_input(
                "WhatsApp Number (with country code)",
                placeholder="+1XXXXXXXXXX or +91XXXXXXXXXX",
                help="Twilio Sandbox requires an initial join message before receiving notes.",
            )
        elif channel == "Telegram":
            destination = st.text_input(
                "Telegram Chat ID",
                placeholder="e.g. 123456789",
                help="Start a chat with your bot and send a message, or find your ID via @userinfobot.",
            )
        else:
            destination = st.text_input(
                "Email Address",
                placeholder="student@example.com",
                help="Your summary revision sheet will be emailed here.",
            )

        submitted = st.form_submit_button("Start Studying 🚀", use_container_width=True)

    if submitted:
        if not name.strip() or not destination.strip():
            st.warning("Please fill in both your name and your delivery destination.")
        elif not active_api_key:
            st.error("Please provide a Gemini API Key before proceeding.")
        else:
            st.session_state.name = name.strip()
            st.session_state.channel = channel
            st.session_state.destination = destination.strip()

            gemini_client = get_gemini_client(active_api_key)
            st.session_state.chat = gemini_client.chats.create(
                model=selected_model,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.session_state.last_summary = ""
            st.rerun()

    st.stop()


# ---------------------------------------------------------
# Step 2: Main Study Room Header & Export Action
# ---------------------------------------------------------
header_col, export_col = st.columns([5, 2], vertical_alignment="center")

with header_col:
    st.title("🎓 Snap & Study")
    st.markdown(
        f'<span class="channel-tag">Logged in as <b>{html.escape(st.session_state.name)}</b> · '
        f'Saving notes to <b>{html.escape(st.session_state.channel)}</b> (`{html.escape(st.session_state.destination)}`)</span>',
        unsafe_allow_html=True,
    )

with export_col:
    # Disable export until at least 1 Q&A exchange has occurred
    send_disabled = len(st.session_state.messages) <= 1
    button_label = f"📤 Send to {st.session_state.channel}"

    if st.button(button_label, disabled=send_disabled, use_container_width=True):
        with st.spinner("Compiling high-yield revision sheet..."):
            try:
                summary_response = st.session_state.chat.send_message(SUMMARY_REQUEST_PROMPT).text
                st.session_state.last_summary = summary_response
            except Exception as e:
                summary_response = f"Failed to generate summary: {e}"

        if st.session_state.last_summary:
            with st.spinner(f"Transmitting to {st.session_state.channel}..."):
                success, info = dispatch_summary(
                    st.session_state.channel,
                    st.session_state.destination,
                    st.session_state.name,
                    st.session_state.last_summary,
                )

            if success:
                st.success(f"Sent to {st.session_state.channel}! 📲 (ID: {info})")
            else:
                st.error(f"Dispatch notice: {info}")
                st.info("💡 You can still view, copy, or download your notes below!")

# If a summary exists, offer a revision preview expander
if st.session_state.get("last_summary"):
    with st.expander("📋 View Latest Pocket Revision Sheet", expanded=False):
        st.markdown(st.session_state.last_summary)
        st.download_button(
            label="💾 Download Notes (.md)",
            data=st.session_state.last_summary,
            file_name=f"snap_study_{st.session_state.name.lower()}_notes.md",
            mime="text/markdown",
            use_container_width=True,
        )


# ---------------------------------------------------------
# Step 3: Chat History Rendering
# ---------------------------------------------------------
def render_message(message):
    """Renders a single chat bubble (text or image)."""
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.markdown(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"], caption="Uploaded Problem / Notes", use_container_width=True)


def add_message(role: str, kind: str, content):
    """Appends to session history and immediately displays."""
    st.session_state.messages.append({"role": role, "kind": kind, "content": content})
    render_message(st.session_state.messages[-1])


# Initial welcome message
if not st.session_state.messages:
    welcome_text = WELCOME_MESSAGE_TEMPLATE.format(
        name=st.session_state.name,
        channel_name=st.session_state.channel,
    )
    add_message("assistant", "text", welcome_text)
else:
    for msg in st.session_state.messages:
        render_message(msg)


# ---------------------------------------------------------
# Step 4: Quick Study Assist Pills
# ---------------------------------------------------------
if len(st.session_state.messages) > 1:
    pill_cols = st.columns(4)
    for index, (label, prompt_text) in enumerate(QUICK_PROMPTS.items()):
        with pill_cols[index]:
            if st.button(label, key=f"quick_{index}", use_container_width=True):
                add_message("user", "text", prompt_text)
                with st.spinner("Analyzing with Gemini..."):
                    try:
                        ans = st.session_state.chat.send_message(prompt_text).text
                    except Exception as err:
                        ans = f"Sorry, something went wrong: {err}"
                add_message("assistant", "text", ans)
                st.rerun()


# ---------------------------------------------------------
# Step 5: Multimodal Input (Vision + Text)
# ---------------------------------------------------------
user_input = st.chat_input(
    "Ask a study question or attach a photo of your problem / diagram / notes...",
    accept_file=True,
    file_type=["jpg", "jpeg", "png", "webp"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    # 1. Attach and render photo if present
    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=photo.type))

    # 2. Attach text or fallback prompt if photo was submitted alone
    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        fallback_prompt = (
            "What is this academic problem, diagram, or page of notes? "
            "Please break down the core concept, explain it in plain language, "
            "and walk me through the step-by-step solution."
        )
        parts.append(fallback_prompt)

    # 3. Query Gemini multi-turn chat
    with st.spinner("Tutor is analyzing your problem & breaking down the concept..."):
        try:
            response = st.session_state.chat.send_message(parts).text
        except Exception as error:
            response = f"Sorry, something went wrong analyzing that: {error}"

    add_message("assistant", "text", response)
    st.rerun()
