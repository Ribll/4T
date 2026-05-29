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
        # SCARICO DATI — sempre 2000 giorni per
        # avere analisi e backtest affidabili
        # ----------------------------------------
        qqq_raw = yf.download("QQQ", period="2000d", progress=False, auto_adjust=True)
        spy_raw = yf.download("SPY", period="2000d", progress=False, auto_adjust=True)
        nasdaq_raw = yf.download("^NDX", period="2000d", progress=False, auto_adjust=True)
        sp500_raw = yf.download("^GSPC", period="2000d", progress=False, auto_adjust=True)

        # DataFrame indici per Z-Score
        data = pd.DataFrame({
            "nasdaq": nasdaq_raw["Close"].iloc[:, 0] if isinstance(nasdaq_raw["Close"], pd.DataFrame) else nasdaq_raw["Close"],
            "sp500": sp500_raw["Close"].iloc[:, 0] if isinstance(sp500_raw["Close"], pd.DataFrame) else sp500_raw["Close"]
        }).dropna()

        # DataFrame ETF per backtest economico
        data_etf = pd.DataFrame({
            "qqq": qqq_raw["Close"].iloc[:, 0] if isinstance(qqq_raw["Close"], pd.DataFrame) else qqq_raw["Close"],
            "spy": spy_raw["Close"].iloc[:, 0] if isinstance(spy_raw["Close"], pd.DataFrame) else spy_raw["Close"]
        }).dropna()

        # ----------------------------------------
        # CALCOLO Z-SCORE SU TUTTI I 2000 GIORNI
        # ----------------------------------------
        data["nasdaq_ret"] = data["nasdaq"].pct_change()
        data["sp500_ret"] = data["sp500"].pct_change()
        data["spread"] = data["nasdaq_ret"] - data["sp500_ret"]
        data = data.dropna()

        window = 60
        data["mean"] = data["spread"].rolling(window).mean()
        data["std"] = data["spread"].rolling(window).std()
        data["zscore"] = (data["spread"] - data["mean"]) / data["std"]
        data = data.dropna()

        ultimo_zscore = data["zscore"].iloc[-1]

        # ----------------------------------------
        # Z-SCORE ATTUALE
        # ----------------------------------------
        if abs(ultimo_zscore) > soglia:
            st.error(f"🔴 Z-SCORE ATTUALE: {ultimo_zscore:.2f} (Soglia superata!)")
        else:
            st.success(f"🟢 Z-SCORE ATTUALE: {ultimo_zscore:.2f} (In zona neutra)")

        # Grafico Z-Score ultimi 100 giorni
        st.line_chart(data["zscore"].iloc[-100:])

        # ----------------------------------------
        # CRUSCOTTO GRAFICO INDICI SOVRAPPOSTI
        # Fisso a 100 giorni, senza slider
        # ----------------------------------------
        st.subheader("📉 Confronto Indici — NASDAQ vs S&P500 (ultimi 100 giorni)")

        GIORNI_GRAFICO = 100
        data_grafico = data[["nasdaq", "sp500"]].iloc[-GIORNI_GRAFICO:].copy()

        # Normalizza a 100 nel primo giorno del periodo
        data_grafico["NASDAQ (norm)"] = (data_grafico["nasdaq"] / data_grafico["nasdaq"].iloc[0]) * 100
        data_grafico["S&P500 (norm)"] = (data_grafico["sp500"] / data_grafico["sp500"].iloc[0]) * 100

        st.line_chart(data_grafico[["NASDAQ (norm)", "S&P500 (norm)"]])
        st.caption(
            f"Entrambi gli indici normalizzati a 100 il {data_grafico.index[0].strftime('%d/%m/%Y')}. "
            f"Quando la linea NASDAQ è sopra S&P500 lo spread è positivo (Z-Score tende al rialzo); "
            f"quando è sotto è negativo (Z-Score tende al ribasso)."
        )

        # Mini-metriche del periodo
        perf_nasdaq = ((data_grafico["nasdaq"].iloc[-1] / data_grafico["nasdaq"].iloc[0]) - 1) * 100
        perf_sp500 = ((data_grafico["sp500"].iloc[-1] / data_grafico["sp500"].iloc[0]) - 1) * 100
        differenza = perf_nasdaq - perf_sp500

        col_g1, col_g2, col_g3 = st.columns(3)
        with col_g1:
            st.metric("NASDAQ ultimi 100gg", f"{perf_nasdaq:+.2f}%")
        with col_g2:
            st.metric("S&P500 ultimi 100gg", f"{perf_sp500:+.2f}%")
        with col_g3:
            st.metric(
                "Differenza di performance",
                f"{differenza:+.2f}%",
                delta="NASDAQ sovraperforma" if differenza > 0 else "S&P500 sovraperforma"
            )

        # ----------------------------------------
        # PANNELLO DIAGNOSTICA Z-SCORE
        # Calcolato su tutti i 2000 giorni
        # ----------------------------------------
        st.subheader("🔬 Diagnostica Z-Score")

        col_d1, col_d2, col_d3, col_d4 = st.columns(4)
        with col_d1:
            st.metric("Z-Score Attuale", f"{ultimo_zscore:.2f}")
        with col_d2:
            st.metric("Massimo (2000gg)", f"{data['zscore'].max():.2f}")
        with col_d3:
            st.metric("Minimo (2000gg)", f"{data['zscore'].min():.2f}")
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

        # Giudizio affidabile perché sempre su 2000 giorni
        if segnali_per_100_giorni > 8:
            st.warning(f"⚠️ Soglia ±{soglia} troppo bassa: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni. Prova ad alzare la soglia.")
        elif segnali_per_100_giorni < 1:
            st.warning(f"⚠️ Soglia ±{soglia} troppo alta: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni. Prova ad abbassare la soglia.")
        else:
            st.success(f"✅ Soglia ±{soglia} nella norma: {segnali_per_100_giorni:.1f} segnali ogni 100 giorni.")

        # ----------------------------------------
        # BACKTEST QUALITATIVO (ritorno alla media)
        # Su tutti i 2000 giorni
        # ----------------------------------------
        st.subheader("🧪 Backtest Storico - Ritorno alla Media")
        st.caption("Per ogni segnale passato, misura il tempo reale impiegato dallo z-score a tornare in zona neutra.")

        zscore_values = data["zscore"].values
        date_index = data.index
        soglia_uscita = 0.5

        risultati = []
        i = 0
        while i < len(zscore_values):
            z = zscore_values[i]
            if z > soglia:
                tipo = "SHORT (vendi QQQ)"
            elif z < -soglia:
                tipo = "LONG (compra QQQ)"
            else:
                i += 1
                continue

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

            i += giorni_impiegati if uscita_trovata else len(zscore_values) - i

        if risultati:
            df_qual = pd.DataFrame(risultati)
            tornati = (df_qual["Esito"] == "✅ Tornato").sum()
            totale_q = len(df_qual)
            durate_reali = df_qual[df_qual["Esito"] == "✅ Tornato"]["Giorni al ritorno"]
            durata_media = durate_reali.mean() if len(durate_reali) > 0 else 0
            durata_mediana = durate_reali.median() if len(durate_reali) > 0 else 0
            durata_massima = durate_reali.max() if len(durate_reali) > 0 else 0

            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                st.metric("⏱️ Durata Media", f"{durata_media:.1f} giorni")
            with col_t2:
                st.metric("⏱️ Durata Mediana", f"{durata_mediana:.1f} giorni")
            with col_t3:
                st.metric("⏱️ Caso Peggiore", f"{durata_massima:.0f} giorni")

            st.info(f"📖 Storicamente, metà dei segnali si è risolta entro **{durata_mediana:.0f} giorni**. Media: **{durata_media:.1f} giorni**. Caso più lento: **{durata_massima:.0f} giorni**.")

            with st.expander("📋 Dettaglio tutti i trade storici"):
                st.dataframe(df_qual, use_container_width=True)

        # ----------------------------------------
        # BACKTEST ECONOMICO - ULTIMI 6 MESI
        # ----------------------------------------
        st.subheader("💰 Backtest Economico — Ultimi 6 Mesi")
        st.caption("Simula ogni trade con prezzi reali QQQ e SPY. Costo simulato: $1 per ordine ($4 totali per trade completo).")

       # NUOVO - realistico per Alpaca con ETF liquidi
QTY = 10
SPREAD_PER_AZIONE = 0.01   # $0.01 di spread bid-ask per azione, tipico per QQQ e SPY
COSTO_ORDINE = SPREAD_PER_AZIONE * QTY  # = $0.10 per ordine

        data_merged = data[["zscore"]].join(data_etf, how="inner").dropna()
        data_6m = data_merged.iloc[-126:].copy()

        zscore_eco = data_6m["zscore"].values
        qqq_prices = data_6m["qqq"].values
        spy_prices = data_6m["spy"].values
        date_eco = data_6m.index

        trades = []
        i = 0
        in_posizione = False
        trade_aperto = {}

        while i < len(zscore_eco):
            z = zscore_eco[i]

            if not in_posizione:
                if z > soglia:
                    trade_aperto = {
                        "data_ingresso": date_eco[i].strftime("%Y-%m-%d"),
                        "tipo": "SHORT SPREAD",
                        "zscore_ing": round(z, 2),
                        "qqq_ing": qqq_prices[i],
                        "spy_ing": spy_prices[i],
                        "dir_qqq": "SELL",
                        "idx": i
                    }
                    in_posizione = True
                elif z < -soglia:
                    trade_aperto = {
                        "data_ingresso": date_eco[i].strftime("%Y-%m-%d"),
                        "tipo": "LONG SPREAD",
                        "zscore_ing": round(z, 2),
                        "qqq_ing": qqq_prices[i],
                        "spy_ing": spy_prices[i],
                        "dir_qqq": "BUY",
                        "idx": i
                    }
                    in_posizione = True
            else:
                if abs(z) < SOGLIA_USCITA_ECO:
                    if trade_aperto["dir_qqq"] == "SELL":
                        pnl_qqq = (trade_aperto["qqq_ing"] - qqq_prices[i]) * QTY
                        pnl_spy = (spy_prices[i] - trade_aperto["spy_ing"]) * QTY
                    else:
                        pnl_qqq = (qqq_prices[i] - trade_aperto["qqq_ing"]) * QTY
                        pnl_spy = (trade_aperto["spy_ing"] - spy_prices[i]) * QTY

                    costi = COSTO_ORDINE * 4  # 4 ordini per trade completo = $0.40
                    pnl_tot = pnl_qqq + pnl_spy - costi
                    giorni = i - trade_aperto["idx"]

                    trades.append({
                        "Data ingresso": trade_aperto["data_ingresso"],
                        "Data uscita": date_eco[i].strftime("%Y-%m-%d"),
                        "Tipo": trade_aperto["tipo"],
                        "Z entrata": trade_aperto["zscore_ing"],
                        "Z uscita": round(z, 2),
                        "Giorni": giorni,
                        "P&L QQQ ($)": round(pnl_qqq, 2),
                        "P&L SPY ($)": round(pnl_spy, 2),
                        "Costi ($)": round(-costi, 2),
                        "P&L Totale ($)": round(pnl_tot, 2),
                        "Esito": "✅ Profitto" if pnl_tot > 0 else "❌ Perdita"
                    })
                    in_posizione = False
                    trade_aperto = {}

            i += 1

        if in_posizione:
            if trade_aperto["dir_qqq"] == "SELL":
                pnl_qqq = (trade_aperto["qqq_ing"] - qqq_prices[-1]) * QTY
                pnl_spy = (spy_prices[-1] - trade_aperto["spy_ing"]) * QTY
            else:
                pnl_qqq = (qqq_prices[-1] - trade_aperto["qqq_ing"]) * QTY
                pnl_spy = (trade_aperto["spy_ing"] - spy_prices[-1]) * QTY

            costi = COSTO_ORDINE * 2  # solo apertura = $0.20
            pnl_tot = pnl_qqq + pnl_spy - costi
            giorni = len(zscore_eco) - 1 - trade_aperto["idx"]

            trades.append({
                "Data ingresso": trade_aperto["data_ingresso"],
                "Data uscita": f"{date_eco[-1].strftime('%Y-%m-%d')} ⏳ aperto",
                "Tipo": trade_aperto["tipo"],
                "Z entrata": trade_aperto["zscore_ing"],
                "Z uscita": round(zscore_eco[-1], 2),
                "Giorni": giorni,
                "P&L QQQ ($)": round(pnl_qqq, 2),
                "P&L SPY ($)": round(pnl_spy, 2),
                "Costi ($)": round(-costi, 2),
                "P&L Totale ($)": round(pnl_tot, 2),
                "Esito": "⏳ Ancora aperto"
            })

        if trades:
            df_eco = pd.DataFrame(trades)
            df_chiusi = df_eco[~df_eco["Esito"].str.contains("aperto")]

            pnl_totale = df_eco["P&L Totale ($)"].sum()
            vincenti = (df_chiusi["P&L Totale ($)"] > 0).sum()
            perdenti = (df_chiusi["P&L Totale ($)"] < 0).sum()
            totale_chiusi = len(df_chiusi)
            tasso_eco = (vincenti / totale_chiusi * 100) if totale_chiusi > 0 else 0
            durata_media_eco = df_chiusi["Giorni"].mean() if totale_chiusi > 0 else 0
            costi_totali = df_eco["Costi ($)"].sum()

            col_e1, col_e2, col_e3, col_e4 = st.columns(4)
            with col_e1:
                st.metric("💵 P&L Totale", f"${pnl_totale:+.2f}", delta="profitto" if pnl_totale >= 0 else "perdita")
            with col_e2:
                st.metric("🎯 Tasso Successo", f"{tasso_eco:.1f}%")
            with col_e3:
                st.metric("📅 Durata Media Trade", f"{durata_media_eco:.1f} giorni")
            with col_e4:
                st.metric("💸 Costi Totali", f"${costi_totali:.2f}")

            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                st.metric("Trade totali", len(df_eco))
            with col_f2:
                st.metric("✅ Profittevoli", vincenti)
            with col_f3:
                st.metric("❌ In perdita", perdenti)

            st.divider()

            if pnl_totale > 0 and tasso_eco >= 60:
                st.success(f"✅ Il bot avrebbe guadagnato **${pnl_totale:+.2f}** negli ultimi 6 mesi con un tasso di successo del {tasso_eco:.1f}%. Strategia solida su questo periodo.")
            elif pnl_totale > 0 and tasso_eco < 60:
                st.warning(f"⚠️ Il bot avrebbe guadagnato **${pnl_totale:+.2f}** ma con solo il {tasso_eco:.1f}% di trade vincenti. Il guadagno dipende da pochi trade molto profittevoli — strategia instabile.")
            elif pnl_totale <= 0 and tasso_eco >= 60:
                st.warning(f"⚠️ Il bot ha il {tasso_eco:.1f}% di trade vincenti ma il P&L totale è **${pnl_totale:+.2f}**. I trade perdenti pesano più di quelli vincenti.")
            else:
                st.error(f"🔴 Il bot avrebbe perso **${pnl_totale:+.2f}** negli ultimi 6 mesi con solo il {tasso_eco:.1f}% di successo. Valuta di cambiare soglia prima di andare in produzione.")

            df_eco_plot = df_eco.copy()
            df_eco_plot["P&L Cumulativo ($)"] = df_eco_plot["P&L Totale ($)"].cumsum()
            st.line_chart(df_eco_plot.set_index("Data ingresso")["P&L Cumulativo ($)"])
            st.caption("P&L cumulativo nel tempo. Una linea che sale = strategia profittevole nel periodo.")

            with st.expander("📋 Dettaglio ogni singolo trade con prezzi reali"):
                st.dataframe(df_eco, use_container_width=True)

        else:
            st.info("Nessun segnale rilevato negli ultimi 6 mesi con la soglia attuale. Prova ad abbassare la soglia.")

        # ----------------------------------------
        # LOGICA ORDINI LIVE
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
