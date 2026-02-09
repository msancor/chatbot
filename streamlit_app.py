import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from openai import OpenAI
import json
import os
import time
import random
from collections import defaultdict

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="Online Discussion Study",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# LOAD JSON FILES
# ============================================================================
def load_json(path):
    if not os.path.exists(path):
        st.error(f"Missing file: {path}")
        st.stop()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

PROMPTS = load_json("prompts.json")
NORMS = load_json("norms.json")

# ============================================================================
# COMPREHENSION QUESTION (MASKED ATTENTION CHECK)
# ============================================================================
COMPREHENSION_QUESTION = {
    "question": '''People get their news from a variety of sources, and in today’s world reliance on on-line news sources is increasingly common. 
    To show that you’ve read this much, please select “Television or print news only” as your answer.''',
    "options": [
        "On-line sources only",
        "Mostly on-line sources with some television and print news",
        "About half on-line sources",
        "Mostly television or print news with some on-line sources",
        "Television or print news only"
    ],
    "correct": "Television or print news only"
}

# ============================================================================
# GOOGLE SHEETS HELPERS
# ============================================================================
def check_prolific_id_exists(sheet, prolific_id):
    values = sheet.col_values(1)
    return prolific_id.lower() in [v.lower() for v in values[1:]]

def get_least_used_combination(sheet, prompts, norms):
    data = sheet.get_all_values()
    counts = defaultdict(int)
    for p in prompts:
        for n in norms:
            counts[(p, n)] = 0
    for row in data[1:]:
        if len(row) >= 3 and (row[1], row[2]) in counts:
            counts[(row[1], row[2])] += 1
    min_count = min(counts.values())
    return random.choice([k for k, v in counts.items() if v == min_count])

def save_to_google_sheets(sheet, row):
    sheet.append_row(row, value_input_option="RAW")

# ============================================================================
# SECRETS / CLIENTS
# ============================================================================
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)
sheet = gspread.authorize(creds).open_by_url(
    st.secrets["google_sheet_url"]
).sheet1

openai_client = OpenAI(api_key=st.secrets["openai_api_key"])

# ============================================================================
# PROLIFIC ID CHECK AT THE VERY START
# ============================================================================
prolific_id = st.query_params.get("PROLIFIC_PID", "")
if not prolific_id:
    st.error("Please access this study via Prolific to continue.")
    st.stop()

if "prolific_id" not in st.session_state:
    st.session_state.prolific_id = prolific_id

# Check PID only at the start
if "pid_checked" not in st.session_state:
    st.session_state.pid_checked = True
    if check_prolific_id_exists(sheet, prolific_id):
        st.error("This Prolific ID has already completed the study. You cannot participate again.")
        st.stop()

# ============================================================================
# SESSION STATE DEFAULTS
# ============================================================================
DEFAULTS = {
    "phase": 0,
    "messages": [],
    "greeting_sent": False,
    "conversation_ended": False,
    "data_saved": False,
    "generate_assistant": False
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================================
# PHASE 0 — WELCOME & INSTRUCTIONS
# ============================================================================
if st.session_state.phase == 0:
    st.markdown("## Welcome")
    st.markdown("""
    Thank you for taking part in this study.

    You will:
    - Answer a few short questions
    - Have a brief discussion with an AI system
    - Share your opinion before and after the discussion

    Please complete the study in one sitting and respond thoughtfully.
    """)
    if st.button("Begin"):
        st.session_state.phase = 1
        st.rerun()

# ============================================================================
# PHASE 1 — COMPREHENSION QUESTION
# ============================================================================
elif st.session_state.phase == 1:
    if "comp_start_time" not in st.session_state:
        st.session_state.comp_start_time = time.time()

    st.markdown("## Quick Question")
    st.markdown("Before continuing, please answer the following question.")

    response = st.radio(
        COMPREHENSION_QUESTION["question"],
        COMPREHENSION_QUESTION["options"]
    )

    if st.button("Continue"):
        st.session_state.comp_response = response
        st.session_state.comp_correct = response == COMPREHENSION_QUESTION["correct"]
        st.session_state.comp_response_time = time.time() - st.session_state.comp_start_time
        st.session_state.phase = 2
        st.rerun()

# ============================================================================
# PHASE 2 — BACKGROUND QUESTION (ENGAGEMENT)
# ============================================================================
elif st.session_state.phase == 2:
    if "engagement_start_time" not in st.session_state:
        st.session_state.engagement_start_time = time.time()

    st.markdown("## Background Question")
    st.markdown("""
    Please answer the question below in a few sentences.
    There is no right or wrong answer.
    """)

    text = st.text_area(
        "If you could change one thing about the world what would it be and why? Please elaborate in a few sentences so we can better understand your perspective.",
        height=150
    )

    if st.button("Continue"):
        st.session_state.engagement_text = text
        st.session_state.engagement_word_count = len(text.split())
        st.session_state.engagement_response_time = time.time() - st.session_state.engagement_start_time
        st.session_state.phase = 3
        st.rerun()

# ============================================================================
# PHASE 3 — INITIAL OPINION
# ============================================================================
elif st.session_state.phase == 3:
    if "prompt_key" not in st.session_state:
        prompt_key, norm_key = get_least_used_combination(sheet, PROMPTS, NORMS)
        st.session_state.prompt_key = prompt_key
        st.session_state.norm_key = norm_key
        st.session_state.start_time = time.time()

    norm_data = NORMS[st.session_state.norm_key]

    st.markdown("## Your Initial Opinion")
    st.markdown("Before the discussion begins, please indicate your view.")

    opinion = st.slider(
        norm_data["title"],
        1, 100, 50
    )

    if st.button("Start Discussion"):
        st.session_state.initial_opinion = opinion
        st.session_state.phase = 4
        st.rerun()

# ============================================================================
# PHASE 4 — CONVERSATION
# ============================================================================
elif st.session_state.phase == 4:
    prompt_data = PROMPTS[st.session_state.prompt_key]
    norm_data = NORMS[st.session_state.norm_key]
    system_prompt = prompt_data["system_prompt_template"].replace(
        "{NORM_DESCRIPTION}", norm_data["title"]
    )

    # Initial greeting
    if not st.session_state.greeting_sent:
        reply = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Start the discussion"}
            ]
        )
        st.session_state.messages.append({
            "role": "assistant",
            "content": reply.choices[0].message.content,
            "timestamp": datetime.now().isoformat()
        })
        st.session_state.greeting_sent = True
        st.rerun()

    # Display all messages
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Count conversation rounds
    assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    round_count = max(0, len(assistant_msgs) - 1)

    # Enforce max 10 rounds
    if round_count >= 10:
        st.session_state.phase = 5
        st.rerun()

    # Show chat input only if conversation not ended
    if not st.session_state.conversation_ended:
        if user_input := st.chat_input("Type your response here"):
            # Append and display user message first
            st.session_state.messages.append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().isoformat()
            })
            with st.chat_message("user"):
                st.markdown(user_input)

            # Flag to generate assistant reply in next rerun
            st.session_state.generate_assistant = True
            st.rerun()

    # Generate assistant reply
    if st.session_state.generate_assistant:
        st.session_state.generate_assistant = False
        stream = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system_prompt}] +
                     [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
            stream=True
        )
        reply_text = st.write_stream(stream)
        st.session_state.messages.append({
            "role": "assistant",
            "content": reply_text,
            "timestamp": datetime.now().isoformat()
        })
        st.rerun()

    # Show "End Discussion" after 2 rounds
    if round_count >= 2:
        if st.button("End Discussion"):
            st.session_state.conversation_ended = True
            st.session_state.phase = 5
            st.rerun()

# ============================================================================
# PHASE 5 — FINAL OPINION & SAVE
# ============================================================================
elif st.session_state.phase == 5 and not st.session_state.data_saved:
    st.markdown("## Final Opinion")
    final_opinion = st.slider(
        "After the discussion, how much do you agree with the statement?",
        1, 100, st.session_state.initial_opinion
    )

    if st.button("Submit Responses"):
        total_duration = time.time() - st.session_state.start_time
        user_word_count = sum(
            len(m["content"].split())
            for m in st.session_state.messages
            if m["role"] == "user"
        )

        row = [
            st.session_state.prolific_id,
            st.session_state.prompt_key,
            st.session_state.norm_key,
            st.session_state.initial_opinion,
            json.dumps(st.session_state.messages, ensure_ascii=False),
            final_opinion,
            st.session_state.comp_response,
            st.session_state.comp_correct,
            st.session_state.comp_response_time,
            st.session_state.engagement_text,
            st.session_state.engagement_word_count,
            st.session_state.engagement_response_time,
            len([m for m in st.session_state.messages if m["role"] == "user"]),
            user_word_count,
            total_duration,
            datetime.now().isoformat()
        ]

        save_to_google_sheets(sheet, row)
        st.session_state.data_saved = True
        st.session_state.phase = 6
        st.rerun()

# ============================================================================
# PHASE 6 — THANK YOU & PROLIFIC REDIRECT
# ============================================================================
if st.session_state.phase >= 6:

    st.markdown("## Thank you for your participation")
    st.markdown("""
    Your responses have been successfully recorded.

    The link below will redirect you immediately to Prolific:""")

    # Replace with your actual Prolific completion code
    prolific_id = st.session_state.get("prolific_id", "")
    # Safe placeholder for testing; replace with your real Prolific completion code
    completion_base_url = "https://www.prolific.co/"
    completion_url = f"{completion_base_url}?PROLIFIC_PID={prolific_id}"

    st.markdown(f"[Return to Prolific immediately]({completion_url})", unsafe_allow_html=True)
