# Edge IE Compatibility Mode Manager

---

## Overview

Edge IE Compatibility Mode Manager is a desktop GUI tool that automates the configuration of **Microsoft Edge's IE compatibility mode** (also known as "IE mode"). It allows you to manage a list of IP addresses or domain names that should automatically open in IE mode within Edge, without requiring manual registry edits or XML file creation.

### What is Edge IE Mode?

Microsoft Edge (Chromium-based) includes an **IE mode** that renders specific websites using the legacy Trident (MSHTML) engine — the same engine used by Internet Explorer 11. This is essential for organizations that rely on legacy web applications designed for older versions of Internet Explorer.

IE mode is configured through:

1. **An Enterprise Mode Site List XML** — a structured XML file declaring which URLs should use IE mode, what compatibility level to apply (`Default`, `IE8Enterprise`, `IE7Enterprise`, `IE11`), and optional expiry dates.
2. **Two Windows Registry values** under `SOFTWARE\Policies\Microsoft\Edge`:
   - `InternetExplorerIntegrationLevel` — set to `1` to enable IE mode
   - `InternetExplorerIntegrationSiteList` — points to the XML file via a `file://` URL

This tool handles **both steps** through a simple graphical interface.

---

## Features

| Feature | Description |
|---------|-------------|
| **Site Management** | Add, delete, import, and export IP addresses / domain names |
| **XML Generation** | Automatically generates a valid Enterprise Mode Site List v2 XML |
| **Registry Configuration** | Writes the required registry keys (HKLM or HKCU) in one click |
| **Auto-Import on Launch** | Detects and imports existing IE mode sites from your current Edge configuration |
| **Expiry Tracking** | Shows color-coded remaining validity days for each site (green > 30d, amber 7-30d, red < 7d) |
| **One-Click Extension** | Extends all expiry dates at once to prevent IE mode from expiring |
| **Edge Reload** | Force-restarts Edge processes so changes take effect immediately |
| **Auto Elevation** | Automatically requests administrator privileges via UAC on launch |
| **No Dependencies** | The bundled `.exe` requires nothing — no Python, no pip install |

---

## Screenshots & Layout

```
┌─────────────────────────────────────────────────────┐
│  Edge IE Compatibility Mode Manager          [blue] │
├─────────────────────────────────────────────────────┤
│ Sites │ Settings                                    │
├──────────────────────────────────────────┬──────────┤
│ New Site: [________] Mode: [Default▼]    │ Actions  │
│ [+Add] [Import] [Export] [From XML]      │ ┌──────┐ │
│                                          ││Generate│ │
│ ┌────────────────────────┬───────────────┤│& Apply │ │
│ │Site URL   │Compat Mode │Expires In    │└──────┘ │
│ ├────────────────────────┼───────────────┤┌──────┐ │
│ │192.168.1.100 │ Default │ 85 days     ││Extend │ │
│ │10.0.0.50     │ IE11    │ 12 days     ││Validity│ │
│ │app.example.com│Default │ -           │└──────┘ │
│ └────────────────────────┴───────────────┤┌──────┐ │
│                                          ││Reload │ │
│                                          ││ Edge  │ │
│                                          ├──┤└──────┘ │
│                                          │ Manage   │
│                                          │ ┌──────┐ │
│                                          │ │Delete │ │
│                                          │ │Selected│ │
│                                          │ └──────┘ │
│ 5 sites | Config: C:\Users\xxx\...       └──────────┘
│                        Last action: 06-08 14:30     │
└─────────────────────────────────────────────────────┘
```

---

## Getting Started

### Option A: Run from Executable (Recommended)

1. Double-click `Edge_IE_Compatibility_Manager.exe`
2. Accept the UAC prompt (administrator privileges are required)
3. The application window opens — ready to use

> **Note:** On first run, Windows Defender SmartScreen may show a warning because this is an unsigned executable. Click **"More info" → "Run anyway"** to proceed.

### Option B: Run from Source Code

**Prerequisites:**
- Python 3.8 or higher
- Windows 10/11 (for `winreg` and `ctypes` support)

```bash
pip install tk   # Usually included with Python on Windows
python edge_ie_manager.py
```

---

## Usage Guide

### Step 1: Add Sites

There are four ways to add sites to the list:

1. **Manual entry** — Type an IP or domain in the "New Site" field, optionally select a compat mode, then click **+ Add** (or press Enter)
2. **Text file import** — Click **Import**, select a `.txt` file with one URL per line
3. **XML import** — Click **From XML** to load sites from an existing Enterprise Mode Site List XML
4. **Auto-import** — On startup, the tool automatically detects any existing IE mode configuration in Edge and imports those sites

**Supported URL formats:**
- IP addresses: `192.168.1.1`, `10.0.0.50`
- Domains: `app.example.com`, `intranet.local`
- With or without protocol: `https://192.168.1.1`, `http://app.example.com`
- All protocols and trailing slashes are stripped automatically

### Step 2: Configure Settings

Go to the **Settings** tab to customize:

| Setting | Description | Default |
|---------|-------------|---------|
| **XML File Path** | Where the generated site-list XML will be saved | `%USERPROFILE%\edge_ie_sitelist.xml` |
| **Expiry Extension Days** | Number of days from today when generating/extending expiry dates (max **1000**) | 360 |
| **Registry Scope** | `HKLM` = all users on this machine; `HKCU` = current user only | HKLM |

Click **Save Settings** after making changes.

### Step 3: Apply Configuration

Click **Generate XML & Apply** in the right-side action panel. This:
1. Creates the Enterprise Mode Site List XML file with all your sites
2. Writes/updates the Windows Registry to enable IE mode and point Edge to your XML
3. Shows a confirmation dialog with the XML path and expiry date

### Step 4: Restart Edge

After applying, restart Microsoft Edge (or click **Reload Edge**) for the new settings to take effect.

**Verification:** In Edge, navigate to `edge://compat/` — you should see your site list loaded under "Enterprise Site List".

### Extending Validity

Each site entry has an expiry date. When the date passes, Edge stops forcing IE mode for that site.

- To extend manually: Click **Extend Validity** — this pushes all `<expires>` dates forward by the configured number of days
- To automate: Use the bundled `auto_extend.py` script with Windows Task Scheduler

**Color-coded badges in the table show urgency:**

| Color | Meaning | Action Needed |
|-------|---------|---------------|
| 🟢 Green | > 30 days remaining | No action needed |
| 🟡 Amber | 7 – 30 days remaining | Plan to extend soon |
| 🔴 Red | < 7 days remaining | Extend immediately |
| ⚪ Gray `-` | No data (XML not yet generated) | Generate XML first |

---

## File Structure

```
edge-ie-tool/
├── edge_ie_manager.py              # Main application source code (Python/Tkinter)
├── Edge_IE_Compatibility_Manager.exe # Bundled standalone executable (no Python needed)
├── auto_extend.py                  # Headless script for scheduled auto-extension
├── create_scheduled_task.bat        # One-click setup for monthly auto-extension task
├── config.json                     # Auto-generated user preferences (after first run)
├── edge_ie_sitelist.xml            # Auto-generated Enterprise Mode Site List (after "Apply")
└── README.md                       # This documentation file
```

---

## Technical Details

### Generated XML Schema

The tool generates XML conforming to Microsoft's **Enterprise Mode Site List v2** schema:

```xml
<site-list version="2">
  <created-by>
    <tool>Edge IE Manager</tool>
    <version>2.0</version>
    <date-created>2026-06-08</date-created>
  </created-by>
  <site url="192.168.1.100">
    <open-in>IE11</open-in>
    <compat-mode>Default</compat-mode>
    <expires>2026-09-06</expires>
  </site>
</site-list>
```

### Registry Values Written

| Hive | Key | Value Name | Type | Value |
|------|-----|------------|------|-------|
| `HKLM` or `HKCU` | `SOFTWARE\Policies\Microsoft\Edge` | `InternetExplorerIntegrationLevel` | REG_DWORD | `1` |
| `HKLM` or `HKCU` | `SOFTWARE\Policies\Microsoft\Edge` | `InternetExplorerIntegrationSiteList` | REG_SZ | `file:///C:/Users/You/edge_ie_sitelist.xml` |

### Compatibility Modes

When adding a site, you can choose one of these compatibility modes:

| Mode | Behavior |
|------|----------|
| **Default** | Edge decides the best emulation (recommended for most cases) |
| **IE8Enterprise** | Emulates Internet Explorer 8 Standards Mode |
| **IE7Enterprise** | Emulates Internet Explorer 7 Standards Mode |
| **IE11** | Emulates Internet Explorer 11 Standards Mode |

---

## Automation: Scheduled Expiry Extension

For long-running deployments, you can set up automatic expiry extension using the bundled helper scripts.

### Using auto_extend.py

```bash
# Run manually (headless, no GUI):
python auto_extend.py

# Expected output:
# [2026-06-08 14:30:00] Extended 5 records. New expiry: 2026-09-06
```

This script reads the last-known XML path from `config.json`, extends all `<expires>` dates, and logs results to `auto_extend.log`.

### Creating a Windows Scheduled Task

Double-click **`create_scheduled_task.bat`** to register a monthly task that runs on the 1st of every month at 09:00 AM. Or manually create it:

```powershell
schtasks /create /tn "EdgeIEExtendExpiry" /tr "pythonw.exe auto_extend.py" /sc monthly /d 1 /st 09:00 /rl HIGHEST
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **UAC prompt appears on every launch** | This is normal and required for registry writes to HKLM |
| **Sites don't open in IE mode after applying** | Fully close and restart Edge (not just refresh the tab) |
| **`edge://compat/` shows no site list** | Check that the XML path in registry is accessible; verify the XML is valid |
| **"Permission denied" error** | Make sure you're running as administrator (the tool auto-elevates) |
| **Expiry dates already passed** | Click "Extend Validity" to push dates forward |
| **Config not saving** | Check write permissions on the exe directory; if read-only, config goes to `%APPDATA%\EdgeIEManager\` |
| **"Exceeds maximum of 1000 days" warning** | The expiry days field has a hard limit of 1000. Adjust the value in Settings ≤ 1000 and try again |

---

## Building the Executable

If you need to rebuild the `.exe` from source:

```bash
# Install PyInstaller (one-time setup)
pip install pyinstaller

# Build single-file exe (no console window)
pyinstaller --onefile --noconsole --name "Edge_IE_Compatibility_Manager" edge_ie_manager.py

# Output: dist/Edge_IE_Compatibility_Manager.exe
```

Clean up build artifacts afterwards:
```bash
rm -rf build/ *.spec __pycache__/
```

---




