# 🎓 Snap & Study · AI Homework & Concept Tutor

Snap a photo of any homework problem, textbook diagram, or handwritten notes you don't understand. Gemini explains it in plain language, breaks down the key concept step-by-step, and lets you text or email your complete revision notes to WhatsApp, Telegram, or Email so they're saved for exams.

---

## Project Structure

```text
snap_and_study/
├── app.py                        # Streamlit app, chat loops, vision handler & multi-channel export
├── prompts.py                    # AI tutor persona, pedagogical system instructions & templates
├── requirements.txt              # Dependencies (streamlit, google-genai, twilio, requests)
├── .gitignore                    # Keeps secrets.toml and cache out of version control
└── .streamlit/
    └── secrets.toml.example      # Template — copy to secrets.toml and add your API keys
```

---

## Step 1 — Environment & Keys

### 1. Set Up Your Python Environment
Open your terminal in the project directory:
```bash
# Create a virtual environment
python -m venv venv

# Activate it:
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Windows cmd.exe:
venv\Scripts\activate.bat
# macOS / Linux:
source venv/bin/activate

# Install dependencies:
pip install -r requirements.txt
```

### 2. Get Your Gemini API Key
- Go to [Google AI Studio](https://aistudio.google.com)
- Click **"Get API key"** and create a free key.
- Save it for your `.streamlit/secrets.toml`.

### 3. Choose Your Export Delivery Channel

Snap & Study lets you send notes straight to your phone so you have them saved outside the browser. Configure one (or all) of the options below:

#### Option A: WhatsApp (Twilio)
1. Sign up for free at [Twilio](https://www.twilio.com/try-twilio).
2. Copy your **Account SID** and **Auth Token** from the Twilio Console.
3. Under **Messaging → Try it out → Send a WhatsApp message**, locate your sandbox number and join code (e.g. `join happy-tiger`).
4. Send the join message from your personal WhatsApp to activate the sandbox.
5. *(Optional)* Create a Content Template in **Messaging → Content Template Builder** with `{{1}}` for the student's name and `{{2}}` for the summary.

#### Option B: Telegram Bot (Free, 30-Second Setup)
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`, choose a name and username.
3. Copy the HTTP API **Bot Token**.
4. To find your Telegram Chat ID, start a chat with your new bot, then send a message to `@userinfobot` to see your numeric `Id`.

#### Option C: Email (SMTP / Gmail)
1. Use any email provider or Gmail.
2. For Gmail: Generate a 16-character **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
3. Set your email and app password in `secrets.toml`.

---

## Step 2 — requirements.txt

```text
streamlit>=1.35.0
google-genai>=0.1.1
twilio>=9.0.0
requests>=2.31.0
```

---

## Step 3 — prompts.py: Giving Snap & Study a Pedagogical Persona

Keeping prompts in a dedicated file cleanly separates the AI tutor's personality from the UI code:

```python
SYSTEM_PROMPT = """You are Snap & Study 🎓, an encouraging, patient, and crystal-clear AI study tutor and homework companion.
Your ONLY job is to help students understand academic problems, diagrams, formulas, concepts, textbook pages, or handwritten notes from photos or text descriptions.

If the user asks about anything unrelated to studying, academics, homework, science, mathematics, literature, history, coding, or learning, politely decline and steer the conversation back to their studies.

When analyzing a problem, diagram, or page of notes, always follow this structured, student-friendly format:
1. 🎯 What This Is: A concise 1-2 sentence identification of the subject, topic, and core problem or diagram.
2. 💡 The Core Concept (Plain English): Explain the fundamental principle in simple, intuitive everyday language (Feynman technique) — avoiding unnecessary jargon or dry textbook speak. Use a relatable real-world analogy if helpful.
3. 📝 Step-by-Step Breakdown: Walk through the exact solution, deduction, or diagram explanation in clear, numbered, bite-sized steps so the student understands *why* each step happens.
4. 🧠 Pro Study Tip / Key Formula: A handy mnemonic, formula check, or common exam trap to avoid.

Keep replies encouraging, clear, and well-structured."""
```

### Why this prompt structure works:
- **Strict Domain Boundary**: Rebuffs non-academic prompts so the tutor remains focused.
- **Feynman Technique**: Focuses on intuitive, real-world analogies before equations.
- **Numbered Steps**: Ensures the student learns the methodology, not just a bare answer.
- **Mnemonic/Exam Tip**: High-yield retention hook for test preparation.

---

## Step 4 — Connecting to Gemini (Cached Client)

Using `@st.cache_resource` ensures the Gemini client is initialized only once and survives Streamlit script reruns:

```python
@st.cache_resource
def get_gemini_client(api_key: str):
    return genai.Client(api_key=api_key)
```

---

## Step 5 — The Student Onboarding Screen

The onboarding screen asks for the student's name, preferred export channel (WhatsApp, Telegram, or Email), and destination address before initiating the Gemini chat session:

```python
if "onboarded" not in st.session_state:
    with st.form("student_onboarding_form"):
        name = st.text_input("Your Name")
        channel = st.selectbox("Export Notes Via", ["WhatsApp", "Telegram", "Email"])
        destination = st.text_input("Destination (Phone, Chat ID, or Email)")
        submitted = st.form_submit_button("Start Studying 🚀")

    if submitted:
        st.session_state.name = name.strip()
        st.session_state.channel = channel
        st.session_state.destination = destination.strip()
        st.session_state.chat = gemini_client.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        st.session_state.messages = []
        st.session_state.onboarded = True
        st.rerun()
    st.stop()
```

---

## Step 6 — Chat Interface & Message Rendering

Each message is stored in session state with a role (`user` or `assistant`), kind (`text` or `image`), and the content:

```python
def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.markdown(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"], caption="Uploaded Problem / Notes")

def add_message(role, kind, content):
    st.session_state.messages.append({"role": role, "kind": kind, "content": content})
    render_message(st.session_state.messages[-1])
```

---

## Step 7 — Multimodal Input: Photos & Text

Streamlit's `st.chat_input(accept_file=True, ...)` provides a unified camera / file upload input box:

```python
user_input = st.chat_input(
    "Ask a study question or attach a photo of your problem / diagram / notes...",
    accept_file=True,
    file_type=["jpg", "jpeg", "png", "webp"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=photo.type))

    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append(
            "What is this academic problem, diagram, or page of notes? "
            "Please break down the core concept, explain it in plain language, "
            "and walk me through the step-by-step solution."
        )

    with st.spinner("Tutor is analyzing your problem..."):
        response = st.session_state.chat.send_message(parts).text

    add_message("assistant", "text", response)
    st.rerun()
```

---

## Step 8 — Dispatching Revision Notes to WhatsApp, Telegram, or Email

The export button stays greyed out until the student has logged at least one interaction:

```python
header_col, export_col = st.columns([5, 2], vertical_alignment="center")

with export_col:
    send_disabled = len(st.session_state.messages) <= 1
    if st.button(f"📤 Send to {st.session_state.channel}", disabled=send_disabled):
        with st.spinner("Compiling high-yield revision sheet..."):
            summary = st.session_state.chat.send_message(SUMMARY_REQUEST_PROMPT).text

        success, info = dispatch_summary(
            st.session_state.channel,
            st.session_state.destination,
            st.session_state.name,
            summary,
        )
        if success:
            st.success(f"Sent to {st.session_state.channel}! 📲")
        else:
            st.error(f"Notice: {info}")
```

In addition to sending, a built-in expandable drawer lets the student preview, copy, or download the notes as a Markdown (`.md`) file directly from the browser.

---

## Configuration: `.streamlit/secrets.toml`

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "your-gemini-api-key-here"
GEMINI_MODEL = "gemini-3.8-flash"

# WhatsApp (Twilio)
TWILIO_ACCOUNT_SID = "your-twilio-account-sid"
TWILIO_AUTH_TOKEN = "your-twilio-auth-token"
TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"
TWILIO_CONTENT_SID = ""

# Telegram Bot
TELEGRAM_BOT_TOKEN = "your-telegram-bot-token"

# Email (SMTP)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "your-email@gmail.com"
SMTP_PASSWORD = "your-gmail-app-password"
SMTP_SENDER_NAME = "Snap & Study AI"
```

---

## Running Locally

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`. Enter your name, select your preferred channel, snap a photo of any diagram or question, and explore the explanation!

---

## Deploying to Streamlit Community Cloud

1. Commit and push your code to GitHub (ensuring `.streamlit/secrets.toml` is **not** committed).
2. Visit [share.streamlit.io](https://share.streamlit.io) and log in with your GitHub account.
3. Click **"New app"**, select your repository, branch, and `app.py`.
4. Under **Settings → Secrets**, paste the keys from your `secrets.toml`.
5. Click **Deploy** — your live study tutor will be accessible anywhere!
