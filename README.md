# 🏗️ Normattiva Search

App di ricerca normativa assistita per la Pubblica Amministrazione.

Inserisci un'esigenza amministrativa in linguaggio naturale (es. *"determina di acquisto software per un Comune sotto soglia"*) e l'app trova automaticamente le norme di riferimento da [Normattiva](https://www.normattiva.it), con ranking AI e motivazione per ogni risultato.

## Stack

| Layer | Tecnologia |
|---|---|
| **Frontend** | HTML / CSS / Vanilla JS |
| **Backend** | Python serverless (Vercel Functions) |
| **AI ranking** | [Groq](https://console.groq.com) — Llama 3.3 70B (free tier) |
| **Fonte dati** | [Normattiva](https://www.normattiva.it) + [dati.normattiva.it](https://dati.normattiva.it) |
| **Hosting** | [Vercel Hobby](https://vercel.com) (gratuito) |

## Come funziona

1. Il motore **tag-based** esegue un pre-filtro sulle norme candidate in base a tipo atto, importo e parole chiave semantiche
2. Il modello **Llama 3.3 70B via Groq** riordina i candidati e aggiunge una motivazione specifica per l'atto in esame
3. Se `GROQ_API_KEY` non è impostata, l'app continua a funzionare usando solo il motore tag (fallback silenzioso)

## Struttura

```
normattiva/
├── public/
│   └── index.html         # Interfaccia utente
├── api/
│   ├── search.py          # Endpoint ricerca + ranking Groq
│   └── utils/
├── vercel.json            # Configurazione Vercel
├── requirements.txt       # Nessuna dipendenza esterna (solo stdlib Python)
└── README.md
```

## Come si usa

1. Seleziona il tipo di atto amministrativo
2. Descrivi l'esigenza in linguaggio naturale
3. Inserisci eventuali dettagli (importo, ente, oggetto)
4. Clicca **Cerca norme** → ottieni l'elenco delle norme rilevanti con link diretti a Normattiva e motivazione AI

## Deploy su Vercel

```bash
# 1. Clona il repo
git clone https://github.com/enricobrunazzo/normattiva.git
cd normattiva

# 2. Installa Vercel CLI
npm i -g vercel

# 3. Deploy
vercel
```

Dopo il deploy, imposta la variabile d'ambiente nel pannello Vercel:

```
GROQ_API_KEY=<la tua chiave da console.groq.com>
```

> **Groq free tier**: 14.400 richieste/giorno, nessuna carta di credito richiesta.
> Registrati su [console.groq.com](https://console.groq.com) e genera una API key gratuita.

## Sviluppo locale

```bash
# Nessuna dipendenza Python da installare (requirements.txt vuoto)

# Imposta la variabile locale
export GROQ_API_KEY=<la tua chiave>

# Avvia Vercel in locale
vercel dev
```

## Roadmap

- [x] Struttura base progetto
- [x] Frontend form input esigenza
- [x] Motore tag-based con mappa semantica
- [x] Ranking AI con Groq / Llama 3.3 70B (free tier)
- [x] Motivazione AI per ogni norma suggerita
- [x] Soglie D.Lgs. 36/2023 (affidamento diretto / negoziata / aperta)
- [ ] Scheda dettaglio norma con testo degli articoli
- [ ] Integrazione dati.normattiva.it open data API
- [ ] Storico ricerche
- [ ] Export PDF/Word delle norme trovate

## Licenza

I dati normativi provengono da Normattiva — disponibili con licenza [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) dal 1° gennaio 2026.
