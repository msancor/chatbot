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

# ================================
# PAGE CONFIG
# ================================
st.set_page_config(
    page_title="Everyday Norm Experiment",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================================
# LOAD PROMPTS / NORMS
# ================================
def load_json_from_file(file_path):
    if not os.path.exists(file_path):
        st.error(f"Missing file: {file_path}")
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

PROMPTS = load_json_from_file("prompts.json")
NORMS = load_json_from_file("norms.json")

# ================================
# GOOGLE SHEETS HELPERS
# ================================
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
        if len(row) >= 3:
            counts[(row[1], row[2])] += 1

    min_count = min(counts.values())
    return random.choice([k for k, v in counts.items() if v == min_count])

def save_to_google_sheets(sheet, row):
    sheet.append_row(row, value_input_option="RAW")

# ================================
# SECRETS / CLIENTS
# ================================
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

# ================================
# SESSION STATE
# ================================
defaults = {
    "user_data_collected": False,
    "initial_opinion_collected": False,
    "messages": [],
    "greeting_sent": False,
    "conversation_ended": False,
    "data_saved": False,
    "instruction_check_passed": False,
    "instruction_issued": False,
    "attention_check_response": None,
    "timing": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ================================
# PHASE 1 — AUTO PROLIFIC ID
# ================================
if not st.session_state.user_data_collected:

    prolific_id = st.query_params.get("PROLIFIC_PID")

    if not prolific_id:
        st.error("Missing Prolific ID. Please return via Prolific.")
        st.stop()

    if check_prolific_id_exists(sheet, prolific_id):
        st.error("This Prolific ID has already participated.")
        st.stop()

    prompt_key, norm_key = get_least_used_combination(sheet, PROMPTS, NORMS)

    st.session_state.update({
        "prolific_id": prolific_id,
        "prompt_key": prompt_key,
        "norm_key": norm_key,
        "start_time": time.time(),
        "user_data_collected": True
    })

    st.rerun()

# ================================
# PHASE 2 — INITIAL OPINION
# ================================
elif not st.session_state.initial_opinion_collected:

    norm = NORMS[st.session_state.norm_key]

    opinion = st.slider(
        f"Before starting, how much do you agree with: {norm['title']}?",
        1, 100, 50
    )

    if st.button("Start Conversation"):
        st.session_state.initial_opinion = opinion
        st.session_state.initial_opinion_collected = True
        st.rerun()

# ================================
# PHASE 3 — CHAT
# ================================
elif not st.session_state.conversation_ended:

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
                {"role": "user", "content": "Start the conversation"}
            ]
        )
        st.session_state.messages.append({
            "role": "assistant",
            "content": reply.choices[0].message.content,
            "timestamp": time.time()
        })
        st.session_state.greeting_sent = True

    # Display messages
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Count rounds
    assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    round_count = max(0, len(assistant_msgs) - 1)

    # Auto end at 10
    if round_count >= 10:
        st.session_state.conversation_ended = True
        st.rerun()

    # Chat input
    if user_msg := st.chat_input("Your response"):
        st.session_state.messages.append({
            "role": "user",
            "content": user_msg,
            "timestamp": time.time()
        })

        # Conversational instruction check (issued once at round 2)
        if round_count == 1 and not st.session_state.instruction_issued:
            user_msg += "\n\n(Instruction: Please start your next reply with the word 'Blue'.)"
            st.session_state.instruction_issued = True

        # Detect instruction compliance
        if st.session_state.instruction_issued and not st.session_state.instruction_check_passed:
            if user_msg.strip().lower().startswith("blue"):
                st.session_state.instruction_check_passed = True

        api_messages = [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
        ]

        stream = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=api_messages,
            stream=True
        )

        with st.chat_message("assistant"):
            reply = st.write_stream(stream)

        st.session_state.messages.append({
            "role": "assistant",
            "content": reply,
            "timestamp": time.time()
        })

        st.rerun()

    # End button after 3 rounds
    if round_count >= 3:
        if st.button("End Conversation"):
            st.session_state.conversation_ended = True
            st.rerun()

# ================================
# PHASE 4 — FINAL OPINION + ATTENTION CHECK
# ================================
elif not st.session_state.data_saved:

    final_opinion = st.slider("Final opinion", 1, 100, st.session_state.initial_opinion)

    attention = st.radio(
        "To confirm attention, please select 'Strongly Agree'.",
        ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"]
    )

    if st.button("Submit"):
        duration = time.time() - st.session_state.start_time

        row = [
            st.session_state.prolific_id,
            st.session_state.prompt_key,
            st.session_state.norm_key,
            st.session_state.initial_opinion,
            json.dumps(st.session_state.messages),
            final_opinion,
            attention,
            st.session_state.instruction_check_passed,
            duration,
            sum(len(m["content"].split()) for m in st.session_state.messages if m["role"] == "user"),
            datetime.now().isoformat()
        ]

        save_to_google_sheets(sheet, row)
        st.session_state.data_saved = True
        st.rerun()

# ================================
# PHASE 5 — THANK YOU
# ================================
else:
    st.success("Thank you! Your responses have been recorded.")
