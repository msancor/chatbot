import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# Configura le credenziali di Google Sheets
def get_gsheet_client():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Errore nell'autenticazione: {e}")
        return None

# Carica i dati da Google Sheets
def load_data(sheet_url):
    try:
        client = get_gsheet_client()
        if client:
            sheet = client.open_by_url(sheet_url).worksheet("nomi")
            data = sheet.get_all_records()
            return data
        return []
    except Exception as e:
        st.error(f"Errore nel caricamento dati: {e}")
        return []

# Salva il nome su Google Sheets
def save_name(sheet_url, nome, email):
    try:
        client = get_gsheet_client()
        if client:
            sheet = client.open_by_url(sheet_url).worksheet("nomi")
            sheet.append_row([
                nome,
                email,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
            return True
    except Exception as e:
        st.error(f"Errore nel salvataggio: {e}")
        return False

# Titolo e descrizione
st.title("📝 Salva il Tuo Nome")
st.write("Inserisci il tuo nome e salvalo su Google Sheets")

# Input per Google Sheets URL
sheet_url = st.text_input(
    "Google Sheets URL",
    placeholder="https://docs.google.com/spreadsheets/d/..."
)

if not sheet_url:
    st.info("Per favore, inserisci l'URL del Google Sheets per continuare.", icon="🗝️")
else:
    # Crea il form
    with st.form("name_form"):
        nome = st.text_input("Nome", placeholder="Inserisci il tuo nome")
        email = st.text_input("Email", placeholder="Inserisci la tua email")
        
        submitted = st.form_submit_button("Salva")
        
        if submitted:
            if nome and email:
                if save_name(sheet_url, nome, email):
                    st.success(f"✅ Nome '{nome}' salvato con successo!")
            else:
                st.error("Per favore, compila tutti i campi!")
    
    # Mostra i dati salvati
    st.divider()
    st.subheader("📊 Nomi salvati")
    
    data = load_data(sheet_url)
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nessun nome salvato ancora.")