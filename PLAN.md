# DSI Mapper — Piano di Sviluppo

## Visione

Piattaforma SaaS per ispezione fotovoltaica con drone: dalla pianificazione del volo al digital twin dell'impianto, con reportistica IEC 62446-3. Target: operatori drone FV europei (modello Raptor Maps).

---

## Architettura di Sistema

### Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DSI Mapper Platform                          │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌───────────┐   ┌────────────┐ │
│  │  Flight   │──▶│   Data       │──▶│  Analysis  │──▶│  Digital   │ │
│  │  Planner  │   │   Ingestion  │   │  Engine    │   │  Twin      │ │
│  └──────────┘   └──────────────┘   └───────────┘   └────────────┘ │
│       │                                    │              │         │
│       ▼                                    ▼              ▼         │
│  ┌──────────┐                      ┌───────────┐   ┌────────────┐ │
│  │  KMZ     │                      │  Defect   │   │  IEC 62446 │ │
│  │  Export   │                      │  Database │   │  Reports   │ │
│  └──────────┘                      └───────────┘   └────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Serial Reading Pipeline                    │  │
│  │  RGB Zoom → Label Detection → Crop → Super-Res → OCR        │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Tecnologia | Motivo |
|-------|-----------|--------|
| **Backend** | Python 3.12 + FastAPI | Ecosistema AI/GIS maturo, async, type-safe |
| **Frontend** | React 18 + TypeScript + Leaflet | Mappa interattiva, component library ricca |
| **Database** | PostgreSQL 16 + PostGIS + TimescaleDB | Geospatial queries + time-series per storico pannelli |
| **Processing** | OpenDroneMap (Docker) | Ortomosaico, DSM, nuvole di punti |
| **AI Detection** | YOLOv8 (Ultralytics) + PyTorch | Panel detection + defect classification |
| **Thermal** | DJI Thermal SDK + flirimageextractor | Estrazione temperature da R-JPEG |
| **OCR** | EasyOCR + Real-ESRGAN | Lettura seriali da immagini drone |
| **GIS** | GDAL, rasterio, shapely | Manipolazione raster/vector |
| **Report** | ReportLab + Jinja2 | PDF IEC 62446-3 compliant |
| **Object Storage** | MinIO (locale) → S3 (cloud) | COG, immagini originali, report |
| **Task Queue** | Celery + Redis | Processing asincrono lungo (ODM, AI) |
| **Containerization** | Docker Compose | Sviluppo locale, deploy identico |

### Struttura Repository

```
DSI-Mapper/
├── docker-compose.yml          # Orchestrazione locale
├── docker-compose.prod.yml     # Override per produzione
│
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py           # Settings (pydantic-settings)
│   │   ├── models/             # SQLAlchemy + GeoAlchemy2 models
│   │   │   ├── site.py         # Impianto FV
│   │   │   ├── inspection.py   # Ispezione (evento)
│   │   │   ├── module.py       # Singolo pannello (asset)
│   │   │   ├── defect.py       # Difetto rilevato
│   │   │   └── flight.py       # Piano di volo
│   │   ├── api/                # Endpoint REST
│   │   │   ├── flights.py      # CRUD piani volo + export KMZ
│   │   │   ├── ingestion.py    # Upload immagini + trigger processing
│   │   │   ├── analysis.py     # Status/risultati analisi
│   │   │   ├── sites.py        # CRUD impianti
│   │   │   ├── inspections.py  # CRUD ispezioni
│   │   │   ├── reports.py      # Generazione report IEC
│   │   │   └── serials.py      # Pipeline lettura seriali
│   │   ├── services/           # Business logic
│   │   │   ├── flight_planner.py
│   │   │   ├── thermal_processor.py
│   │   │   ├── odm_processor.py
│   │   │   ├── ai_detector.py
│   │   │   ├── serial_reader.py
│   │   │   ├── digital_twin.py
│   │   │   └── report_generator.py
│   │   ├── tasks/              # Celery async tasks
│   │   │   ├── process_flight.py
│   │   │   ├── run_detection.py
│   │   │   └── generate_report.py
│   │   └── iec/                # IEC 62446-3 compliance logic
│   │       ├── standards.py    # Soglie, classificazioni, requisiti
│   │       ├── validators.py   # Validazione condizioni ambientali
│   │       └── templates/      # Template Jinja2 per report PDF
│   ├── tests/
│   ├── alembic/                # DB migrations
│   └── requirements.txt
│
├── frontend/                   # React SPA
│   ├── src/
│   │   ├── pages/
│   │   │   ├── FlightPlanner/  # Mappa + editor piano volo
│   │   │   ├── DataIngestion/  # Upload + progress processing
│   │   │   ├── Analysis/       # Risultati AI + mappa difetti
│   │   │   ├── DigitalTwin/    # Vista impianto + storico pannelli
│   │   │   ├── Reports/        # Generazione + download report
│   │   │   └── SerialReader/   # Pipeline seriali
│   │   ├── components/
│   │   │   ├── Map/            # Leaflet wrapper + layers
│   │   │   ├── PanelInspector/ # Dettaglio singolo pannello
│   │   │   └── DefectGallery/  # Galleria difetti con filtri
│   │   └── lib/
│   └── package.json
│
├── ai/                         # Modelli AI e training
│   ├── models/                 # Pesi modelli (gitignored)
│   ├── training/
│   │   ├── train_panel_detector.py
│   │   ├── train_defect_classifier.py
│   │   └── train_serial_detector.py
│   ├── inference/
│   │   ├── panel_detector.py
│   │   ├── defect_classifier.py
│   │   ├── thermal_analyzer.py
│   │   └── serial_ocr.py
│   └── datasets/               # Script download + preparazione dataset
│       ├── download_pvhawk.py
│       ├── download_pvf10.py
│       └── prepare_training.py
│
├── dji/                        # DJI integration
│   ├── thermal_sdk/            # Wrapper Python per DJI Thermal SDK
│   │   ├── __init__.py
│   │   └── rjpeg_decoder.py    # ctypes binding a libdirp.dll
│   ├── kmz_generator/          # Generatore piani volo KMZ
│   │   ├── __init__.py
│   │   ├── mission.py          # Modello missione (waypoint, azioni)
│   │   ├── exporter.py         # Export KMZ per DJI Pilot 2
│   │   └── templates/          # Template KML
│   └── simulator/              # Config e script per DJI Simulator
│       └── README.md
│
└── docs/
    ├── architecture.md
    ├── iec-62446-3-reference.md
    └── api.md
```

---

## Pipeline Principale: Ispezione Termica FV

### Fase 1 — Pianificazione Volo

**Input:** Coordinate impianto (poligono), parametri missione
**Output:** File KMZ importabile in DJI Pilot 2

Funzionalita':
- Importa perimetro impianto da GeoJSON, KML, o disegno su mappa
- Calcolo automatico rotte di volo:
  - Pattern lawnmower (boustrophedon) per copertura termica
  - Quota ottimale in base a GSD target (IEC: risoluzione geometrica ≤ dimensione cella)
  - Overlap frontale 80%, laterale 60% (requisito ODM + IEC)
  - Velocita' drone adattata a shutter speed per evitare motion blur
- Parametri IEC 62446-3 pre-impostati:
  - Angolo camera: nadir (0°) per termica, obliquo opzionale per RGB
  - GSD target: ≤3 cm/px per termica (identificazione difetto a livello cella)
  - Orario volo: irradianza ≥600 W/m², vento ≤3 Bft (validazione pre-volo)
- Export KMZ compatibile DJI Pilot 2 (waypoint + azioni camera)
- Supporto dual-camera M30T: trigger simultaneo RGB + termico

**Test su simulatore:**
- DJI Flight Simulator (richiede M30T connesso via USB al PC)
- Validazione: rotta corretta, trigger camera, overlap coverage

### Fase 2 — Esecuzione Volo e Raccolta Dati

**Input:** KMZ caricato su DJI Pilot 2
**Output:** Immagini R-JPEG termiche + JPEG RGB con EXIF/GPS sulla SD card

Workflow operatore:
1. Pre-volo: checklist IEC (irradianza, vento, temperatura ambiente) → registrata nell'app
2. Carica KMZ su DJI Pilot 2 via controller
3. Esegui missione autonoma
4. Post-volo: trasferisci SD card → upload immagini in DSI Mapper

Dati ambientali da registrare (IEC 62446-3 obbligatori):
- Irradianza sul piano dei moduli (POA) in W/m² — misurata con piranometro o cella di riferimento
- Temperatura ambiente (°C)
- Velocita' e direzione vento
- Umidita' relativa
- Timestamp inizio/fine volo

### Fase 3 — Analisi Dati

Pipeline di processing (Celery task chain):

```
3.1  Thermal Decode
     R-JPEG → DJI Thermal SDK → matrice temperatura (float32 per pixel)
     Output: GeoTIFF radiometrico (temperatura in °C)

3.2  Orthomosaic Generation
     Immagini RGB → OpenDroneMap → ortofoto RGB georeferenziata (COG)
     Immagini termiche → ODM con --radiometric-calibration → ortofoto termica (COG)
     Output: ortofoto RGB + termica allineate, DSM, nuvola punti

3.3  Panel Detection
     Ortofoto → YOLOv8 instance segmentation → bounding box + mask per ogni modulo
     Output: poligoni GeoJSON di ogni pannello con coordinate WGS84

3.4  Defect Detection (IEC 62446-3 compliant)
     Per ogni pannello segmentato:
     - Estrai patch termica
     - Calcola ΔT (differenza vs media stringa/array)
     - Classifica anomalia secondo IEC:
       · Classe 1: ΔT < 10K → monitoraggio
       · Classe 2: 10K ≤ ΔT < 20K → azione necessaria
       · Classe 3: ΔT ≥ 20K → azione urgente
     - Tipologia difetto: hotspot, diode bypass, cella difettosa,
       PID, string fault, soiling, ombreggiamento
     Output: tabella difetti con coordinate, classe, ΔT, tipo, foto termica crop

3.5  Georeferencing & Panel Mapping
     Associa ogni pannello a posizione nell'impianto:
     - Riga, colonna, stringa, inverter
     - Coordinate centroide + poligono footprint
     Output: mappa completa dell'impianto con ID per ogni pannello
```

### Fase 4 — Digital Twin

**Data model (PostGIS):**

```sql
sites
├── id, name, location (POLYGON), capacity_kw, commissioning_date
├── client_id (FK)
└── metadata (JSONB: orientamento, tilt, tipo modulo, inverter)

modules
├── id, site_id (FK), geometry (POLYGON 4326)
├── row_index, col_index, string_id, inverter_id
├── serial_number (nullable — popolato da pipeline seriali)
├── installation_date
└── module_type, manufacturer

inspections
├── id, site_id (FK), date, operator_id
├── environmental_conditions (JSONB: irradiance, temp, wind, humidity)
├── instruments (JSONB: camera model, lens, calibration cert)
├── flight_id (FK)
└── status (processing|completed|validated)

defects
├── id, module_id (FK), inspection_id (FK)
├── geometry (POINT 4326)
├── defect_type (enum: hotspot, bypass_diode, cell, pid, string, soiling, shading)
├── iec_class (1|2|3)
├── delta_t_kelvin (FLOAT)
├── thermal_image_url, rgb_image_url
├── notes
└── status (open|monitoring|resolved|replaced)

module_history (TimescaleDB hypertable)
├── module_id (FK), inspection_id (FK), timestamp
├── avg_temperature, max_temperature, delta_t
├── defect_count, iec_class_max
└── status_snapshot
```

**Funzionalita' dashboard:**
- Mappa impianto con overlay termico
- Click su pannello → storico completo (tutte le ispezioni)
- Filtri: per classe IEC, per tipo difetto, per stringa/inverter
- Trend temperatura nel tempo (grafici per pannello/stringa)
- Heatmap di degrado (quali zone peggiorano)
- KPI impianto: % pannelli anomali, distribuzione classi IEC, confronto anno/anno

### Fase 5 — Report IEC 62446-3

**Struttura report PDF conforme:**

```
1. Copertina
   - Identificazione impianto, committente, ispettore
   - Data ispezione, condizioni ambientali

2. Sommario esecutivo
   - Risultati principali, KPI, classificazione complessiva
   - Raccomandazioni prioritarie

3. Informazioni impianto
   - Layout, specifiche tecniche, storico

4. Metodologia di ispezione
   - Strumentazione (drone, camera termica, calibrazione)
   - Parametri di volo (quota, GSD, overlap)
   - Condizioni ambientali al momento del rilievo
   - Riferimenti normativi (IEC 62446-3, IEC 61215, IEC 61730)

5. Risultati analisi termica
   - Ortofoto termica con overlay difetti
   - Tabella difetti completa:
     · ID pannello, coordinate, tipo difetto
     · Classe IEC (1/2/3), ΔT misurato
     · Immagine termica + RGB del difetto
   - Distribuzione difetti per tipo e classe
   - Mappa difetti su layout impianto

6. Analisi per stringa/inverter
   - Performance relativa per stringa
   - Identificazione pattern (stringhe problematiche)

7. Storico (se disponibile)
   - Confronto con ispezioni precedenti
   - Trend di degrado

8. Raccomandazioni
   - Azioni per classe IEC
   - Priorita' interventi
   - Stima impatto su produzione

9. Allegati
   - Certificati calibrazione strumenti
   - Dati grezzi (CSV export)
   - Dichiarazione di conformita' IEC 62446-3
```

---

## Pipeline Seriali (adattata)

Stessa architettura concettuale con modifiche specifiche:

### Fase 1 — Pianificazione Volo Seriali

Differenze dalla missione termica:
- Quota piu' bassa: 8-12m (vs 25-40m termica)
- Camera RGB con zoom ottico 10-16x
- Pattern specifico: volo lungo le file di pannelli
- GSD target: ≤1 mm/px (necessario per OCR)
- Angolo: 60-75° rispetto al piano del modulo (per evitare riflessi)
- Velocita' ridotta per nitidezza

### Fase 2 — Esecuzione e Raccolta

- Solo camera RGB wide/zoom (no termico)
- Focus su label area dei pannelli
- Scatto ad alta risoluzione con zoom

### Fase 3 — Analisi Seriali

```
3.1  Label Region Detection
     Immagine RGB → YOLOv8 (modello custom) → bounding box etichetta

3.2  Crop & Enhancement
     Crop label → Real-ESRGAN super-resolution (4x) → immagine enhancata

3.3  OCR
     Immagine enhancata → EasyOCR → testo seriale candidato

3.4  Validation & Matching
     Seriale OCR → regex validation (formato produttore noto)
     → match con database moduli (coordinate GPS → panel_id → serial)
```

### Fase 4-5 — Identiche

I seriali riconosciuti vengono scritti nel campo `serial_number` della tabella `modules`. Il digital twin e i report si arricchiscono con l'informazione seriale.

---

## DJI Integration

### DJI Thermal SDK

- Libreria C/C++ fornita da DJI (libdirp.dll / libdirp.so)
- Wrapper Python via ctypes per integrare nel backend
- Funzioni chiave:
  - `dirp_create_from_rjpeg()` — carica R-JPEG
  - `dirp_measure_ex()` — estrai matrice temperatura pixel-per-pixel
  - `dirp_set_measurement_params()` — imposta emissivita', distanza, temperatura riflessa
- Output: numpy array float32 (H x W) con temperature in °C

### DJI Pilot 2 / KMZ Integration

- Formato: KMZ (zip contenente KML + risorse)
- KML con `<wpml:*>` namespace DJI per waypoint mission
- Elementi chiave:
  - `<wpml:missionConfig>` — tipo volo, velocita', altitudine
  - `<wpml:waypoint>` — lat, lon, alt, heading
  - `<wpml:action>` — trigger camera (foto/video), zoom, gimbal angle
- Template KML parametrizzato con Jinja2

### DJI Flight Simulator

- Software DJI per testare missioni in ambiente virtuale
- Requisito: M30T connesso via USB al PC + DJI Assistant 2 Enterprise
- Workflow test:
  1. Genera KMZ da DSI Mapper
  2. Carica su DJI Pilot 2 (controller connesso)
  3. Avvia simulazione → il drone "vola" virtualmente
  4. Verifica: rotta, trigger camera, coverage area

---

## Fasi di Sviluppo (Roadmap)

### MILESTONE 1 — Fondamenta (settimane 1-4)

**Obiettivo:** Infrastruttura base funzionante, primo import di dati reali.

1. **Setup progetto**
   - Init repo con struttura directory
   - Docker Compose: PostgreSQL+PostGIS, Redis, MinIO, NodeODM
   - Backend FastAPI skeleton con auth base (JWT)
   - Frontend React skeleton con routing e mappa Leaflet
   - CI/CD base (GitHub Actions: lint + test)

2. **Data model e migrations**
   - Modelli SQLAlchemy/GeoAlchemy2 per sites, modules, inspections, defects
   - Alembic migrations
   - Seed data: un impianto di test

3. **DJI Thermal SDK wrapper**
   - Python ctypes binding per libdirp
   - Funzione: R-JPEG → numpy temperature array → GeoTIFF
   - Test con immagini reali M30T

4. **Ingestion base**
   - API upload immagini (chunked upload per file grandi)
   - Storage su MinIO
   - Estrazione EXIF/GPS metadata

### MILESTONE 2 — Flight Planner + KMZ Export (settimane 5-7)

**Obiettivo:** Pianificare voli e esportare KMZ per DJI Pilot 2.

1. **Flight Planner UI**
   - Editor mappa: disegna/importa perimetro impianto
   - Generazione automatica rotta lawnmower
   - Parametri configurabili: quota, GSD, overlap, velocita'
   - Preview rotta su mappa con stima durata/batterie

2. **KMZ Generator**
   - Template KML con namespace DJI wpml
   - Waypoint con azioni camera (foto, intervallo, zoom)
   - Export KMZ scaricabile
   - Preset IEC: termica (nadir, GSD ≤3cm) e seriali (bassa quota, zoom)

3. **Test su DJI Simulator**
   - Documentazione setup simulatore
   - Validazione KMZ generati su simulatore

### MILESTONE 3 — Processing Pipeline (settimane 8-12)

**Obiettivo:** Da immagini raw a ortomosaico + detection pannelli.

1. **ODM Integration**
   - Celery task: submit job a NodeODM via PyODM
   - Processing RGB → ortofoto + DSM
   - Processing termico → ortofoto radiometrica
   - Monitoraggio progresso, gestione errori

2. **Panel Detection AI**
   - Setup training pipeline YOLOv8
   - Pre-training su dataset aperti (PV-Hawk, Zenodo UAV PV)
   - Inference: ortofoto → poligoni pannelli GeoJSON
   - Salvataggio pannelli rilevati in PostGIS

3. **Thermal Analysis**
   - Per ogni pannello: estrai patch termica dal GeoTIFF
   - Calcolo statistiche: media, max, ΔT vs stringa
   - Classificazione IEC: classe 1/2/3
   - Salvataggio difetti nel DB

### MILESTONE 4 — Digital Twin Dashboard (settimane 13-16)

**Obiettivo:** Visualizzazione completa impianto con storico.

1. **Mappa impianto interattiva**
   - Overlay: ortofoto RGB, termico, pannelli rilevati, difetti
   - Click pannello → sidebar con dettaglio + storico
   - Filtri per tipo difetto, classe IEC, stringa/inverter

2. **Storico e trend**
   - TimescaleDB hypertable per module_history
   - Grafici trend temperatura per pannello/stringa
   - Confronto tra ispezioni successive
   - Heatmap degrado

3. **Multi-site management**
   - Lista impianti con KPI sintetici
   - Dashboard aggregata per operatore

### MILESTONE 5 — Report IEC 62446-3 (settimane 17-19)

**Obiettivo:** Report PDF conforme alla normativa.

1. **Report engine**
   - Template Jinja2 → ReportLab PDF
   - Sezioni conformi a IEC 62446-3 (vedi struttura sopra)
   - Inserimento automatico: ortofoto, tabella difetti, grafici, mappe

2. **Validazione IEC**
   - Check condizioni ambientali (irradianza ≥600 W/m²)
   - Check strumentazione (calibrazione valida)
   - Warning se requisiti non soddisfatti
   - Dichiarazione di conformita' con checklist

3. **Export dati**
   - CSV difetti per import in CMMS
   - GeoJSON pannelli + difetti
   - Raw data archive

### MILESTONE 6 — Serial Reading Pipeline (settimane 20-23)

**Obiettivo:** OCR seriali pannelli da immagini drone RGB.

1. **Serial flight planning**
   - Preset volo dedicato: bassa quota, zoom, pattern lungo file
   - KMZ con trigger zoom camera

2. **AI pipeline seriali**
   - YOLOv8 custom: detection regione etichetta
   - Real-ESRGAN: super-resolution 4x
   - EasyOCR: estrazione testo
   - Regex validation per formati seriali noti

3. **Matching e database**
   - Associazione seriale → pannello via coordinate GPS
   - UI per correzione manuale OCR dubbi
   - Statistiche: % seriali letti con successo

### MILESTONE 7 — SaaS Multi-Operatore (settimane 24-30)

**Obiettivo:** Da tool interno a piattaforma multi-utente.

1. **Multi-tenancy**
   - Schema per organizzazione/team
   - Ruoli: admin, operatore, cliente (view-only)
   - Isolamento dati tra organizzazioni

2. **Client portal**
   - Dashboard read-only per asset manager
   - Accesso report e storico impianti assegnati
   - Notifiche difetti critici

3. **Deploy cloud**
   - Docker Compose → Kubernetes / Docker Swarm
   - GPU cloud per processing (spot instances)
   - CDN per ortofoto (COG + tile server)
   - Backup automatici DB

### MILESTONE 8 (Futuro) — DJI Mobile SDK v5 Android App

**Obiettivo:** App Android custom per controller DJI RC Plus.

1. **Android app** (Kotlin + DJI MSDK v5)
   - Carica piano volo da DSI Mapper API
   - Esecuzione missione autonoma con UI custom
   - Telemetria live → backend
   - Sync immagini automatica post-volo
2. **Integrazione bidirezionale**
   - Pianifica su web → esegui su app
   - Dati app → upload automatico a backend

---

## Ambiente di Sviluppo

### Hardware locale

- **GPU:** NVIDIA GTX 1080 Ti (11GB VRAM, CUDA 6.1)
  - Sufficiente per: inference YOLOv8, fine-tuning su dataset piccoli (<5k immagini), ODM processing
  - Non ideale per: training da zero su dataset grandi, modelli segmentazione pesanti
- **Dati test:** Dataset completi reali da DJI M30T (RGB + termico R-JPEG)
- **Sensori:** Piranometro e stazione meteo disponibili per dati IEC

### Cloud training (per dataset grandi)

| Servizio | GPU | Costo/ora | Uso |
|----------|-----|-----------|-----|
| Google Colab Pro | T4/V100 | ~10 EUR/mese flat | Sperimentazione, notebook |
| Vast.ai | RTX 3090/4090 | ~0.20-0.50 EUR | Training YOLOv8 (il piu' economico) |
| RunPod | RTX 3090 | ~0.40 EUR | Training con Docker custom |
| Lambda Cloud | A10G/A100 | ~1.10-2.50 EUR | Dataset molto grandi, training multi-GPU |

Stima costo training YOLOv8 su ~5000 immagini termiche: **~1-2 EUR** su Vast.ai (2-4 ore RTX 3090).

---

## Dipendenze Esterne

| Componente | Licenza | Note |
|-----------|---------|------|
| DJI Thermal SDK | Proprietaria (gratuita) | Richiede download da DJI Developer |
| DJI Flight Simulator | Proprietaria | Richiede M30T + DJI Assistant 2 Enterprise |
| OpenDroneMap | AGPL-3.0 | Se usato come servizio SaaS → verificare compliance AGPL |
| YOLOv8 (Ultralytics) | AGPL-3.0 | Stesso discorso AGPL. Alternativa: uso con licenza Enterprise |
| Real-ESRGAN | BSD-3 | OK per uso commerciale |
| EasyOCR | Apache-2.0 | OK per uso commerciale |
| PostGIS | GPL-2.0 | OK (database engine, non linkato) |
| ReportLab | BSD | OK per uso commerciale |

**Nota AGPL:** ODM e YOLOv8 sono AGPL. Per SaaS questo significa che il codice sorgente del servizio che li usa deve essere reso disponibile. Opzioni:
1. Rendere DSI Mapper open source (modello open-core)
2. Acquistare licenza Enterprise Ultralytics (~$800/anno)
3. Isolare ODM/YOLO come microservizi separati con API, mantenendo il core proprietario

---

## Comandi Sviluppo

```bash
# Setup iniziale
git clone https://github.com/[username]/DSI-Mapper.git
cd DSI-Mapper
cp .env.example .env
docker compose up -d                  # DB, Redis, MinIO, NodeODM

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate             # Linux/Mac
pip install -r requirements.txt
alembic upgrade head                  # migrations
uvicorn app.main:app --reload         # dev server :8000

# Frontend
cd frontend
npm install
npm run dev                           # dev server :5173

# AI Training
cd ai
python training/train_panel_detector.py --data datasets/pvhawk --epochs 100

# Test
cd backend && pytest
cd frontend && npm test
```
