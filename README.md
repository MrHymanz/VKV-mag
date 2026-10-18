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

## Backend installeren op een Linux-server

De backend levert ook de webinterface: gebruikers openen de server in hun browser.
De Windows-`.exe` is voor zelfstandig lokaal gebruik en hoeft niet op de server
of op de computers van deze gebruikers te worden geïnstalleerd.

### Installeren met Docker Compose

Vereist: Git, Docker Engine met de Compose-plugin en een Linux-server met voldoende
ruimte voor de containerimages en documenten. Reserveer als startpunt 2 GB RAM;
grote PDF’s en meerdere gebruikers kunnen meer nodig hebben. Voer de opdrachten
uit als gebruiker die Docker mag gebruiken, vanuit de projectmap.

1. Clone deze repository met de clone-URL van uw Git-server. De grote Windows-installer
   is voor de backend niet nodig:

   ```bash
   GIT_LFS_SKIP_SMUDGE=1 git clone <clone-URL> VKV-mag
   cd VKV-mag
   ```

2. Maak de opslagmappen aan en stel de containergebruiker in op de eigenaar ervan:

   ```bash
   mkdir -p storage/uploads storage/temporary storage/fonts
   cp .env.example .env
   printf '\nVKV_UID=%s\nVKV_GID=%s\n' "$(id -u)" "$(id -g)" >> .env
   ```

   Bij een bestaande installatie: behoud uw `.env` en controleer dat deze gebruiker
   in alle drie de mappen kan schrijven. Gebruik geen algemene `chmod 777`.

3. Start de backend en de meegeleverde LanguageTool-dienst:

   ```bash
   docker compose -f docker-compose.backend.yml up -d --build
   docker compose -f docker-compose.backend.yml ps
   docker compose -f docker-compose.backend.yml logs --tail=100
   ```

   De eerste start downloadt images en Python-afhankelijkheden. Wacht tot
   LanguageTool klaar is; tijdens het laden kan een upload nog een 503 geven.
   LanguageTool is alleen binnen het Docker-netwerk bereikbaar.

4. Open `http://<server-IP>:8765`. Controleer een klein TXT-bestand met een
   spelfout en download de correctie. Controleer daarna ook een eigen DOCX/PDF.
   Een eenvoudige bereikbaarheidscontrole op de server is:

   ```bash
   curl --fail http://127.0.0.1:8765/ > /dev/null
   ```

Deze opdrachten gebruiken bewust `docker-compose.backend.yml`. De bestaande
`docker-compose.yml` is voor de huidige server met een afzonderlijke
LanguageTool op hostpoort 8010. Start beide configuraties niet tegelijk op poort
8765. De backendvariant heeft geen vaste containernamen.

### Configuratie en bereikbaarheid

Compose leest `.env` in de projectmap. De backendconfiguratie ondersteunt:

| Variabele | Standaard | Doel |
| --- | --- | --- |
| `VKV_UID`, `VKV_GID` | `1000` | Eigenaar met schrijfrechten op `storage` |
| `VKV_BIND_ADDRESS` | `0.0.0.0` | Luisteradres op de host |
| `VKV_PORT` | `8765` | Poort op de host |
| `DEFAULT_LANGUAGE` | `nl-NL` | Taal van de controle |
| `MAX_UPLOAD_MB` | `25` | Maximale documentgrootte |
| `LANGUAGETOOL_TIMEOUT_SECONDS` | `60` | Wachttijd voor spellingcontrole |
| `LOG_LEVEL` | `INFO` | Logniveau |

De LanguageTool-URL en opslagpaden worden in deze Compose-configuratie ingesteld
op de interne dienst en het gekoppelde storage-volume. `APP_PORT` in `.env`
verandert de Uvicorn-poort niet; gebruik `VKV_PORT` voor de hostpoort.
De app leest een `.env` niet zelf in bij een start buiten Compose.

De app heeft nog geen ingebouwde login. Gebruik haar op een vertrouwd intern
netwerk, via VPN of achter een reverse proxy met authenticatie en HTTPS.
Voor een reverse proxy op dezelfde host zet u `VKV_BIND_ADDRESS=127.0.0.1` in
`.env`; stuur verkeer door naar `http://127.0.0.1:8765`. Sta in de proxy uploads
van minstens 25 MB en voldoende verwerkingstijd toe (bijvoorbeeld 120 seconden).
Publiceer de LanguageTool-poort niet.

### Beheer, updates en gegevens

```bash
# Logs bekijken
docker compose -f docker-compose.backend.yml logs -f --tail=100

# Applicatie bijwerken vanuit Git en opnieuw bouwen
GIT_LFS_SKIP_SMUDGE=1 git pull --ff-only
docker compose -f docker-compose.backend.yml up -d --build

# Stoppen
docker compose -f docker-compose.backend.yml down
```

De map `storage` blijft buiten de containers bewaard. Plaats redactiefonts
in `storage/fonts`; maak van deze map inclusief JSON-koppelingen een back-up.
**Bij netjes stoppen of herstarten verwijdert de app uploads en tijdelijke
bestanden.** Laat gebruikers hun resultaat vooraf downloaden. Goedkeuringen
staan in het werkgeheugen; maak lopende controles na een herstart opnieuw.
`TEMP_FILE_TTL_MINUTES` voert momenteel geen periodieke opruiming uit.

Bij een 503: bekijk de LanguageTool-logs en wacht tot de dienst geladen is.
Bij `Permission denied`: controleer `VKV_UID`, `VKV_GID` en de eigenaar van
`storage`. Bij een poortconflict: kies bijvoorbeeld `VKV_PORT=8767` in `.env`
en voer de startopdracht opnieuw uit. Voor reproduceerbare releases kunt u de
LanguageTool-image in de Compose-configuratie op een geteste digest vastzetten;
`latest` kan bij een volgende pull wijzigen.

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
- of de Docker-container uit `docker-compose.backend.yml`

De backend communiceert alleen met `LANGUAGETOOL_URL`, bij een directe Python-start standaard `http://127.0.0.1:8010`.

### 3. DOCX-behoud van opmaak

Voor DOCX gebruiken we `python-docx` en werken we op run-/paragraph-niveau in plaats van de volledige paragraaf opnieuw te reconstrueren. Dat minimaliseert het risico op verlies van vet, cursief, koppen en lijsten.

### 4. Deployment zonder WSL als verplichte eis

Voor Windows is het doel een native installatiemethode zonder dat de eindgebruiker Python, Java of WSL handmatig hoeft te installeren. De server-variant gebruikt Docker, en de Windows-installer bundelt Python, Java en LanguageTool met een NSIS-launcher.

## Projectstructuur

```text
VKV-mag/
├── app/                       # FastAPI, parsers, diensten en webinterface
├── docs/                      # Architectuur
├── installer/                 # Windows-launcher, bouwscript en dist/*.exe
├── storage/
│   ├── fonts/                 # Redactiefonts en fontkoppelingen
│   ├── temporary/             # Tijdelijke uitvoer
│   └── uploads/               # Geüploade documenten
├── tests/
├── Dockerfile
├── docker-compose.yml         # Bestaande server met externe LanguageTool
├── docker-compose.backend.yml # Zelfstandige backend plus LanguageTool
├── .env.example
├── requirements.txt
└── README.md
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

De app verwacht een lokaal draaiende LanguageTool-instantie op de configuratie-URL, bij een directe Python-start standaard `http://127.0.0.1:8010`.

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

## Dubbele spaties in DOCX

DOCX-bestanden worden in alle gevoeligheidsstanden ook op dubbele of meervoudige
gewone spaties tussen woorden gecontroleerd. Deze voorstellen staan standaard
uit; vink ze aan om de reeks door één spatie te vervangen. Tabs, inspringing,
regelafbrekingen en vaste spaties vallen buiten deze extra controle. Deze
controle is niet toegevoegd aan PDF- of TXT-bestanden.

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
- Uploads en tijdelijke bestanden worden bij netjes afsluiten lokaal verwijderd
- Uploads worden niet gelogd met volledige documentinhoud

## Belangrijk

Het project is bewust ontworpen als een server-side backend met een modulair documentframework. Daardoor kan dezelfde codebase later zowel lokaal als op een Linux/Docker-server worden ingezet zonder een volledige herarchitectuur.
