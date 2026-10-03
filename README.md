# Volvo Klassieker Vereniging – Documentcontrole

## Windows-versie delen

Voor Windows 10/11 (64-bit) is er een zelfstandig installatieprogramma:
`VKV-Documentcontrole-Setup.exe`. Het bevat Python, Java en LanguageTool en
werkt lokaal zonder verbinding met deze server.

1. Download [VKV-Documentcontrole-Setup.exe](installer/dist/VKV-Documentcontrole-Setup.exe)
   via de downloadknop op GitHub, of haal het op met Git LFS (zie de Windows-handleiding).
2. Start de `.exe` en volg de installatiestappen. Een aparte installatie van Python,
   Java of Docker is niet nodig.
3. Open de snelkoppeling **VKV Documentcontrole**. Na het starten van de lokale
   spellingcontrole opent de app in de standaardbrowser.
4. Laat het startvenster open tijdens het werken. Download het gecorrigeerde
   document en druk daarna in het startvenster op **Enter** om de app af te sluiten.

De huidige build is niet digitaal ondertekend. Installatie en documentverwerking
zijn onder Wine getest; voer voor productiewerk ook een proef uit op de Windows-pc.
Zie [Windows-installatie, gegevens en bouwen](installer/README.md) voor details.

Het bestand wordt op de buildserver gegenereerd in
`installer/dist/VKV-Documentcontrole-Setup.exe` en kan als één bestand worden gedeeld.
Documentuploads in `storage/uploads/` en tijdelijke Windows-buildbestanden worden niet in Git opgenomen.
De distributie-`.exe` wordt via Git LFS bijgehouden; het SHA-256-controlebestand staat ernaast.

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

De Docker-container draait standaard met UID/GID `1000:1000`, passend bij de
schrijfrechten van de opslagmappen op deze server. Gebruik bij een verhuizing
zo nodig `VKV_UID` en `VKV_GID` om de gebruiker met schrijfrechten op `storage`
te kiezen.

## Testen

Installeer de afhankelijkheden in een virtuele omgeving:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Voer de tests uit met tijdelijke opslag, zodat testuploads gescheiden blijven
van bestaande documenten:

```bash
VKV_TEST_DIR=$(mktemp -d)
UPLOAD_DIR="$VKV_TEST_DIR/uploads" TEMP_DIR="$VKV_TEST_DIR/temporary" .venv/bin/python -m pytest -q
```

De uploadtest gebruikt een draaiende lokale LanguageTool-instantie, standaard
op `http://127.0.0.1:8010`. Stel zo nodig `LANGUAGETOOL_URL` in.

## Gevoeligheid

Kies vóór het uploaden **Voorzichtig** (standaard), **Normaal** of **Streng**.
Voorzichtig toont spelling en typefouten. Normaal voegt grammatica en
interpunctie toe. Streng toont ook stijl, woordkeuzes en overige suggesties.
De browser onthoudt uw gekozen stand. Dit zijn filters op regelsoorten, geen zekerheidsscores. Woordvervangingen uit
de categorie Vergissingen, zoals `mijne` → `mijn`, verschijnen alleen bij Streng.

Spellingssuggesties staan vooraf aangevinkt. Overige suggesties moet u per stuk
aankruisen bij **Overnemen**. U kunt elke suggestie uitvinken of een andere
vervanging kiezen. Alleen aangevinkte suggesties verschijnen als wijzigingen
in de tekst- en PDF-vergelijking. Een heel deel goedkeuren neemt twijfelachtige
suggesties niet automatisch over. Na een gewijzigde keuze maakt **PDF vergelijken**
een nieuwe weergave. Keuzes gelden voor de huidige controle; opnieuw controleren
begint met nieuwe keuzes.

**Gecorrigeerd document downloaden** maakt bij elke klik een nieuw bestand met
de actuele aangevinkte correcties van alle delen/pagina’s. Uitgevinkte suggesties
blijven ongewijzigd. De originele upload wordt niet overschreven. PDF-downloads
behouden hun afzonderlijke pagina’s en bevatten geen rode of groene markeringen;
de bescherming van woordafbrekingen geldt ook voor de download. TXT en DOCX
worden in hun eigen formaat opgeslagen. Bij een DOCX-correctie die een
alineagrens wijzigt verschijnt een melding, omdat die niet met behoud van
opmaak kan worden verwerkt.

PDF-correcties gebruiken het oorspronkelijke ingesloten lettertype, de kleur,
lettergrootte, dikte, letterbreedte en letterafstand. Langere correcties schuiven
volgende woorden zo nodig op met behoud van de woordafstand. Past de tekst niet,
dan verschijnt een melding in plaats van verkleinde tekst. Ontbreekt een nieuw
leesteken in het ingesloten font, dan krijgt alleen dat teken een vervangend font
met dezelfde kleur en grootte; de interface meldt dit bij vergelijken en downloaden.

Met **Niet verbeteren** laat u alleen de huidige plek ongewijzigd.
**Nergens overnemen** vinkt alle suggesties met dezelfde oorspronkelijke tekst,
dezelfde gekozen vervanging en dezelfde controleregel uit, op alle pagina’s van
het huidige document. Andere vervangingen blijven ongemoeid. De goedkeuring van
betrokken pagina’s vervalt; de PDF wordt bij opnieuw vergelijken bijgewerkt.
U kunt een afzonderlijke plek weer aanvinken als uitzondering. Deze keuze geldt
voor de huidige controle en wordt bij een nieuwe upload niet onthouden.

Via **Gevoeligheid wijzigen / opnieuw controleren** kunt u hetzelfde bestand
met een andere stand opnieuw laten controleren.

Voor de afzonderlijke browsertest:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_sensitivity.py
```

Deze test gebruikt een tijdelijke lokale webserver en vaste controlesuggesties.

Woordafbrekingen en suggesties om woorden samen te voegen of anders te splitsen
worden in alle standen overgeslagen. Ook losse fragmenten van afgebroken woorden
blijven ongemoeid. De PDF-vergelijking beschermt deze afbrekingen bovendien bij
verzoeken vanuit een oude browsersessie.

## Redactiefonts

Bij een ontbrekend of onbruikbaar PDF-lettertype verschijnt bij vergelijken of
downloaden een uploadveld. Kies het bijbehorende OTF/TTF-bestand (maximaal 10 MB)
en klik op **Lettertype uploaden**. Daarna kunt u opnieuw vergelijken of downloaden;
de gekozen correcties blijven behouden. Het font blijft beschikbaar voor volgende
documenten. Een verkeerde fontvariant of ongeldig bestand wordt geweigerd.

Bij een afwijkende interne naam kunt u expliciet **Toch gebruiken** aanvinken.
Dit bewaart een koppeling tussen het gevraagde font en het geüploade bestand,
ook voor volgende documenten. Het bestand moet nog steeds een geldig font zijn
en de benodigde letters bevatten. Fontfouten vermelden de PDF-pagina (het deel
in de controle, niet het gedrukte paginanummer) en de betrokken tekstcorrectie.
U kunt die correctie uitzetten om de oorspronkelijke tekst te behouden.

Volledige redactiefonts kunnen als `.otf` of `.ttf` in `storage/fonts/` worden
geplaatst. De PDF-verwerking gebruikt deze automatisch wanneer een benodigde
letter ontbreekt in de ingesloten PDF-fonts. De interne fontnaam, inclusief
gewicht en stijl, moet overeenkomen; alleen de bestandsnaam wijzigen helpt niet.
De oorspronkelijke kleur, grootte en letterafstand blijven behouden. De map
wordt via het bestaande storage-volume ook in Docker beschikbaar gemaakt.

## Privacy

- Geen externe API's
- Geen analytics van derden
- Tijdelijke bestanden worden standaard lokaal verwijderd
- Uploads worden niet gelogd met volledige documentinhoud

## Belangrijk

Het project is bewust ontworpen als een server-side backend met een modulair documentframework. Daardoor kan dezelfde codebase later zowel lokaal als op een Linux/Docker-server worden ingezet zonder een volledige herarchitectuur.
