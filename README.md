# Volvo Klassieker Vereniging – Documentcontrole

Dit project is een server-first proof-of-concept voor documentcontrole binnen de Volvo Klassieker Vereniging (VKV). Het doel is om redacteuren een eenvoudige workflow te bieden voor het uploaden van documenten, lokaal controleren met LanguageTool, aanpassen van fouten en downloaden van het gecorrigeerde document, zonder externe LLM-API's of cloudspellingsdiensten te gebruiken.

## Kernprincipes

- Server-first architectuur, niet laptop-first.
- Geen externe LLM-API's.
- Lokale spellingscontrole via LanguageTool op dezelfde server of in een lokale Docker-container.
- De documentparser en corrigeren-logica zijn onafhankelijk van deploymentmodel.
- Dezelfde codebase moet lokaal, op een Windows-apparaat en in een server- of Docker-omgeving kunnen draaien.

## Ontwerpkeuzes

### 1. Server-first opbouw

De applicatie bestaat uit een modulair FastAPI-backend met:

- upload- en validatie-API
- tekstparsers voor TXT en DOCX
- lokale LanguageTool-client
- correctiemodule voor tekst- en DOCX-aanpassingen
- eenvoudige webinterface met HTML/CSS/vanilla JS

Deze logica wordt niet gekoppeld aan Windows of Docker; alleen de startup- en deploymentlaag verschilt.

### 2. Lokale LanguageTool-integratie

De voorkeur gaat uit naar een volledig lokale LanguageTool-instantie, bijvoorbeeld:

- lokaal Java-process
- of Docker-container met `erikzaadi/languagetool` of officiële LanguageTool image

De backend communiceert alleen met `LANGUAGETOOL_URL`, standaard `http://127.0.0.1:8081`.

### 3. DOCX-behoud van opmaak

Voor DOCX gebruiken we `python-docx` en werken we op run-/paragraph-niveau in plaats van de volledige paragraaf opnieuw te reconstrueren. Dat minimaliseert het risico op verlies van vet, cursief, koppen en lijsten.

### 4. Deployment zonder WSL als verplichte eis

Voor Windows is het doel een native installatiemethode zonder dat de eindgebruiker Python, Java of WSL handmatig hoeft te installeren. De server-variant gebruikt Docker, terwijl een native Windows-build via PyInstaller of een bundeld package kan worden uitgebracht.

## Projectstructuur

```text
VKV-mag/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   ├── document.py
│   │   └── correction.py
│   ├── parsers/
│   │   ├── base.py
│   │   ├── docx_parser.py
│   │   └── txt_parser.py
│   ├── routes/
│   │   ├── upload.py
│   │   └── check.py
│   ├── services/
│   │   ├── correction_service.py
│   │   └── languagetool.py
│   ├── static/
│   │   └── css/
│   │       └── styles.css
│   ├── templates/
│   │   ├── index.html
│   │   └── editor.html
│   └── __init__.py
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/
│   └── architecture.md
├── installer/
│   └── README.md
├── storage/
│   ├── temporary/
│   └── uploads/
├── tests/
│   └── test_phase1.py
├── .env.example
├── requirements.txt
├── README.md
└── pyproject.toml
```

## Fase 1

De eerste fase levert een werkend proof-of-concept op met:

1. FastAPI-app
2. Simpel webinterface
3. TXT- en DOCX-upload
4. Tekstextractie
5. Lokale LanguageTool-call
6. Fouten en suggesties tonen
7. Eenvoudige correcties toepassen
8. Gecorrigeerd document downloaden

## Verdere fasen

- Fase 2: verbeterde DOCX-formatting, editor, VKV-woordenlijst, filtering
- Fase 3: Windows packaging en browserstart
- Fase 4: Docker deployment, reverse proxy, toekomstige loginintegratie

## Opstarten

Gebruik een lokale Python-omgeving en start de app via:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
```

De app verwacht een lokaal draaiende LanguageTool-instantie op de configuratie-URL, standaard `http://127.0.0.1:8081`.

## Privacy

- Geen externe API's
- Geen analytics van derden
- Tijdelijke bestanden worden standaard lokaal verwijderd
- Uploads worden niet gelogd met volledige documentinhoud

## Belangrijk

Het project is bewust ontworpen als een server-side backend met een modulair documentframework. Daardoor kan dezelfde codebase later zowel lokaal als op een Linux/Docker-server worden ingezet zonder een volledige herarchitectuur.
