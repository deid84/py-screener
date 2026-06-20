# CLAUDE.md — py-screener

Contesto per sessioni future. Leggere prima di fare qualsiasi modifica.

---

## Cos'è questo progetto

CLI + HTTP server per lo screening di opzioni su base stagionale.
Per ogni ticker analizza: stagionalità mensile storica, volatilità realizzata,
IV live dall'options chain, Greeks, skew, expected move, e suggerisce una
strategia options in base a bias direzionale + livello IV.

Utente finale: trader di opzioni (non developer), lavora principalmente con
opzioni mensili su ETF e single stock.

---

## Stack

- **Python 3.12+** (installato tramite python.org installer su Mac dev, immagine Docker su server)
- **yfinance** — unica sorgente dati (prezzi storici + options chain live)
- **pandas / numpy / scipy** — analisi
- **FastAPI + uvicorn** — HTTP server
- **SQLite** (`iv_archive.db`) — unico file di storage per tutto: IV snapshots, screening results, backtest results
- **Venv locale** in `venv/` (gitignored)

---

## File principali

| File | Ruolo |
|------|-------|
| `screener.py` | CLI principale. Scarica dati, analizza ogni ticker, stampa report o salva su DB (`--output db`) |
| `backtest.py` | Walk-forward backtest: price-only (default) o options-aware (`--strategy long-call` ecc.) |
| `seasonality.py` | Calcola stagionalità mensile + t-test di significatività (p-value per ogni mese) |
| `volatility.py` | HV rolling percentile + fetch IV snapshot live con Greeks (calcolati via BS) e skew |
| `options_analysis.py` | Expected move (IV × √DTE/365), strategy selector (matrice bias × IV level), Black-Scholes price + Greeks |
| `iv_archive.py` | Persiste snapshot IV giornalieri su SQLite. Calcola IV Rank e IV Percentile dopo 30+ osservazioni |
| `db.py` | Layer DB per screening_results e backtest_results. Encoder JSON custom per pandas/numpy |
| `server.py` | FastAPI: `/api/results`, `/api/iv-history/{ticker}`, `/api/backtest/{ticker}`. Serve `static/` |
| `static/index.html` | Frontend single-page: ranking table sortable, detail panel, grafico IV history (Chart.js) |

---

## Decisioni architetturali chiave

**Nessun lookahead bias nel backtest**
Per ogni mese M, stagionalità e HV vengono calcolati esclusivamente su dati
precedenti a M. Implementato filtrando `price_df[price_df.index < cutoff]`.

**HV come proxy IV nel backtest**
yfinance non fornisce storia IV. Il backtest options-aware usa la 20-day HV
come sigma per il pricing Black-Scholes. È un'approssimazione — i risultati
sono direzionalmente corretti ma non quantitativamente precisi.
La `iv_archive` accumula IV reale nel tempo (richiede run quotidiani).

**SQLite come unico storage**
Tutto in `iv_archive.db`: IV snapshots (tabella originale in `iv_archive.py`),
più `screening_results` e `backtest_results` gestite da `db.py`.
Path configurabile via env var `IV_ARCHIVE_DB` (letto da `server.py`;
da aggiungere ancora a `screener.py` e `backtest.py` come fallback a `--iv-archive`).

**Strategy selector (matrice 3×3)**
In `options_analysis.py`: bias (bullish/bearish/neutral) × IV level (low/normal/high)
→ strategia suggerita con rationale e structure hint.
IV level usa IV Rank se disponibile (≥30 obs in archive), altrimenti HV percentile.

---

## Deployment target

**Docker** — l'utente ha già un docker-compose con altri servizi su un server Linux.
Il progetto va aggiunto a quel compose come due servizi:
- `py-screener` → `uvicorn server:app`
- `py-screener-cron` → stessa immagine, esegue `screener.py --output db` su schedule

Volume named condiviso per `iv_archive.db`. Reverse proxy già presente nel compose
esistente (da confermare se Traefik o nginx).

**Cosa manca ancora per Docker:**
1. `IV_ARCHIVE_DB` env var come fallback in `screener.py` e `backtest.py`
2. `Dockerfile`
3. `.dockerignore`
4. Crontab da includere nell'immagine

---

## Come girare in sviluppo

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Screener (stdout)
python screener.py --tickers GLD,XRT --years 5

# Screener (salva su DB)
python screener.py --tickers GLD,XRT --years 5 --output db

# Backtest price-only
python backtest.py --tickers GLD --years 10

# Backtest options
python backtest.py --tickers GLD --years 10 --strategy long-call

# Server
uvicorn server:app --host 0.0.0.0 --port 8000
# → http://localhost:8000
```

---

## Prossimi step discussi (non ancora implementati)

**Breve termine (pronti da fare):**
- `Dockerfile` + `.dockerignore` + crontab per deploy su compose esistente
- `IV_ARCHIVE_DB` env var in `screener.py` / `backtest.py`
- Earnings filter: `yfinance Ticker.calendar` per flaggare earnings dentro il DTE
- Multiple testing correction sui p-value (Bonferroni o Benjamini-Hochberg)
- Filtro liquidità: escludere opzioni con bid-ask spread > N% del mid

**Medio termine:**
- Backtest results visibili nel frontend (il DB li ha già, il frontend non li mostra)
- Mid-month exit nel backtest opzioni (stop 200% / take profit 50%)
- Spread backtest (debit/credit spread, non solo single-leg)

**Limitazioni note da non dimenticare:**
- Multiple testing: 12 t-test simultanei → ~0.6 falsi positivi attesi con α=0.05
- HV ≠ IV: backtest opzioni sottostima il premio in regimi ad alta IV
- No transaction costs modellati
- ATM strike = spot (no strike discreti reali)
