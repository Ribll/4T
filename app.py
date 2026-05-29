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
        nasdaq = yf.download("^NDX", period="100d", progress=False, auto_adjust=True)
        sp500 = yf.download("^GSPC", period="100d", progress=False, auto_adjust=True)

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
            st.warning(f"⚠️ Soglia ±{soglia} troppo bassa: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni. Prova ad alzare la soglia.")
        elif segnali_per_100_giorni < 1:
            st.warning(f"⚠️ Soglia ±{soglia} troppo alta: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni. Prova ad abbassare la soglia.")
        else:
            st.success(f"✅ Soglia ±{soglia} nella norma: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni.")

        # ----------------------------------------
        # BACKTEST SENZA LIMITE DI TEMPO
        # ----------------------------------------
        st.subheader("🧪 Backtest Storico")
        st.caption("Per ogni segnale passato, misura il tempo reale impiegato dallo z-score a tornare in zona neutra, senza limiti artificiali.")

        zscore_values = data["zscore"].values
        date_index = data.index
        soglia_uscita = 0.5

        risultati = []
        i = 0
        while i < len(zscore_values):
            z = zscore_values[i]

            # Rilevazione segnale
            if z > soglia:
                tipo = "SHORT (vendi QQQ)"
            elif z < -soglia:
                tipo = "LONG (compra QQQ)"
            else:
                i += 1
                continue

            # Cerca uscita senza limite di tempo
            uscita_trovata = False
            giorni_impiegati = None
            for j in range(1, len(zscore_values) - i):
                if abs(zscore_values[i + j]) < soglia_uscita:
                    uscita_trovata = True
                    giorni_impiegati = j
                    break

            risultati.append({
                "Data segnale": date_index[i].strftime("%Y-%m-%d"),
                "Tipo": tipo,
                "Z-Score ingresso": round(z, 2),
                "Esito": "✅ Tornato" if uscita_trovata else "⏳ Non ancora tornato",
                "Giorni al ritorno": giorni_impiegati if uscita_trovata else "ancora aperto"
            })

            # Salta al giorno dopo l'uscita per evitare duplicati
            i += giorni_impiegati if uscita_trovata else len(zscore_values) - i

        # ----------------------------------------
        # RIEPILOGO BACKTEST
        # ----------------------------------------
        if risultati:
            df_risultati = pd.DataFrame(risultati)

            tornati = (df_risultati["Esito"] == "✅ Tornato").sum()
            ancora_aperti = (df_risultati["Esito"] == "⏳ Non ancora tornato").sum()
            totale_trade = len(df_risultati)

            # Durata media calcolata dai dati reali
            durate_reali = df_risultati[df_risultati["Esito"] == "✅ Tornato"]["Giorni al ritorno"]
            durata_media = durate_reali.mean() if len(durate_reali) > 0 else 0
            durata_mediana = durate_reali.median() if len(durate_reali) > 0 else 0
            durata_massima = durate_reali.max() if len(durate_reali) > 0 else 0

            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            with col_b1:
                st.metric("Trade Totali", totale_trade)
            with col_b2:
                st.metric("✅ Tornati in zona neutra", tornati)
            with col_b3:
                st.metric("⏳ Ancora aperti", ancora_aperti)
            with col_b4:
                tasso = (tornati / totale_trade * 100) if totale_trade > 0 else 0
                st.metric("% Risolti", f"{tasso:.1f}%")

            st.divider()

            # Le tre metriche temporali chiave
            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                st.metric(
                    "⏱️ Durata Media",
                    f"{durata_media:.1f} giorni",
                    help="Media aritmetica dei giorni di ritorno. Sensibile ai casi estremi."
                )
            with col_t2:
                st.metric(
                    "⏱️ Durata Mediana",
                    f"{durata_mediana:.1f} giorni",
                    help="Il valore centrale: metà dei trade si chiude prima, metà dopo. Più robusta della media."
                )
            with col_t3:
                st.metric(
                    "⏱️ Caso Peggiore",
                    f"{durata_massima:.0f} giorni",
                    help="Il trade più lento mai visto storicamente. Utile per sapere il rischio massimo di attesa."
                )

            # Spiegazione delle metriche
            st.info(
                f"📖 **Come leggere questi numeri:** "
                f"Storicamente, metà dei segnali si è risolta entro **{durata_mediana:.0f} giorni**. "
                f"In media ci sono voluti **{durata_media:.1f} giorni**. "
                f"Il caso più lento nella storia analizzata ha impiegato **{durata_massima:.0f} giorni**. "
                f"Questi numeri emergono dai dati reali, non da parametri arbitrari."
            )

            # Giudizio sulla strategia
            st.divider()
            if tasso >= 90:
                st.success(f"✅ Lo z-score è tornato in zona neutra nel {tasso:.1f}% dei casi storici. Strategia molto affidabile.")
            elif tasso >= 70:
                st.warning(f"⚠️ Lo z-score è tornato in zona neutra nel {tasso:.1f}% dei casi. Strategia discreta, ma con margine di rischio.")
            else:
                st.error(f"🔴 Lo z-score è tornato in zona neutra solo nel {tasso:.1f}% dei casi. Valuta di cambiare soglia o approccio.")

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
