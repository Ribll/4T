import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# =========================================================
# CONFIGURAZIONE PAGINA
# =========================================================
st.set_page_config(page_title="Trading Desk - Pair Trading", layout="wide")
st.title("📊 Trading Desk - Sistema Automatico Z-Score")

# =========================================================
# RECUPERO CHIAVI API
# =========================================================
API_KEY = None
SECRET_KEY = None

if "ALPACA_API_KEY" in st.secrets:
    API_KEY = st.secrets["ALPACA_API_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET_KEY"]
elif hasattr(st.secrets, "secrets") and "ALPACA_API_KEY" in st.secrets.secrets:
    API_KEY = st.secrets.secrets["ALPACA_API_KEY"]
    SECRET_KEY = st.secrets.secrets["ALPACA_SECRET_KEY"]

if not API_KEY or not SECRET_KEY:
    st.error("⚠️ Chiavi API non trovate nei Secrets!")
    st.write("Chiavi rilevate attualmente nel pannello Streamlit:", list(st.secrets.keys()))
    st.stop()

# =========================================================
# CONNESSIONE ALPACA
# =========================================================
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# =========================================================
# LAYOUT: DUE COLONNE
# =========================================================
col1, col2 = st.columns([1, 2])

# ==========================================
# COLONNA SINISTRA: STATO DEL CONTO
# ==========================================
with col1:
    st.header("💰 Stato Portafoglio")
    try:
        account = trading_client.get_account()
        st.metric(label="Saldo Totale (Paper)", value=f"${float(account.equity):,.2f}")
        st.metric(label="Potere d'Acquisto", value=f"${float(account.buying_power):,.2f}")

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
# COLONNA DESTRA: ANALISI E SEGNALI
# ==========================================
with col2:
    st.header("📈 Analisi di Mercato Real-Time")

    # SLIDER SOGLIA - sempre visibile, fuori dal pulsante
    soglia = st.slider(
        "Soglia Z-Score per i segnali",
        min_value=1.0,
        max_value=4.0,
        value=2.0,
        step=0.1,
        help="Sposta il cursore per cambiare la soglia. Valori consigliati: tra 1.5 e 3.0"
    )

    if st.button("🔄 Aggiorna e Controlla Segnali Ora"):
        st.write("Scaricamento dati in corso...")

        # ----------------------------------------
        # SCARICO DATI
        # ----------------------------------------
        nasdaq = yf.download("^NDX", period="2000d", progress=False, auto_adjust=True)
        sp500 = yf.download("^GSPC", period="2000d", progress=False, auto_adjust=True)

        data = pd.DataFrame({
            "nasdaq": nasdaq["Close"].iloc[:, 0] if isinstance(nasdaq["Close"], pd.DataFrame) else nasdaq["Close"],
            "sp500": sp500["Close"].iloc[:, 0] if isinstance(sp500["Close"], pd.DataFrame) else sp500["Close"]
        }).dropna()

        # ----------------------------------------
        # CALCOLO RENDIMENTI E SPREAD
        # ----------------------------------------
        data["nasdaq_ret"] = data["nasdaq"].pct_change()
        data["sp500_ret"] = data["sp500"].pct_change()
        data["spread"] = data["nasdaq_ret"] - data["sp500_ret"]
        data = data.dropna()

        # ----------------------------------------
        # CALCOLO Z-SCORE
        # ----------------------------------------
        window = 60
        data["mean"] = data["spread"].rolling(window).mean()
        data["std"] = data["spread"].rolling(window).std()
        data["zscore"] = (data["spread"] - data["mean"]) / data["std"]
        ultimo_zscore = data["zscore"].iloc[-1]

        # ----------------------------------------
        # Z-SCORE ATTUALE
        # ----------------------------------------
        if abs(ultimo_zscore) > soglia:
            st.error(f"🔴 Z-SCORE ATTUALE: {ultimo_zscore:.2f} (Soglia superata!)")
        else:
            st.success(f"🟢 Z-SCORE ATTUALE: {ultimo_zscore:.2f} (In zona neutra)")

        st.line_chart(data["zscore"])

        # ----------------------------------------
        # PANNELLO DIAGNOSTICA
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

        # Conteggio segnali storici con frequenza proporzionale
        giorni_analizzati = len(data)
        segnali_long = (data["zscore"] < -soglia).sum()
        segnali_short = (data["zscore"] > soglia).sum()
        totale_segnali = segnali_long + segnali_short
        segnali_per_100_giorni = (totale_segnali / giorni_analizzati) * 100

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric("🔴 Segnali SHORT (QQQ)", segnali_short)
        with col_s2:
            st.metric("🟢 Segnali LONG (QQQ)", segnali_long)
        with col_s3:
            st.metric("📊 Frequenza", f"{segnali_per_100_giorni:.1f} ogni 100gg")

        st.divider()
        st.caption(f"Periodo analizzato: {giorni_analizzati} giorni | Segnali totali: {totale_segnali} | Frequenza: {segnali_per_100_giorni:.1f} ogni 100 giorni")

        if segnali_per_100_giorni > 8:
            st.warning(f"⚠️ Soglia ±{soglia} troppo bassa: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni. Il sistema scatta troppo spesso. Prova ad alzare la soglia.")
        elif segnali_per_100_giorni < 1:
            st.warning(f"⚠️ Soglia ±{soglia} troppo alta: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni. Il sistema non scatta quasi mai. Prova ad abbassare la soglia.")
        else:
            st.success(f"✅ Soglia ±{soglia} nella norma: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni. Frequenza ragionevole.")

        # ----------------------------------------
        # BACKTEST
        # ----------------------------------------
        st.subheader("🧪 Backtest Storico")
        st.caption("Per ogni segnale passato, verifica se lo z-score è tornato in zona neutra entro 30 giorni.")

        zscore_values = data["zscore"].values
        date_index = data.index
        max_giorni_attesa = 30
        soglia_uscita = 0.5

        risultati = []
        i = 0
        while i < len(zscore_values) - max_giorni_attesa:
            z = zscore_values[i]

            # Rilevazione segnale
            if z > soglia:
                tipo = "SHORT (vendi QQQ)"
            elif z < -soglia:
                tipo = "LONG (compra QQQ)"
            else:
                i += 1
                continue

            # Cerca uscita nei 30 giorni successivi
            uscita_trovata = False
            giorni_impiegati = None
            for j in range(1, max_giorni_attesa + 1):
                if abs(zscore_values[i + j]) < soglia_uscita:
                    uscita_trovata = True
                    giorni_impiegati = j
                    break

            risultati.append({
                "Data segnale": date_index[i].strftime("%Y-%m-%d"),
                "Tipo": tipo,
                "Z-Score ingresso": round(z, 2),
                "Esito": "✅ Vincente" if uscita_trovata else "❌ Perdente",
                "Giorni al ritorno": giorni_impiegati if uscita_trovata else f">{max_giorni_attesa}"
            })

            # Salta i giorni successivi per evitare di contare lo stesso trade più volte
            i += giorni_impiegati if uscita_trovata else max_giorni_attesa

        # ----------------------------------------
        # RIEPILOGO BACKTEST
        # ----------------------------------------
        if risultati:
            df_risultati = pd.DataFrame(risultati)

            vincenti = (df_risultati["Esito"] == "✅ Vincente").sum()
            perdenti = (df_risultati["Esito"] == "❌ Perdente").sum()
            totale = len(df_risultati)
            tasso_successo = (vincenti / totale) * 100

            durate_vincenti = df_risultati[df_risultati["Esito"] == "✅ Vincente"]["Giorni al ritorno"]
            durata_media = durate_vincenti.mean() if len(durate_vincenti) > 0 else 0

            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            with col_b1:
                st.metric("Trade Totali", totale)
            with col_b2:
                st.metric("✅ Vincenti", vincenti)
            with col_b3:
                st.metric("❌ Perdenti", perdenti)
            with col_b4:
                st.metric("🎯 Tasso Successo", f"{tasso_successo:.1f}%")

            st.metric("⏱️ Durata Media Trade Vincente", f"{durata_media:.1f} giorni")

            # Giudizio sul tasso di successo
            st.divider()
            if tasso_successo >= 60:
                st.success(f"✅ Strategia storicamente solida: {tasso_successo:.1f}% dei trade ha raggiunto il target entro {max_giorni_attesa} giorni.")
            elif tasso_successo >= 45:
                st.warning(f"⚠️ Strategia nella media: {tasso_successo:.1f}% di successo. Considera di alzare la soglia per segnali più selettivi.")
            else:
                st.error(f"🔴 Strategia debole: solo {tasso_successo:.1f}% di successo. La soglia attuale genera troppi falsi segnali.")

            # Tabella dettaglio trade
            with st.expander("📋 Dettaglio tutti i trade storici"):
                st.dataframe(df_risultati, use_container_width=True)
        else:
            st.info("Nessun segnale trovato nel periodo analizzato con la soglia attuale.")

        # ----------------------------------------
        # LOGICA ORDINI
        # ----------------------------------------
        ha_nasdaq = any(p.symbol == "QQQ" for p in posizioni)

        st.subheader("📝 Registro Operazioni (Log)")

        if ultimo_zscore > soglia and not ha_nasdaq:
            st.warning("Esecuzione: Segnale SHORT SPREAD. Invio ordini...")
            trading_client.submit_order(MarketOrderRequest(symbol="SPY", qty=10, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
            trading_client.submit_order(MarketOrderRequest(symbol="QQQ", qty=10, side=OrderSide.SELL, time_in_force=TimeInForce.DAY))
            st.success("Ordini inviati con successo!")

        elif ultimo_zscore < -soglia and not ha_nasdaq:
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
