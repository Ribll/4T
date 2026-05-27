import streamlit as st
import yfinance as yf
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Configurazione della pagina Streamlit (Stile Dashboard)
st.set_page_config(page_title="Trading Desk - Pair Trading", layout="wide")
st.title("📊 Trading Desk - Sistema Automatico Z-Score")

# Recuperiamo le chiavi in modo sicuro dai segreti del Cloud
try:
    API_KEY = st.secrets["PKDGFYR2QIQW2767NNVOVONLFG"]
    SECRET_KEY = st.secrets["HCGTNyH78ZVvHW19YPuwT1VHZcnsDmcgfP6UFHHQp6fa"]
except:
    st.error("⚠️ Chiavi API non configurate nei Secrets di Streamlit!")
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
        nasdaq = yf.download("^NDX", period="100d", progress=False, auto_adjust=True)
        sp500 = yf.download("^GSPC", period="100d", progress=False, auto_adjust=True)

        data = pd.DataFrame({
            "nasdaq": nasdaq["Close"].iloc[:, 0] if isinstance(nasdaq["Close"], pd.DataFrame) else nasdaq["Close"],
            "sp500": sp500["Close"].iloc[:, 0] if isinstance(sp500["Close"], pd.DataFrame) else sp500["Close"]
        }).dropna()

        # Calcoli
        data["nasdaq_norm"] = data["nasdaq"] / data["nasdaq"].iloc[0]
        data["sp500_norm"] = data["sp500"] / data["sp500"].iloc[0]
        data["spread"] = data["nasdaq_norm"] - data["sp500_norm"]

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
