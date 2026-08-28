# Allerte Italia — design

Data: 2026-08-29 · Stato: approvata

## Obiettivo

Un'integrazione Home Assistant che sorveglia quattro fonti italiane e avvisa
quando succede qualcosa che merita attenzione: il carburante che scende sotto la
soglia che ti sei dato, un terremoto vicino, un'allerta della Protezione Civile,
un'ondata di calore.

Le notifiche si configurano **dentro l'integrazione**, con soglie e servizio di
notifica scelti dall'utente: chi la installa non deve saper scrivere automazioni.

## Le fonti, verificate il 2026-08-28

| Provider | Fonte | Formato | Aggiornamento | Peso |
|---|---|---|---|---|
| Carburanti | `mimit.gov.it/images/exportCSV/` | CSV separato da `|` | 1×/giorno dopo le 8:30 | 7,5 MB |
| Terremoti | `webservices.ingv.it/fdsnws/event/1/query` | GeoJSON (FDSN) | 5 minuti | ~1 KB |
| Allerte | `github.com/pcm-dpc/DPC-Bollettini-*` | JSON + TopoJSON | 1 ora | pochi KB |
| Caldo | temperatura e umidità già note ad HA | — | 30 minuti | nessuno |

Due file MIMIT: `anagrafica_impianti_attivi.csv` (con latitudine e longitudine di
ogni impianto) e `prezzo_alle_8.csv` (`idImpianto|descCarburante|prezzo|isSelf|dtComu`).

L'INGV filtra **lato server** per `lat`, `lon`, `maxradiuskm`, `minmagnitude`:
nessuna libreria esterna, payload minimo.

Il Ministero della Salute pubblica le ondate di calore **solo in PDF**: scartato.
L'allerta caldo si calcola dall'indice di calore su dati che Home Assistant ha già.

## Architettura

Quattro provider isolati, un coordinatore ciascuno, ritmi indipendenti. Una fonte
che cambia formato o va giù non tocca le altre — la protezione necessaria quando
si dipende da quattro enti diversi.

I provider hanno un'interfaccia comune ma due nature:

- **Misure continue** (carburante, indice di calore) → numeri; la soglia è un
  confronto.
- **Eventi discreti** (terremoti, bollettini) → fatti datati; la soglia è un filtro.

```
custom_components/allerte_italia/
├── __init__.py              avvio, registrazione dei coordinatori
├── config_flow.py           configurazione e opzioni (soglie)
├── coordinator.py           coordinatore base
├── const.py
├── sources/
│   ├── base.py              interfaccia comune, tipi condivisi
│   ├── fuel.py              MIMIT, parsing in streaming
│   ├── quakes.py            INGV
│   ├── civil_protection.py  bollettini DPC
│   └── heat.py              indice di calore
├── geo.py                   distanza haversine (puro)
├── thresholds.py            valutazione soglie e antirumore (puro)
├── sensor.py
├── binary_sensor.py
└── notifications.py         invio tramite il servizio notify scelto
```

La logica pura (`geo`, `thresholds`, parsing, indice di calore) non importa
`homeassistant`: si testa senza far girare Home Assistant.

## Il vincolo dei 7,5 MB

Home Assistant gira spesso su Raspberry, quindi i CSV MIMIT non vanno mai tenuti
interi in memoria.

- L'**anagrafica** si scarica al primo avvio e poi settimanalmente, si legge
  **riga per riga** e si scarta subito ogni impianto fuori dal raggio: di ~25.000
  impianti ne restano qualche decina, e solo quelli vengono conservati.
- I **prezzi** si scaricano una volta al giorno e si processano allo stesso modo,
  scartando al volo le righe con `idImpianto` non selezionato.

## Entità

**Carburanti** — un sensore per impianto e tipo di carburante selezionato, con
stato uguale al prezzo in €/litro e attributi: nome impianto, bandiera, indirizzo,
comune, distanza, self o servito, ora di comunicazione. Più un sensore
riepilogativo col prezzo più basso fra quelli sorvegliati.

**Terremoti** — un sensore con la magnitudo dell'ultimo evento rilevante e
attributi: luogo, profondità, distanza, ora. Più un `binary_sensor` acceso quando
esiste un evento sopra soglia nelle ultime N ore.

**Allerte Protezione Civile** — un sensore per la zona configurata con il livello
corrente (`verde`, `giallo`, `arancione`, `rosso`) e attributi: tipo di criticità,
validità, link al bollettino. Un `binary_sensor` acceso da giallo in su.

**Caldo** — un sensore con l'indice di calore e un `binary_sensor` per il
superamento della soglia.

La zona di allerta si sceglie **una volta in configurazione** da un elenco, invece
di calcolare in quale poligono cadono le coordinate: più prevedibile, e non si
rompe se il DPC ridisegna i confini.

## Notifiche

Nelle opzioni dell'integrazione, per ogni fonte: attiva/disattiva, soglia,
servizio `notify` di destinazione.

| Fonte | Soglia |
|---|---|
| Carburanti | prezzo sotto un valore, per tipo di carburante |
| Terremoti | magnitudo minima e raggio massimo |
| Allerte | livello minimo (giallo, arancione, rosso) |
| Caldo | indice di calore oltre una soglia |

### Antirumore

Senza difese l'integrazione diventa moleste in un pomeriggio, per tre motivi
distinti che richiedono tre rimedi distinti:

1. **Revisioni dello stesso evento.** L'INGV ripubblica un terremoto mentre ne
   affina la magnitudo. Rimedio: gli eventi si identificano per `eventId`, non per
   contenuto; una revisione aggiorna l'entità ma **non rinotifica**, a meno che la
   magnitudo non salga oltre una soglia superiore.
2. **Oscillazione attorno alla soglia.** Un prezzo che balla fra 1,699 e 1,701
   notificherebbe a ogni giro. Rimedio: isteresi — dopo una notifica per
   superamento verso il basso, la successiva richiede che il prezzo sia prima
   risalito sopra soglia più un margine.
3. **Ripetizione della stessa condizione.** Un'allerta arancione dura giorni.
   Rimedio: una notifica per ogni cambio di stato, non per ogni lettura, più un
   tempo minimo fra due notifiche della stessa fonte.

Lo stato dell'antirumore va persistito, altrimenti un riavvio di Home Assistant
rimanda tutte le notifiche già mandate.

## Errori

Ogni provider fallisce per conto proprio: un errore di rete o un formato
inatteso marca *non disponibili* le sue entità e lascia intatte le altre.

Gli errori si registrano nel log una volta per ciclo, non a ogni tentativo. I
fallimenti ripetuti allungano progressivamente l'intervallo, per non martellare
un servizio pubblico che sta avendo problemi.

Il parsing è difensivo: un CSV con una riga malformata scarta la riga, non il file.

## Test

I test coprono la logica pura, senza far girare Home Assistant:

- distanza fra coordinate e filtro per raggio;
- parsing CSV MIMIT, incluse righe malformate, prezzi con virgola, campi mancanti;
- selezione del prezzo più basso fra impianti e carburanti;
- indice di calore, con i valori di riferimento noti;
- valutazione delle soglie e le tre difese antirumore, che sono la parte con più
  probabilità di sbagliare;
- normalizzazione della risposta INGV e del bollettino DPC, da campioni salvati.

Le chiamate di rete non si testano contro i servizi veri: si usano risposte
registrate, così i test restano deterministici e non dipendono dal meteo.

## Distribuzione

Repository pubblico, licenza MIT, `hacs.json` valido, `manifest.json` con chiavi
ordinate, icona in `custom_components/allerte_italia/brand/`, workflow `hassfest`
e `hacs/action` senza `ignore`, release taggata dopo il primo verde.

## Fuori scope della prima versione

- Selezione della zona di allerta calcolata dalle coordinate (point-in-polygon).
- Estrazione dei bollettini caldo dai PDF del Ministero.
- Più zone geografiche: la v1 lavora sulla posizione di casa e un raggio.
- Storico dei prezzi e previsioni.
