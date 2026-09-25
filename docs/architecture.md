# Architectuurdocument – VKV Documentcontrole

## 1. Doel en context

De VKV-documentcontrole moet redacteuren helpen bij het vinden en verwerken van taalfouten in nieuwsartikelen, verenigingsteksten en documenten zonder gebruik te maken van commerciële LLM-API's. De applicatie moet zodanig worden gebouwd dat zij zowel lokaal op een Windows-machine als op een server met Docker kan draaien. De kerncomponenten zijn in alle gevallen hetzelfde: documentparsing, LanguageTool-client, correctiemodule en webinterface.

## 2. Architectuurprincipe

We kiezen voor een server-first, modulair monolithische app:

- backend: FastAPI
- frontend: HTML/CSS/vanilla JavaScript
- storage: lokaal bestandssysteem
- documentverwerking: TXT/DOCX parsers
- spellingscontrole: lokale LanguageTool-instance

Dit is bewust geen cloud-applicatie en geen direct afhankelijkheid van een specifiek OS of deploymentmodel.

## 3. Componenten

### 3.1 Webinterface

De frontend is eenvoudig, overzichtelijk en geschikt voor niet-technische gebruikers. Bij startup toont de app een startpagina met uploadvlak, mogelijkheid om bestandsnaam te kiezen en een knop voor controle. De editor laat tekst en problemen in twee panelen zien.

### 3.2 API-backend

Het backend is verantwoordelijk voor:

- valideren van uploads
- opslag in tijdelijke map
- extractie van tekst per bestandstype
- communicatie met LanguageTool
- verzamelen van suggesties en fouttypen
- voorbereiden van gecorrigeerde uitvoer
- downloaden van het aangepaste document

### 3.3 Parserlaag

Parser-interfaces abstraheren de bestandsoorten. Dat maakt latere uitbreiding voor PDF of ODT eenvoudiger zonder de rest van de app te wijzigen.

### 3.4 LanguageTool-integration

LanguageTool draait lokaal, niet in de cloud. De app vraagt een lokale `POST /v2/check`-endpoint op via HTTP. Dat maakt het mogelijk om dezelfde app te laten draaien in een bekende bedrijfs- of serveromgeving zonder dat documenten de organisatie verlaten.

### 3.5 Correctiemodule

De correctiemodule vertaalt een LanguageTool-fout naar een tekstwijziging of een DOCX-run-aanpassing. Voor DOCX wordt alleen de relevante run of het relevante tekstfragment aangepast. De rest van de documentstijlen, koppen en tabellen blijven intact.

## 4. Deploymentmodellen

### Scenario A: Windows-laptop

- native Python-runtime
- minimale bundeling van Python inclusief backend
- LanguageTool als lokaal Java-process of ingebouwde Java runtime
- browser opent automatisch naar localhost
- startmenu-item voor de app

### Scenario B: server / Docker

- backend in een Docker-container
- LanguageTool in een tweede container of in een lokale service
- Nginx/Traefik/reverse proxy als nodig
- integratie via subdomein of subpad mogelijk

## 5. Security en privacy

- Geen externe API's
- Geen analytics of telemetrie zonder configuratie
- Tijdsgebonden tijdelijke bestanden
- Uploadgrootte beperkt via configuratie
- UUID-gebaseerde bestandsnamen
- Validatie van bestandstype en uploadgrootte
- Geen volledige documentinhoud in logs

## 6. DOCX-strategie

DOCX wordt verwerkt met `python-docx`. De kern van de aanpak is:

- alle paragraven en runs worden doorlopen
- opmerkingen/fouten worden per tekstfragment gekoppeld
- alleen het betwiste text segment wordt vervangen
- stijlvelden zoals bold, italic, list-level en hyperlinks blijven behouden

Als een fout precies in een run valt, dan wordt alleen die run aangepast. Als een fout over meerdere runs heen loopt, dan wordt het fragment in de paragraaf gecontroleerd en zo goed mogelijk vervangen zonder de rest van de paragraaf te vernietigen.

## 7. LanguageTool-localisatie

We ondersteunen de Nederlandse taaloptie en de VKV-woordenlijst als configurabele whitelist. De woordenlijst is een tekstbestand dat kan worden uitgebreid zonder de codebase te wijzigen.

## 8. Implementatieplan

### Fase 1

- FastAPI-service
- eenvoudige HTML-interface
- TXT- en DOCX-upload
- tekstextractie
- lokale LanguageTool-call
- foutresultaten en suggesties
- voorbeeldcorrecties toepassen en downloaden

### Fase 2

- betere DOCX-formatting-verwerking
- editor met markeringen en selectiviteit
- VKV-woordenlijst
- categorisatie van fouten
- styling in VKV-voorkeuren

### Fase 3

- native Windows packaging
- auto-browser-open
- bundeling van LanguageTool/Java
- installer voor eindgebruiker

### Fase 4

- Docker/deployment en serverintegratie
- reverse proxy-ondersteuning
- toekomstige login-integratie met VKV-leden-/beheerdersomgeving

## 9. Belangrijkste uitvoerbaarheid

Het project is ontworpen om de deploymentlaag te scheiden van de kernlogica. Daardoor kan eenzelfde codebase zowel op een beheerderlaptop als op de server draaien zonder dat de documentverwerking of de spellingscontrole anders werkt.
