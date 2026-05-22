# 🏛️ Normattiva Search

App di ricerca normativa assistita per la Pubblica Amministrazione.

Inserisci un'esigenza amministrativa in linguaggio naturale (es. *"determina di acquisto software per un Comune sotto soglia"*) e l'app trova le norme di riferimento da [Normattiva](https://www.normattiva.it).

## Stack

- **Frontend**: HTML / CSS / Vanilla JS
- **Backend**: Python serverless (Vercel Functions)
- **Fonte dati**: [Normattiva](https://www.normattiva.it) + [dati.normattiva.it](https://dati.normattiva.it)
- **Hosting**: [Vercel Hobby](https://vercel.com) (gratuito)

## Struttura

```
normattiva/
├── public/
│   └── index.html         # Interfaccia utente
├── api/
│   ├── search.py          # Endpoint ricerca normativa
│   └── utils/
│       ├── keywords.py    # Estrazione parole chiave
│       └── normattiva.py  # Client Normattiva
├── vercel.json            # Configurazione Vercel
├── requirements.txt       # Dipendenze Python
└── README.md
```

## Come si usa

1. Seleziona il tipo di atto amministrativo
2. Descrivi l'esigenza in linguaggio naturale
3. Inserisci eventuali dettagli (importo, ente, oggetto)
4. Clicca **Cerca norme** → ottieni l'elenco delle norme rilevanti con link diretti

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

## Sviluppo locale

```bash
# Installa dipendenze Python
pip install -r requirements.txt

# Avvia Vercel in locale
vercel dev
```

## Roadmap

- [x] Struttura base progetto
- [x] Frontend form input esigenza
- [x] API Python per ricerca Normattiva
- [ ] Ranking risultati per rilevanza
- [ ] Scheda dettaglio norma con articoli
- [ ] Integrazione dati.normattiva.it open data
- [ ] Storico ricerche
- [ ] Export PDF/Word delle norme trovate

## Licenza

I dati normativi provengono da Normattiva — disponibili con licenza [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) dal 1° gennaio 2026.
