import streamlit as st
import pandas as pd
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json

# Configura le credenziali di Google Sheets
def get_gsheet_client():
    # Carica le credenziali da st.secrets
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict)
    return gspread.authorize(creds)

# Funzioni per Google Sheets
def load_users_data(sheet_url):
    try:
        client = get_gsheet_client()
        sheet = client.open_by_url(sheet_url).worksheet("users")
        data = sheet.get_all_records()
        return data
    except Exception as e:
        st.error(f"Errore nel caricamento dati: {e}")
        return []

def save_user_data(sheet_url, user_info):
    try:
        client = get_gsheet_client()
        sheet = client.open_by_url(sheet_url).worksheet("users")
        # Aggiungi una nuova riga
        sheet.append_row([
            user_info["nome"],
            user_info["cognome"],
            user_info["età"],
            user_info["timestamp"]
        ])
        return True
    except Exception as e:
        st.error(f"Errore nel salvataggio: {e}")
        return False

# Show title and description.
st.title("💬 Chatbot")
st.write(
    "This is a simple chatbot that uses OpenAI's GPT-3.5 model to generate responses. "
    "To use this app, you need to provide an OpenAI API key, which you can get [here](https://platform.openai.com/account/api-keys)."
)

# Ask user for their OpenAI API key
openai_api_key = st.text_input("OpenAI API Key", type="password")

# Ask user for Google Sheets URL
sheet_url = st.text_input("Google Sheets URL", placeholder="https://docs.google.com/spreadsheets/d/...")

if not openai_api_key or not sheet_url:
    st.info("Please add your OpenAI API key and Google Sheets URL to continue.", icon="🗝️")
else:
    # Inizializza session state per i dati utente
    if "user_data_collected" not in st.session_state:
        st.session_state.user_data_collected = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = {"nome": "", "cognome": "", "età": ""}
    
    # Se i dati non sono stati raccolti, mostra il form
    if not st.session_state.user_data_collected:
        st.subheader("📋 Benvenuto! Per iniziare, compilare il modulo:")
        
        with st.form("user_info_form"):
            nome = st.text_input("Nome", placeholder="Inserisci il tuo nome")
            cognome = st.text_input("Cognome", placeholder="Inserisci il tuo cognome")
            eta = st.number_input("Età", min_value=1, max_value=150, step=1, value=18)
            
            submitted = st.form_submit_button("Inizia a chattare")
            
            if submitted:
                if nome and cognome:
                    # Salva i dati in session state
                    st.session_state.user_info = {
                        "nome": nome,
                        "cognome": cognome,
                        "età": int(eta),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # Salva i dati in Google Sheets
                    if save_user_data(sheet_url, st.session_state.user_info):
                        st.session_state.user_data_collected = True
                        st.rerun()
                    else:
                        st.error("Errore nel salvataggio dei dati")
                else:
                    st.error("Per favore, inserisci nome e cognome!")
    
    else:
        # Mostra i dati dell'utente
        st.success(f"✅ Benvenuto, {st.session_state.user_info['nome']} {st.session_state.user_info['cognome']}!")
        
        # Crea il client OpenAI
        client = OpenAI(api_key=openai_api_key)
        
        # Inizializza session state per i messaggi
        if "messages" not in st.session_state:
            st.session_state.messages = []
        
        # Mostra i messaggi della chat
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # Input per la chat
        if prompt := st.chat_input("Dimmi qualcosa..."):
            # Aggiungi il messaggio dell'utente
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Genera risposta
            stream = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ],
                stream=True,
            )
            
            # Stream della risposta
            with st.chat_message("assistant"):
                response = st.write_stream(stream)
            st.session_state.messages.append({"role": "assistant", "content": response})
        
        # Button per logout
        st.divider()
        if st.button("🔄 Logout"):
            st.session_state.user_data_collected = False
            st.session_state.messages = []
            st.rerun()