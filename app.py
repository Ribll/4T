import streamlit as st
import yfinance as yf
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Configurazione della pagina Streamlit (Stile Dashboard)
st.set_page_config(page_title="Trading Desk - Pair Trading", layout="wide")
st.title("📊 Trading Desk - Sistema Automatico Z-Score")

# =========================================================
# RECUPERO CHIAVI API (SISTEMA ROBUSTO MULTI-METODO)
# =========================================================
API_KEY = None
SECRET_KEY = None

# Metodo 1: Lettura standard da dizionario st.secrets
if "ALPACA_API_KEY" in st.secrets:
    API_KEY = st.secrets["ALPACA_API_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET_KEY"]
# Metodo 2: Lettura da sotto-sezione (eredità TOML)
elif hasattr(st.secrets, "secrets") and "ALPACA_API_KEY" in st.secrets.secrets:
    API_KEY = st.secrets.secrets["ALPACA_API_KEY"]
    SECRET_KEY = st.secrets.secrets["ALPACA_SECRET_KEY"]

# Se non ha trovato nulla, stampiamo un debug per capire cosa vede Streamlit
if not API_KEY or not SECRET_KEY:
    st.error("⚠️ Chiavi API non trovate nei Secrets!")
    st.write("Chiavi rilevate attualmente nel pannello Streamlit:", list(st.secrets.keys()))
    st.stop()

# Connessione ad Alpaca
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# ==========================================
# COLONNA DI SINISTRA: STATO DEL CONTO LIVE
# ==========================================
col1, col2 = st.columns([1, 2])

with col1:
    st.header("💰 Stato Portafoglio")
    try:
        account = trading_client.get_account()
        st.metric(label="Saldo Totale (Paper)", value=f"${float(account.equity):,.2f}")
        st.metric(label="Potere d'Acquisto", value=f"${float(account.buying_power):,.2f}")
        
        # Mostra le posizioni aperte
        st.subheader("Posizioni Attive")
        posizioni = trading_client.get_all_positions()
        if posizioni:
            for p in posizioni:
                st.write(f"**{p.symbol}**: {p.qty} quote (Valore: ${float(p.market_value):,.2f})")
        else:
            st.info("Nessuna posizione aperta al momento.")
    except Exception as e:
        st.error(f"Errore di connessione ad Alpaca: {e}")

# ==========================================
# COLONNA DI DESTRA: ANALISI DATI E GRAFICI
# ==========================================
with col2:
    st.header("📈 Analisi di Mercato Real-Time")
    
    # Pulsante per aggiornare manualmente
    if st.button("🔄 Aggiorna e Controlla Segnali Ora"):
        st.write("Scaricamento dati in corso...")
        
        # Scarica dati
        nasdaq = yf.download("^NDX", period="2000d", progress=False, auto_adjust=True)
        sp500 = yf.download("^GSPC", period="2000d", progress=False, auto_adjust=True)

        data = pd.DataFrame({
            "nasdaq": nasdaq["Close"].iloc[:, 0] if isinstance(nasdaq["Close"], pd.DataFrame) else nasdaq["Close"],
            "sp500": sp500["Close"].iloc[:, 0] if isinstance(sp500["Close"], pd.DataFrame) else sp500["Close"]
        }).dropna()

        # Calcoli
       # NUOVO CODICE - rendimenti giornalieri
        data["nasdaq_ret"] = data["nasdaq"].pct_change()
        data["sp500_ret"] = data["sp500"].pct_change()
        data["spread"] = data["nasdaq_ret"] - data["sp500_ret"]
        data = data.dropna()  # pct_change genera un NaN alla prima riga, va rimosso
        
        window = 60
        data["mean"] = data["spread"].rolling(window).mean()
        data["std"] = data["spread"].rolling(window).std()
        data["zscore"] = (data["spread"] - data["mean"]) / data["std"]
        ultimo_zscore = data["zscore"].iloc[-1]
        
        # Mostra lo Z-Score con colore dinamico
        if abs(ultimo_zscore) > 2:
            st.error(f"🔴 Z-SCORE ATTUALE: {ultimo_zscore:.2f} (Soglia superata!)")
        else:
            st.success(f"🟢 Z-SCORE ATTUALE: {ultimo_zscore:.2f} (In zona neutra)")

        # Mostra il grafico dello Z-Score
        st.line_chart(data["zscore"])

        # ----------------------------------------
        # PANNELLO DIAGNOSTICA Z-SCORE
        # ----------------------------------------
        st.subheader("🔬 Diagnostica Z-Score")
        
        col_d1, col_d2, col_d3, col_d4 = st.columns(4)
        
        with col_d1:
            st.metric("Z-Score Attuale", f"{ultimo_zscore:.2f}")
        with col_d2:
            st.metric("Massimo (periodo)", f"{data['zscore'].max():.2f}")
        with col_d3:
            st.metric("Minimo (periodo)", f"{data['zscore'].min():.2f}")
        with col_d4:
            st.metric("Deviazione Std Z", f"{data['zscore'].std():.2f}")

        # Conteggio segnali
        soglia = 2.0  # cambia qui se vuoi testare soglie diverse
        segnali_long = (data["zscore"] < -soglia).sum()
        segnali_short = (data["zscore"] > soglia).sum()
        totale_segnali = segnali_long + segnali_short
        
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric("🔴 Segnali SHORT (QQQ)", segnali_short)
        with col_s2:
            st.metric("🟢 Segnali LONG (QQQ)", segnali_long)
        with col_s3:
            color = "normale" if totale_segnali <= 10 else "troppi segnali ⚠️"
            st.metric("Totale Segnali", totale_segnali, delta=color)

        # Giudizio automatico sulla soglia
        st.divider()
        if totale_segnali > 15:
            st.warning(f"⚠️ Soglia ±{soglia} troppo bassa: {totale_segnali} segnali in {len(data)} giorni. Prova ±2.5 o ±3.0")
        elif totale_segnali < 3:
            st.warning(f"⚠️ Soglia ±{soglia} troppo alta: solo {totale_segnali} segnali in {len(data)} giorni. Prova ±1.5")
        else:
            st.success(f"✅ Soglia ±{soglia} nella norma: {totale_segnali} segnali in {len(data)} giorni.")
        
        # ----------------------------------------
        # LOGICA DI CONTROLLO E ORDINI
        # ----------------------------------------
        ha_nasdaq = any(p.symbol == "QQQ" for p in posizioni)
        
        st.subheader("📝 Registro Operazioni (Log)")
        
        if ultimo_zscore > 2 and not ha_nasdaq:
            st.warning("Esecuzione: Segnale SHORT SPREAD. Invio ordini...")
            trading_client.submit_order(MarketOrderRequest(symbol="SPY", qty=10, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
            trading_client.submit_order(MarketOrderRequest(symbol="QQQ", qty=10, side=OrderSide.SELL, time_in_force=TimeInForce.DAY))
            st.success("Ordini inviati con successo!")
            
        elif ultimo_zscore < -2 and not ha_nasdaq:
            st.warning("Esecuzione: Segnale LONG SPREAD. Invio ordini...")
            trading_client.submit_order(MarketOrderRequest(symbol="QQQ", qty=10, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
            trading_client.submit_order(MarketOrderRequest(symbol="SPY", qty=10, side=OrderSide.SELL, time_in_force=TimeInForce.DAY))
            st.success("Ordini inviati con successo!")
            
        elif abs(ultimo_zscore) < 0.5 and ha_nasdaq:
            st.info("Esecuzione: Ritorno alla media. Chiusura posizioni...")
            trading_client.close_all_positions(cancel_orders=True)
            st.success("Tutte le posizioni sono state chiuse.")
        else:
            st.info("Nessuna azione richiesta. Le posizioni correnti sono allineate alla strategia.")
