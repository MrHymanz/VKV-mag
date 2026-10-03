# Windows-installatiepakket

## Installeren en gebruiken

1. Gebruik een Windows 10/11-computer met een 64-bit Intel- of AMD-processor.
2. Download [VKV-Documentcontrole-Setup.exe](dist/VKV-Documentcontrole-Setup.exe)
   via de downloadknop op GitHub. Het pakket is ongeveer
   361 MB; de uitgepakte installatie neemt ongeveer 700 MB in beslag.
3. Start het bestand en kies de installatiemap. Standaard installeert het voor de
   huidige gebruiker onder `%LOCALAPPDATA%\Programs\VKV Documentcontrole`.
4. Start **VKV Documentcontrole** via het bureaublad of het startmenu. Wacht totdat
   de browser opent; tijdens de eerste start moet LanguageTool worden geladen.
5. Upload en controleer een document. Download het resultaat voordat u afsluit.
6. Druk op **Enter** in het startvenster om de app en spellingcontrole te stoppen.

De installer is niet digitaal ondertekend. Windows kan daarom een melding over
een onbekende uitgever tonen. Gebruik alleen het bestand dat u van de beheerder
hebt ontvangen; deze levert ook een `.sha256`-bestand voor integriteitscontrole.
Het installatiebestand wordt via **Git LFS** bijgehouden, omdat het groter is
dan GitHubs limiet van 100 MiB voor gewone Git-bestanden. Zie de
[GitHub-documentatie](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
Na een clone haalt u het volledige bestand op met:

```bash
git lfs install
git lfs pull
```

Hiervoor moet Git LFS geïnstalleerd zijn. Alleen een klein tekstbestand in plaats
van de `.exe` betekent dat u de LFS-pointer hebt en het echte bestand nog moet
ophalen. De `.sha256` staat naast de installer. Tijdelijke buildbestanden blijven
buiten Git. Een push moet zowel de Git-commit als het LFS-object uploaden.

## Gegevens, updates en problemen

- Geen browser geopend? Open het lokale adres dat in het startvenster staat.
- Startproblemen? Bekijk `%LOCALAPPDATA%\VKV-mag\data\languagetool.log` en de
  melding in het startvenster.
- Ontbrekende lettertypen kunnen via de webinterface worden toegevoegd.
- Sluit de app voor een update en start vervolgens het nieuwe installatiebestand.
- Verwijderen kan via Windows' geïnstalleerde apps of `Verwijderen.exe` in de
  installatiemap. De gegevensmap en toegevoegde fonts blijven behouden.

De ontvanger start `VKV-Documentcontrole-Setup.exe` en vervolgens de
snelkoppeling. Het pakket bevat Python 3.13 x64, Java 21, de LanguageTool-versie
uit de lokale servercontainer en Windows-wheels voor alle app-afhankelijkheden.
De browser en beide servers draaien lokaal. Er is geen serververbinding nodig.

Gebruikersdata staat in `%LOCALAPPDATA%\VKV-mag\data`, los van de installatie.
Uploads en gegenereerde PDF's van de buildserver worden niet meegeleverd.
De fonts uit `storage/fonts` worden wel meegenomen. Sluit de app voor upgrades.

## Build op deze Linux-server

Vereist: de projectvenv (met pip en httpx), Docker, de bestaande
`languagetool-vkv`-container en NSIS. In deze buildomgeving staan `makensis` en
de bijbehorende NSIS-resources onder `installer/build/`.

```bash
.venv/bin/python installer/build_windows.py
```

Uitvoer: `installer/dist/VKV-Documentcontrole-Setup.exe`.
Het meegeleverde `build-manifest.json` registreert downloads, checksums,
Windows-wheels en de gebruikte LanguageTool-containerimage.
NSIS-bronnen: `launcher.nsi` en `setup.nsi`; lokale startcode: `desktop.py`.

Java wordt via de officiële [Adoptium-API](https://api.adoptium.net/) opgehaald;
de download wordt tegen de gepubliceerde SHA-256 gecontroleerd. Python komt
van [python.org](https://www.python.org/downloads/release/python-3137/).
LanguageTool wordt gestart volgens de
[HTTP-serverdocumentatie](https://dev.languagetool.org/http-server).

Deze build is niet digitaal ondertekend. Een proef op een echte Windows 10/11-pc
blijft nodig; tests op Linux/Wine vervangen die proef niet.

Gecontroleerd bij deze build: 69 app-tests, installatie en snelkoppeling onder
Wine 10, Windows-Python-imports, Java-start en de volledige upload/spelling/
TXT-download/PDF-vergelijking/PDF-download-keten, ook vanuit de geïnstalleerde
map met spaties. `smoke_windows.py` voert die ketentest uit met de gebundelde
Windows-Python.
