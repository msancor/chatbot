import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import time
from streamlit_autorefresh import st_autorefresh

# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="Everyday Norm Experiment - Phase 4",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================================================================
# CUSTOM CSS (INVARIATO)
# =============================================================================

st.markdown("""
<style>
* { font-family: 'Segoe UI', Trebuchet MS, sans-serif; }
html, body, [data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #f5f7fa 0%, #f8f9fb 100%);
}
[data-testid="stMainBlockContainer"] { padding: 2rem 3rem; }
.success-badge {
    background: #f0fdf4;
    color: #166534;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    border-left: 4px solid #22c55e;
    margin-bottom: 2rem;
    font-weight: 500;
}
.error {
    background: #fef2f2;
    color: #991b1b;
    padding: 1rem 1.5rem;
    border-radius: 8px;
    border-left: 4px solid #ef4444;
}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# GOOGLE SHEETS
# =============================================================================

def init_google_sheets():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        sheet_url = st.secrets["google_sheet_url"]

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)

        sheet = client.open_by_url(sheet_url).sheet1
        return sheet, True
    except Exception as e:
        print("Sheets error:", e)
        return None, False


def save_to_google_sheets(sheet, user_info, argumentation, content_tracking):
    sheet.append_row([
        user_info["prolific_id"],
        argumentation,
        json.dumps(content_tracking, ensure_ascii=False, indent=2),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ])

# =============================================================================
# SESSION STATE INIT
# =============================================================================

if "user_info" not in st.session_state:
    st.session_state.user_info = {
        "prolific_id": "TEST_USER_001",
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

if "argumentation_input" not in st.session_state:
    st.session_state.argumentation_input = ""

if "content_tracking" not in st.session_state:
    st.session_state.content_tracking = {}

if "tracking_start" not in st.session_state:
    st.session_state.tracking_start = time.monotonic()

if "last_tracked_second" not in st.session_state:
    st.session_state.last_tracked_second = -1

if "submitted" not in st.session_state:
    st.session_state.submitted = False

# =============================================================================
# AUTO REFRESH (1 SECONDO REALE)
# =============================================================================

st_autorefresh(interval=1000, key="second_tracker")

# =============================================================================
# TRACKING LOGIC (QUESTO FUNZIONA DAVVERO)
# =============================================================================

elapsed_seconds = int(time.monotonic() - st.session_state.tracking_start)

if not st.session_state.submitted:
    if elapsed_seconds != st.session_state.last_tracked_second:
        st.session_state.content_tracking[elapsed_seconds] = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": st.session_state.argumentation_input
        }
        st.session_state.last_tracked_second = elapsed_seconds

        print(
            f"[+{elapsed_seconds}s] "
            f"{len(st.session_state.argumentation_input.split())} words"
        )

# =============================================================================
# UI
# =============================================================================

st.markdown("""
<div class="success-badge">
Thank you for the conversation! Please provide your final thoughts below.
</div>
""", unsafe_allow_html=True)

st.markdown("""
### Final Question
Why is it **not appropriate to drink during a job interview**?
""")

argumentation = st.text_area(
    "Your argumentation",
    height=300,
    key="argumentation_input"
)

with st.form("submit_form"):
    submitted = st.form_submit_button("Submit and Complete")

if submitted and argumentation.strip():
    st.session_state.submitted = True

    sheet, connected = init_google_sheets()
    if connected:
        save_to_google_sheets(
            sheet,
            st.session_state.user_info,
            argumentation,
            st.session_state.content_tracking
        )
        st.success("✅ Data saved successfully.")
    else:
        st.error("❌ Google Sheets connection failed.")

    # DEBUG FINALE
    print("\n" + "=" * 60)
    print("FINAL TRACKING JSON")
    print(json.dumps(st.session_state.content_tracking, indent=2, ensure_ascii=False))
    print("=" * 60)

elif submitted:
    st.error("Please write something before submitting.")