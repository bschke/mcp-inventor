# inventor-mcp

MCP-Server, mit dem Claude (oder ein anderer MCP-Client) ein laufendes **Autodesk Inventor** unter Windows steuert: Dokumente öffnen und exportieren, Parameter und iProperties lesen und setzen, einfache Teile modellieren, Baugruppen bestücken und Screenshots der Ansicht holen.

Der Server spricht Inventor über die COM-API an (`Inventor.Application`, via pywin32). Er muss deshalb **auf demselben Windows-Rechner laufen wie Inventor**.

## Voraussetzungen

- Windows 10/11 mit installiertem Autodesk Inventor (die COM-API ist in jeder Vollversion enthalten, ein Add-in ist nicht nötig)
- Python 3.10 oder neuer ([python.org](https://www.python.org/downloads/windows/), beim Setup „Add python.exe to PATH“ anhaken)
- Claude Desktop oder ein anderer MCP-Client

## Installation

In PowerShell:

```powershell
git clone https://github.com/bschke/mcp-inventor.git C:\Tools\mcp-inventor
cd C:\Tools\mcp-inventor
python -m venv .venv
.venv\Scripts\pip install -e .
```

### Claude Desktop einrichten

`%APPDATA%\Claude\claude_desktop_config.json` öffnen (in Claude Desktop: Einstellungen → Entwickler → Konfiguration bearbeiten) und ergänzen:

```json
{
  "mcpServers": {
    "inventor": {
      "command": "C:\\Tools\\mcp-inventor\\.venv\\Scripts\\inventor-mcp.exe",
      "env": {
        "INVENTOR_MCP_ALLOW_SCRIPTS": "0"
      }
    }
  }
}
```

Claude Desktop danach komplett beenden (auch im Infobereich) und neu starten.

### Claude Code

```powershell
claude mcp add inventor -- C:\Tools\mcp-inventor\.venv\Scripts\inventor-mcp.exe
```

## Tools

| Tool | Zweck |
|---|---|
| `get_status`, `list_documents` | Version, aktives Dokument, offene Dateien |
| `open_document`, `new_document`, `save_document`, `close_document` | Dateiverwaltung (`.ipt`, `.iam`, `.idw`, `.dwg`) |
| `export_document` | Kopie als STEP, IGES, STL, SAT, OBJ, JT, bei Zeichnungen PDF, DWG, DXF |
| `get_parameters`, `set_parameters` | Benutzer- und Modellparameter lesen/ändern, neue anlegen |
| `get_iproperties`, `set_iproperties` | Bauteilnummer, Beschreibung, benutzerdefinierte Eigenschaften |
| `create_extrusion` | Rechteck, Kreis oder Polygon auf XY/XZ/YZ skizzieren und extrudieren (Vereinigung, Differenz, Schnitt, neuer Körper) |
| `list_features`, `set_feature_suppressed` | Features auflisten, unterdrücken |
| `get_mass_properties` | Masse, Volumen, Oberfläche, Schwerpunkt |
| `list_occurrences`, `add_occurrence` | Baugruppenkomponenten auflisten und platzieren |
| `capture_view` | PNG der aktiven Ansicht, damit Claude das Ergebnis sieht |
| `run_script` | nur mit `INVENTOR_MCP_ALLOW_SCRIPTS=1`, siehe unten |

Alle Längen sind Millimeter. Intern rechnet die Inventor-API in Zentimetern und Radiant; die Umrechnung übernimmt der Server.

Beispiel-Prompts:

- „Leg ein neues Teil an: Platte 100 × 60 × 8 mm, mittig eine Bohrung Ø 12 durch. Zeig mir das Ergebnis.“
- „Setz in Halter.ipt den Parameter `Laenge` auf 140 mm und exportier das Teil als STEP nach C:\Export.“
- „Trag in allen offenen Teilen den Lieferanten ‚ACME‘ als iProperty ein.“

## Konfiguration

| Variable | Standard | Wirkung |
|---|---|---|
| `INVENTOR_MCP_LAUNCH` | `1` | Inventor starten, wenn keine Instanz läuft. `0` = nur an laufende Instanz andocken |
| `INVENTOR_MCP_ALLOW_SCRIPTS` | `0` | `1` schaltet `run_script` frei |

### `run_script`

Damit führt Claude beliebigen Python-Code gegen die Inventor-API aus (`app`, `doc`, `tg` sind vorbelegt). Das deckt alles ab, wofür es kein eigenes Tool gibt: Abhängigkeiten, Rundungen, Zeichnungsansichten, Stücklisten. Der Code läuft mit deinen Benutzerrechten und kann auch außerhalb von Inventor Dateien löschen. Schalte es nur ein, wenn du die Aufrufe in Claude bestätigst und nicht pauschal freigibst.

## Grenzen

- Kein Undo über den Server. Vor Experimenten speichern.
- `create_extrusion` erzeugt Skizzen ohne Bemaßungen; die Geometrie ist fest, nicht parametrisch.
- Inventor zeigt bei manchen Aktionen modale Dialoge (z. B. fehlende Referenzen beim Öffnen). Dann blockiert der Aufruf, bis der Dialog in Inventor geschlossen wird. `app.SilentOperation = True` per `run_script` unterdrückt die meisten.
- Getestet ist die Logik mit nachgebauten COM-Objekten (`tests/`). Gegen eine echte Inventor-Installation wurde dieser Stand noch nicht geprüft.

## Entwicklung

```powershell
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

Die Tests laufen auch unter Linux/macOS, weil sie Inventor durch Fakes ersetzen. Aufbau: `com.py` hält die COM-Verbindung auf einem eigenen Thread (COM-Objekte dürfen den Thread nicht wechseln), `ops.py` enthält die Inventor-Logik, `server.py` die MCP-Tools.
