# Allerte Italia

**Prezzi dei carburanti, terremoti, allerte della Protezione Civile e ondate di calore in Home Assistant — con notifiche che scattano solo quando lo decidi tu.**

[![Validate](https://github.com/iAlias/AllerteItalia/actions/workflows/validate.yml/badge.svg)](https://github.com/iAlias/AllerteItalia/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-custom-41BDF5)](https://hacs.xyz/)
[![Versione](https://img.shields.io/badge/versione-0.1.1-orange)](custom_components/allerte_italia/manifest.json)
[![Licenza](https://img.shields.io/badge/licenza-MIT-green)](LICENSE)

🇬🇧 [Read in English](README.md)

Quattro fonti pubbliche italiane, sorvegliate in un posto solo, con le soglie che
imposti dall'interfaccia: **non serve saper scrivere automazioni** per essere
avvisato quando il gasolio scende sotto 1,70 € o quando trema la terra vicino a casa.

---

## Indice

- [Cosa sorveglia](#cosa-sorveglia)
- [Installazione](#installazione)
- [Configurazione](#configurazione)
- [Perché non ti tempesta di notifiche](#perché-non-ti-tempesta-di-notifiche)
- [Peso sul sistema](#peso-sul-sistema)
- [Entità](#entità)
- [Sviluppo](#sviluppo)
- [Limiti dichiarati](#limiti-dichiarati)
- [Fonti dei dati](#fonti-dei-dati)
- [Licenza](#licenza)

---

## Cosa sorveglia

| | Fonte | Cosa ottieni |
|---|---|---|
| ⛽ | **MIMIT** — prezzi ufficiali di tutti gli impianti italiani | Prezzo per distributore e carburante, più il più economico nel raggio scelto |
| 🌍 | **INGV** — servizio sismologico nazionale | Ultimo terremoto per magnitudo, luogo, profondità e distanza da te |
| ⚠️ | **Protezione Civile** — bollettini di criticità | Livello di allerta della tua zona: verde, giallo, arancione, rosso |
| 🌡️ | **Indice di calore** | Temperatura percepita calcolata su dati che Home Assistant già ha |

---

## Installazione

**HACS** → Integrazioni → menu ⋮ → *Repository personalizzati* → aggiungi
`https://github.com/iAlias/AllerteItalia` con categoria **Integration** →
installa e riavvia Home Assistant.

Poi *Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Allerte Italia*.

---

## Configurazione

Alla prima configurazione scegli il raggio entro cui cercare i distributori, quali
carburanti ti interessano, il raggio per i terremoti e — se vuoi le allerte — la
tua zona della Protezione Civile.

Le **soglie di notifica** stanno nelle opzioni dell'integrazione:

| Fonte | Soglia | Esempio |
|---|---|---|
| Carburanti | prezzo sotto il quale avvisare | `1.70` |
| Terremoti | magnitudo minima | `3.5` |
| Allerte | livello minimo | `arancione` |
| Caldo | indice di calore | `35` |

Le notifiche vengono inviate al servizio `notify` che indichi: quello del telefono,
Telegram, o `notify.persistent_notification` per vederle dentro Home Assistant.

---

## Perché non ti tempesta di notifiche

È il problema vero di un'integrazione come questa, e ha tre cause distinte con tre
rimedi distinti:

- **Un terremoto viene ripubblicato** mentre l'INGV ne affina la magnitudo. Gli eventi
  sono riconosciuti per identificativo: una revisione aggiorna il sensore ma non
  rinotifica, a meno che la magnitudo non cresca in modo significativo.
- **Un prezzo oscilla attorno alla soglia**, fra 1,699 e 1,701. Dopo un avviso, il
  prezzo deve prima risalire di un margine prima di poter avvisare di nuovo.
- **Un'allerta arancione dura giorni.** Si notifica quando il livello cambia o
  peggiora, non a ogni lettura, e comunque non più di una volta all'ora per fonte.

---

## Peso sul sistema

I due CSV del MIMIT pesano 7,5 MB, ma non finiscono mai interi in memoria:
l'anagrafica viene scaricata al massimo una volta a settimana e **filtrata subito**
per raggio — di ~25.000 impianti ne restano poche decine — e i prezzi vengono letti
riga per riga scartando al volo tutto ciò che non riguarda i distributori scelti.

L'INGV filtra lato server: la risposta è circa un kilobyte.

---

## Entità

**Sensori** — un prezzo per distributore e carburante, il più economico per tipo,
la magnitudo dell'ultimo terremoto, il livello di allerta, l'indice di calore.

**Sensori binari** — terremoto recente sopra soglia, allerta attiva, allerta caldo.

Ogni fonte è indipendente: se il MIMIT non risponde, i terremoti continuano ad
arrivare e solo i sensori dei carburanti risultano non disponibili.

---

## Sviluppo

```bash
python -m pytest tests -q
```

I test coprono la logica pura — distanze, parsing dei CSV, indice di calore,
normalizzazione dei feed e le tre regole antirumore — e non richiedono che Home
Assistant sia in esecuzione né una connessione di rete.

---

## Limiti dichiarati

- La zona di allerta si ricava dal **comune** che indichi: il bollettino elenca i
  comuni di ogni zona, quindi non serve calcolare in quale poligono cadi.
- Le ondate di calore sono **derivate** dall'indice di calore: il Ministero della
  Salute pubblica i suoi bollettini solo in PDF.
- Una sola posizione, quella di casa configurata in Home Assistant.

---

## Fonti dei dati

I dati appartengono ai rispettivi enti e restano soggetti alle loro condizioni:
[MIMIT](https://www.mimit.gov.it/), [INGV](https://www.ingv.it/),
[Dipartimento della Protezione Civile](https://github.com/pcm-dpc).

---

## Licenza

[MIT](LICENSE) © 2026 iAlias
