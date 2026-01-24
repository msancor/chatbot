import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

st.title("📝 Salva il Tuo Nome")

try:
    # Carica le credenziali e l'URL da secrets.toml
    creds_dict = st.secrets["gcp_service_account"]
    sheet_url = st.secrets["google_sheet_url"]
    
    # Configura le credenziali con gli scope corretti
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # Apri il foglio
    spreadsheet = client.open_by_url(sheet_url)
    sheet = spreadsheet.sheet1
    
    # Form per inserire il nome
    with st.form("name_form"):
        nome = st.text_input("Nome", placeholder="Inserisci il tuo nome")
        email = st.text_input("Email", placeholder="Inserisci la tua email")
        
        submitted = st.form_submit_button("Salva")
        
        if submitted:
            if nome and email:
                sheet.append_row([
                    nome,
                    email,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])
                st.success(f"✅ Nome '{nome}' salvato!")
            else:
                st.error("Compila tutti i campi!")
    
    # Mostra i dati
    st.divider()
    st.subheader("📊 Dati salvati")
    data = sheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nessun dato ancora")
        
except KeyError:
    st.error("Errore: Configura 'gcp_service_account' e 'google_sheet_url' nel file secrets.toml")
except Exception as e:
    st.error(f"Errore: {e}")