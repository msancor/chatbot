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
    page_title="Everyday Norm Experiment",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# LOAD PROMPTS / NORMS
# ============================================================================
def load_json_from_file(path):
    if not os.path.exists(path):
        st.error(f"Missing file: {path}")
        st.stop()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

PROMPTS = load_json_from_file("prompts.json")
NORMS = load_json_from_file("norms.json")

# ============================================================================
# ATTENTION CHECK (SINGLE, FIXED)
# ============================================================================
ATTENTION_QUESTION = {
    "question": '''People get their news from a variety of sources, and in today’s world reliance on on-line news sources is increasingly common. 
    We want to know how much of your news consumption comes from on-line sources. We also want to know if people are paying attention to the question. 
    To show that you’ve read this much, please ignore the question and select “Television or print news only” as your answer. 
    About how much of your news consumption comes from on-line sources? Please include print newspapers that you read on-line (e.g., washingtonpost.com) as on-line sources."''',
    "options": ["On-line sources only", "Mostly on-line sources with some television and print news", "About half on-line sources", "Mostly television or print news with some on-line sources", "Television or print news only"],
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
        if len(row) >= 3:
            if (row[1], row[2]) in counts:
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
# SESSION STATE INITIALIZATION
# ============================================================================
DEFAULTS = {
    "attention_passed": False,
    "attention_start_time": None,
    "attention_response_time": None,
    "attention_response": None,
    "attention_correct": None,

    "user_data_collected": False,
    "initial_opinion_collected": False,
    "engagement_check_completed": False,

    "messages": [],
    "greeting_sent": False,
    "conversation_ended": False,
    "data_saved": False,
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================================
# PHASE 0 — ATTENTION CHECK (FIRST SCREEN)
# ============================================================================
if not st.session_state.attention_passed:

    if st.session_state.attention_start_time is None:
        st.session_state.attention_start_time = time.time()

    st.markdown("### Attention Check")

    response = st.radio(
        ATTENTION_QUESTION["question"],
        ATTENTION_QUESTION["options"]
    )

    if st.button("Continue"):
        st.session_state.attention_response = response
        st.session_state.attention_correct = (
            response == ATTENTION_QUESTION["correct"]
        )
        st.session_state.attention_response_time = (
            time.time() - st.session_state.attention_start_time
        )
        st.session_state.attention_passed = True
        st.rerun()

# ============================================================================
# PHASE 1 — AUTO PROLIFIC ID
# ============================================================================
elif not st.session_state.user_data_collected:

    prolific_id = st.query_params.get("PROLIFIC_PID")

    if not prolific_id:
        st.error("Prolific ID not detected. Please access the study via Prolific.")
        st.stop()

    if check_prolific_id_exists(sheet, prolific_id):
        st.error("This Prolific ID has already completed the study.")
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

# ============================================================================
# PHASE 2 — INITIAL OPINION
# ============================================================================
elif not st.session_state.initial_opinion_collected:

    norm = NORMS[st.session_state.norm_key]

    opinion = st.slider(
        f"Before starting, how much do you agree with the following statement?\n\n{norm['title']}",
        1, 100, 50
    )

    if st.button("Continue"):
        st.session_state.initial_opinion = opinion
        st.session_state.initial_opinion_collected = True
        st.rerun()

# ============================================================================
# PHASE 2.5 — ENGAGEMENT CHECK (FREE TEXT)
# ============================================================================
elif not st.session_state.engagement_check_completed:

    if "engagement_start_time" not in st.session_state:
        st.session_state.engagement_start_time = time.time()

    st.markdown("### Short Warm-Up Question")

    engagement_text = st.text_area(
        "If you could change one thing about the world what would it be and why? Please elaborate in a few sentences so we can better understand your perspective.",
        height=150
    )

    if st.button("Continue to Conversation"):
        st.session_state.engagement_text = engagement_text
        st.session_state.engagement_word_count = len(engagement_text.split())
        st.session_state.engagement_response_time = (
            time.time() - st.session_state.engagement_start_time
        )
        st.session_state.engagement_check_completed = True
        st.rerun()

# ============================================================================
# PHASE 3 — CHAT WITH LLM
# ============================================================================
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
            "timestamp": datetime.now().isoformat()
        })
        st.session_state.greeting_sent = True

    # Display conversation
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Count rounds
    assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    round_count = max(0, len(assistant_msgs) - 1)

    # Auto-end at 10 rounds
    if round_count >= 10:
        st.session_state.conversation_ended = True
        st.rerun()

    # Chat input
    if user_input := st.chat_input("Your response..."):

        user_message = {
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        }
        st.session_state.messages.append(user_message)

        with st.chat_message("user"):
            st.markdown(user_input)

        messages_for_api = [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]

        with st.chat_message("assistant"):
            stream = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages_for_api,
                stream=True
            )
            assistant_reply = st.write_stream(stream)

        st.session_state.messages.append({
            "role": "assistant",
            "content": assistant_reply,
            "timestamp": datetime.now().isoformat()
        })

        st.rerun()

    # End button after 3 rounds
    if round_count >= 3:
        if st.button("End Conversation"):
            st.session_state.conversation_ended = True
            st.rerun()

# ============================================================================
# PHASE 4 — FINAL OPINION & SAVE
# ============================================================================
elif not st.session_state.data_saved:

    final_opinion = st.slider(
        "After the conversation, how much do you agree with the statement?",
        1, 100, st.session_state.initial_opinion
    )

    if st.button("Submit and Complete"):

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

            # Attention check
            st.session_state.attention_response,
            st.session_state.attention_correct,
            st.session_state.attention_response_time,

            # Engagement check
            st.session_state.engagement_word_count,
            st.session_state.engagement_response_time,

            # Passive metrics
            len([m for m in st.session_state.messages if m["role"] == "user"]),
            user_word_count,
            total_duration,

            datetime.now().isoformat()
        ]

        save_to_google_sheets(sheet, row)
        st.session_state.data_saved = True
        st.rerun()

# ============================================================================
# PHASE 5 — THANK YOU
# ============================================================================
else:
    st.success("Thank you for your participation. Your responses have been recorded.")

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
# LOAD FILES
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
    We want to know how much of your news consumption comes from on-line sources. We also want to know if people are paying attention to the question. 
    To show that you’ve read this much, please ignore the question and select “Television or print news only” as your answer. 
    About how much of your news consumption comes from on-line sources? Please include print newspapers that you read on-line (e.g., washingtonpost.com) as on-line sources."''',
    "options": ["On-line sources only", "Mostly on-line sources with some television and print news", "About half on-line sources", "Mostly television or print news with some on-line sources", "Television or print news only"],
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
# SESSION STATE
# ============================================================================
DEFAULTS = {
    "phase": 0,
    "messages": [],
    "greeting_sent": False,
    "conversation_ended": False,
    "data_saved": False
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
# PHASE 3 — INITIAL OPINION (NOW IMMEDIATELY BEFORE LLM)
# ============================================================================
elif st.session_state.phase == 3:

    prolific_id = st.query_params.get("PROLIFIC_PID")
    if not prolific_id:
        st.error("Please access this study via Prolific.")
        st.stop()

    if "prolific_id" not in st.session_state:
        if check_prolific_id_exists(sheet, prolific_id):
            st.error("This Prolific ID has already completed the study.")
            st.stop()

        prompt_key, norm_key = get_least_used_combination(sheet, PROMPTS, NORMS)
        st.session_state.update({
            "prolific_id": prolific_id,
            "prompt_key": prompt_key,
            "norm_key": norm_key,
            "start_time": time.time()
        })

    norm = NORMS[st.session_state.norm_key]

    st.markdown("## Your Initial Opinion")
    st.markdown("Before the discussion begins, please indicate your view.")

    opinion = st.slider(
        norm["title"],
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

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    round_count = max(0, len(assistant_msgs) - 1)

    if round_count >= 10:
        st.session_state.phase = 5
        st.rerun()

    if user_input := st.chat_input("Type your response here"):
        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat()
        })

        with st.chat_message("assistant"):
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

    if round_count >= 3:
        if st.button("End Discussion"):
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

            st.session_state.engagement_word_count,
            st.session_state.engagement_response_time,

            len([m for m in st.session_state.messages if m["role"] == "user"]),
            user_word_count,
            total_duration,
            datetime.now().isoformat()
        ]

        save_to_google_sheets(sheet, row)
        st.session_state.data_saved = True
        st.rerun()

# ============================================================================
# PHASE 6 — THANK YOU
# ============================================================================
else:
    st.success("Thank you for your participation. You may now return to Prolific.")

