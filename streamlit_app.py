import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
from openai import OpenAI
import time
import threading
from collections import OrderedDict

# Page configuration
st.set_page_config(
    page_title="Everyday Norm Experiment - Phase 4",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    * {
        font-family: 'Segoe UI', Trebuchet MS, sans-serif;
    }
    
    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #f5f7fa 0%, #f8f9fb 100%);
    }
    
    [data-testid="stMainBlockContainer"] {
        padding: 2rem 3rem;
    }
    
    [data-testid="stForm"] {
        background: white;
        padding: 2.5rem;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
        border: 1px solid #e5e7eb;
    }
    
    button[kind="primary"] {
        background: linear-gradient(135deg, #003d82 0%, #004a9e 100%);
        color: white !important;
        border: none !important;
        padding: 0.75rem 2rem !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        transition: all 0.3s ease;
        margin-top: 1.5rem;
    }
    
    button[kind="primary"]:hover {
        box-shadow: 0 4px 12px rgba(0, 61, 130, 0.3);
        transform: translateY(-1px);
    }
    
    .success-badge {
        background: #f0fdf4;
        color: #166534;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #22c55e;
        margin-bottom: 2rem;
        font-weight: 500;
    }
    
    [data-testid="chatAvatarIcon-assistant"], [data-testid="chatAvatarIcon-user"] {
        display: none !important;
    }
    
    [role="presentation"] [data-testid="stChatMessage"] {
        background: transparent !important;
        padding: 1rem 0 !important;
    }
    
    [data-testid="stChatMessageContent"] {
        background: white;
        padding: 1.25rem 1.5rem;
        border-radius: 10px;
        border: 1px solid #e5e7eb;
        line-height: 1.6;
        color: #333;
        font-size: 0.95rem;
    }
    
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageContent"] p) > div:first-child {
        margin-right: auto;
        max-width: 85%;
    }
    
    [data-testid="stChatMessage"]:last-child [data-testid="stChatMessageContent"] {
        background: linear-gradient(135deg, #f3f4f6 0%, #ffffff 100%);
    }
    
    [data-testid="stChatInputTextArea"] textarea {
        border: 1.5px solid #e5e7eb !important;
        border-radius: 8px !important;
        padding: 1rem !important;
        font-size: 0.95rem !important;
    }
    
    [data-testid="stChatInputTextArea"] textarea:focus {
        border-color: #003d82 !important;
        box-shadow: 0 0 0 3px rgba(0, 61, 130, 0.1) !important;
    }
    
    .timestamp {
        font-size: 0.8rem;
        color: #999;
        margin-top: 0.5rem;
    }
    
    [data-testid="stTextArea"] textarea {
        border: 1.5px solid #e5e7eb !important;
        border-radius: 8px !important;
        padding: 1rem !important;
        font-size: 0.95rem !important;
        font-family: 'Segoe UI', Trebuchet MS, sans-serif;
    }
    
    [data-testid="stTextArea"] textarea:focus {
        border-color: #003d82 !important;
        box-shadow: 0 0 0 3px rgba(0, 61, 130, 0.1) !important;
    }
    
    .error {
        background: #fef2f2;
        color: #991b1b;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #ef4444;
        font-size: 0.95rem;
    }
    
    .timer-badge {
        background: #eff6ff;
        color: #1e40af;
        padding: 0.75rem 1.25rem;
        border-radius: 6px;
        border-left: 3px solid #3b82f6;
        font-size: 0.9rem;
        margin-bottom: 1rem;
        font-weight: 500;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .tracking-indicator {
        display: inline-block;
        width: 8px;
        height: 8px;
        background: #22c55e;
        border-radius: 50%;
        margin-right: 8px;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# CONFIGURAZIONE GOOGLE SHEETS
# ============================================================================

def init_google_sheets():
    """Inizializza la connessione a Google Sheets"""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        sheet_url = st.secrets["google_sheet_url"]
        
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client_sheets = gspread.authorize(creds)
        
        spreadsheet = client_sheets.open_by_url(sheet_url)
        sheet = spreadsheet.sheet1
        
        return sheet, True
    except KeyError:
        return None, False
    except Exception as e:
        print(f"❌ Errore di connessione: {str(e)}")
        return None, False


def save_to_google_sheets(sheet, user_info, prompt_key, prompt_data, argumentation, word_tracking, final_chat_messages):
    """
    Salva i dati su Google Sheets alla fine della sessione.
    """
    try:
        final_chat_json = json.dumps(final_chat_messages or [], ensure_ascii=False, indent=2)
        
        # Formatta il word tracking con timestamp in millisecondi
        word_tracking_formatted = ""
        if word_tracking:
            # Calcola il tempo dall'inizio (in millisecondi)
            start_time = min(word_tracking.keys()) if word_tracking else 0
            tracking_by_elapsed_time = OrderedDict()
            
            for timestamp, data in sorted(word_tracking.items()):
                elapsed_ms = int((timestamp - start_time) * 1000)  # Converti in millisecondi
                tracking_by_elapsed_time[f"ms_{elapsed_ms}"] = {
                    "word_count": data["word_count"],
                    "char_count": data["char_count"],
                    "content_length": len(data["content"]),
                    "content_preview": data["content"][:100] if len(data["content"]) > 100 else data["content"]
                }
            
            word_tracking_formatted = json.dumps(
                tracking_by_elapsed_time,
                ensure_ascii=False,
                indent=2
            )
        
        sheet.append_row([
            user_info["prolific_id"],
            prompt_key,
            prompt_data["title"],
            argumentation,
            word_tracking_formatted,
            final_chat_json,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])
        return True
    except Exception as e:
        print(f"❌ Errore nel salvataggio: {str(e)}")
        return False


# ============================================================================
# HIGH-FREQUENCY BACKGROUND TRACKER - Traccia ogni 100ms
# ============================================================================

class HighFrequencyTracker(threading.Thread):
    """
    Thread in background che traccia il contenuto ogni 100ms (10 volte al secondo).
    Questo permette una granularità molto alta e cattura ogni piccolo cambiamento.
    """
    def __init__(self, session_state):
        super().__init__(daemon=True)
        self.session_state = session_state
        self.is_running = False
        self.tracking_interval = 0.1  # 100ms = 0.1 secondi
        self.last_content = ""
        self.samples_collected = 0
    
    def run(self):
        """Loop in background che traccia ogni 100ms"""
        self.is_running = True
        print(f"🟢 High-frequency tracker started (sampling every {int(self.tracking_interval * 1000)}ms)")
        
        while self.is_running:
            try:
                current_time = time.time()
                content = self.session_state.get("argumentation_input", "")
                
                # Calcola metriche
                word_count = len(content.split()) if content.strip() else 0
                char_count = len(content)
                
                # Salva nel tracking con timestamp preciso
                self.session_state.word_tracking[current_time] = {
                    "word_count": word_count,
                    "char_count": char_count,
                    "content": content
                }
                
                self.samples_collected += 1
                
                # Log solo quando il contenuto cambia (per evitare spam)
                if content != self.last_content:
                    elapsed = current_time - self.session_state.start_time
                    print(f"[{elapsed:.2f}s] 📝 Content changed: {word_count} words, {char_count} chars")
                    self.last_content = content
                
                # Aspetta 100ms prima del prossimo campionamento
                time.sleep(self.tracking_interval)
            
            except Exception as e:
                print(f"⚠️ Tracker error: {str(e)}")
                time.sleep(1)
    
    def stop(self):
        """Ferma il tracker"""
        self.is_running = False
        print(f"🔴 Tracker stopped. Total samples collected: {self.samples_collected}")


# ============================================================================
# Initialize session state
# ============================================================================

if "final_argumentation" not in st.session_state:
    st.session_state.final_argumentation = None
if "final_chat_messages" not in st.session_state:
    st.session_state.final_chat_messages = []
if "word_tracking" not in st.session_state:
    st.session_state.word_tracking = OrderedDict()
if "user_info" not in st.session_state:
    st.session_state.user_info = {
        "prolific_id": "TEST_USER_001",
        "start_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
if "sheet_connected" not in st.session_state:
    st.session_state.sheet_connected = False
if "selected_prompt_key" not in st.session_state:
    st.session_state.selected_prompt_key = "norm_test"
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
if "tracker" not in st.session_state:
    st.session_state.tracker = None
if "tracker_started" not in st.session_state:
    st.session_state.tracker_started = False

# Tentare la connessione a Google Sheets
sheet, is_connected = init_google_sheets()
st.session_state.sheet_connected = is_connected

# Avvia il tracker ad alta frequenza (solo una volta)
if not st.session_state.tracker_started:
    st.session_state.tracker = HighFrequencyTracker(st.session_state)
    st.session_state.tracker.start()
    st.session_state.tracker_started = True
    print("✅ High-frequency tracker initialized")

# ============================================================================
# UI - Pulita e semplice
# ============================================================================

st.markdown(f"""
<div class="success-badge">
    Thank you for the conversation! Please provide your final thoughts below.
</div>
""", unsafe_allow_html=True)

st.markdown("<h2 style='color: #1a1a1a; font-weight: 600; margin-bottom: 2rem;'>Final Question</h2>", unsafe_allow_html=True)

st.markdown("""
<p style='color: #666; margin-bottom: 1.5rem; font-size: 1rem;'>
    Please explain in detail why you believe it is <strong>not correct to drink during a job interview</strong>. 
    Share your reasoning and any relevant considerations.
</p>
""", unsafe_allow_html=True)

# Calcola statistiche in tempo reale
elapsed_time = time.time() - st.session_state.start_time
samples_count = len(st.session_state.word_tracking)
sampling_rate = samples_count / elapsed_time if elapsed_time > 0 else 0

# Timer badge con info dettagliate
st.markdown(f"""
<div class="timer-badge">
    <div>
        <span class="tracking-indicator"></span>
        <strong>High-Frequency Tracking Active</strong> • Session: {elapsed_time:.1f}s
    </div>
    <div style="font-size: 0.85rem; opacity: 0.8;">
        Samples: {samples_count} ({sampling_rate:.1f}/sec)
    </div>
</div>
""", unsafe_allow_html=True)

# Create two columns: form on left, AI Assistant on right
col_form, col_assistant = st.columns([2, 1])

with col_form:
    st.markdown("### Your Response")
    
    # Text area for argumentation
    argumentation = st.text_area(
        "Your argumentation:",
        placeholder="Type your explanation here...",
        height=300,
        label_visibility="collapsed",
        key="argumentation_input"
    )
    
    # Mostra statistiche in tempo reale
    if argumentation.strip():
        current_words = len(argumentation.split())
        current_chars = len(argumentation)
        st.caption(f"📊 **Current stats:** {current_words} words • {current_chars} characters • {samples_count} tracking samples")
    else:
        st.caption(f"💾 Auto-tracking: {samples_count} samples collected")
    
    # Form only for submit button
    with st.form("final_argumentation_form"):
        submitted = st.form_submit_button("Submit and Complete", use_container_width=True)

    if submitted:
        if argumentation.strip():
            st.session_state.final_argumentation = argumentation
            
            # Stop tracker
            if st.session_state.tracker:
                st.session_state.tracker.stop()
            
            # Calcola statistiche finali
            total_samples = len(st.session_state.word_tracking)
            duration = elapsed_time
            avg_sampling_rate = total_samples / duration if duration > 0 else 0
            
            # Print final summary to console (for debugging)
            print("\n" + "="*70)
            print("📊 FINAL SUBMISSION - HIGH-FREQUENCY TRACKING RESULTS")
            print("="*70)
            print(f"User: {st.session_state.user_info['prolific_id']}")
            print(f"Final word count: {len(argumentation.split())}")
            print(f"Final character count: {len(argumentation)}")
            print(f"Total tracking samples: {total_samples}")
            print(f"Session duration: {duration:.2f} seconds")
            print(f"Average sampling rate: {avg_sampling_rate:.2f} samples/second")
            print(f"Tracking interval: ~{1000/avg_sampling_rate:.0f}ms")
            print(f"\n📈 Tracking timeline (first 10 and last 10 samples):")
            
            # Mostra primi 10 samples
            start_time = st.session_state.start_time
            samples_list = list(st.session_state.word_tracking.items())
            
            print("\n  First 10 samples:")
            for i, (timestamp, data) in enumerate(samples_list[:10]):
                elapsed_ms = (timestamp - start_time) * 1000
                print(f"    [{elapsed_ms:7.0f}ms] {data['word_count']:3d} words, {data['char_count']:4d} chars")
            
            if total_samples > 20:
                print("\n  ...")
            
            print(f"\n  Last 10 samples:")
            for i, (timestamp, data) in enumerate(samples_list[-10:]):
                elapsed_ms = (timestamp - start_time) * 1000
                print(f"    [{elapsed_ms:7.0f}ms] {data['word_count']:3d} words, {data['char_count']:4d} chars")
            
            print("="*70 + "\n")
            
            # Try to save to database
            if st.session_state.sheet_connected:
                mock_prompt_data = {
                    "title": "Why not drink during job interview",
                    "description": "Professional conduct discussion"
                }
                
                success = save_to_google_sheets(
                    sheet,
                    st.session_state.user_info,
                    st.session_state.selected_prompt_key,
                    mock_prompt_data,
                    argumentation,
                    st.session_state.word_tracking,
                    st.session_state.final_chat_messages
                )
                
                if success:
                    st.markdown(f"""
                        <div class="success-badge">
                            ✅ Thank you for your participation! Your responses have been recorded.<br>
                            <small style="opacity: 0.8;">Captured {total_samples} high-frequency samples over {duration:.1f} seconds</small>
                        </div>
                    """, unsafe_allow_html=True)
                    print("✅ Data saved to Google Sheets")
                else:
                    st.markdown("<div class='error'>❌ Error saving data. Please try again.</div>", unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div class='error'>
                        ❌ Database connection error. Please contact the researcher.
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("<div class='error'>Please provide an argumentation to continue.</div>", unsafe_allow_html=True)

with col_assistant:
    st.markdown("### AI Assistant")
    
    # Display chat messages
    chat_container = st.container(border=True, height=400)
    with chat_container:
        if not st.session_state.final_chat_messages:
            st.markdown("<p style='color: #999; text-align: center;'>No messages yet. Start a conversation!</p>", unsafe_allow_html=True)
        else:
            for message in st.session_state.final_chat_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    st.markdown(f"<div class='timestamp'>{message.get('timestamp', 'N/A')}</div>", unsafe_allow_html=True)
    
    # Chat input
    if final_chat_prompt := st.chat_input("Ask something...", key="final_chat_input"):
        # Add user message
        st.session_state.final_chat_messages.append({
            "role": "user",
            "content": final_chat_prompt,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # Generate response
        try:
            # Mock response (without real API for testing)
            response_text = f"""This is a response to your question about professional conduct during interviews.
            
Drinking during a job interview is generally considered inappropriate because it can affect your professional image, impair your judgment, and show a lack of respect for the interviewer and the opportunity."""
            response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            st.session_state.final_chat_messages.append({
                "role": "assistant",
                "content": response_text,
                "timestamp": response_timestamp
            })
            
            st.rerun()
        
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

# Auto-refresh ogni 500ms per aggiornare le statistiche in tempo reale
time.sleep(0.5)
st.rerun()