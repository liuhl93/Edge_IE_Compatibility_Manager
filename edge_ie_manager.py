#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  Edge IE Compatibility Mode Manager
=============================================================================

  Version      : 2.0
  Description  : A GUI tool for managing Microsoft Edge IE compatibility
                 mode site lists on Windows.
  Author       : Auto-generated
  License     : MIT

-----------------------------------------------------------------------------
  Features
-----------------------------------------------------------------------------

  - Add / remove IP addresses or domain names to an Enterprise Mode Site List.
  - Generate a valid Edge Enterprise Mode Site List XML (version 2 schema).
  - Write the required registry keys so Edge loads the site list and forces
    IE mode for listed URLs.
  - Auto-detect and import existing IE mode sites from the current Edge config.
  - Display remaining validity days for each site with color-coded badges.
  - Extend all expiry dates in one click (or via scheduled task).
  - Reload Edge browser to pick up changes without a full reboot.

-----------------------------------------------------------------------------
  Technical Background
-----------------------------------------------------------------------------

  Microsoft Edge supports "IE mode" which renders specific sites using the
  Trident (MSHTML) engine — just like legacy Internet Explorer 11. To enable
  this, two things are needed:

    1. A valid "Enterprise Mode Site List" XML file that declares which URLs
       should open in IE mode and what compatibility level to use.
    2. Two registry values under
         HKLM/HKCU\\SOFTWARE\\Policies\\Microsoft\\Edge :
           - InternetExplorerIntegrationLevel   = 1 (DWORD)
             (1 = IE mode enabled)
           - InternetExplorerIntegrationSiteList = <file URL> (SZ)
             Points to the XML file, e.g.
             "file:///C:/Users/You/edge_ie_sitelist.xml"

  This tool automates both steps through a user-friendly tkinter GUI.

-----------------------------------------------------------------------------
  Requirements
-----------------------------------------------------------------------------

  - Windows 10 / 11 (x64)
  - Python 3.8+ (for source execution) OR the bundled .exe (no Python needed)
  - Administrator privileges (auto-elevated at launch)

-----------------------------------------------------------------------------
  Usage
-----------------------------------------------------------------------------

  As source:
    $ python edge_ie_manager.py

  As executable:
    Double-click Edge_IE_Compatibility_Manager.exe

=============================================================================
"""

# ═══════════════════════════════════════════════════════════════════════
# Standard Library Imports
# ═══════════════════════════════════════════════════════════════════════

import os               # File path operations, directory checks
import sys              # System-specific parameters (argv, platform, frozen flag)
import json             # Reading/writing JSON configuration files
import re               # Regular expressions for URL cleaning
import datetime         # Date arithmetic for expiry calculations
import subprocess       # Spawning external processes (e.g., killing Edge)
import ctypes           # Windows API calls for UAC elevation check
import xml.etree.ElementTree as ET  # Building/parsing the site-list XML
from xml.dom import minidom            # Pretty-printing XML output
import winreg           # Windows Registry read/write operations

# Tkinter – the standard Python GUI toolkit shipped with Python on Windows
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


# ═══════════════════════════════════════════════════════════════════════
# Section 1: Constants & Path Resolution
# ═══════════════════════════════════════════════════════════════════════

def _get_base_dir():
    """Determine the base directory for persistent data files.

    When running as a normal Python script (__file__ is reliable), we use
    the directory where the script lives. When bundled by PyInstaller into a
    single .exe, __file__ points inside a temporary extraction folder that
    gets deleted after the process exits — so we fall back to the directory
    containing the exe itself (sys.executable), or AppData if that location
    is not writable.

    Returns:
        str: Absolute path to a writable directory for storing config.json.
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle detected — use the exe's parent directory
        d = os.path.dirname(sys.executable)
        # Some locations like Program Files are read-only; use AppData instead
        if not os.access(d, os.W_OK):
            d = os.path.join(
                os.environ.get('APPDATA', os.path.expanduser('~')),
                'EdgeIEManager'
            )
            os.makedirs(d, exist_ok=True)
        return d
    # Normal script execution — script's own directory
    return os.path.dirname(os.path.abspath(__file__))


# Resolve the base directory once at module import time
BASE_DIR = _get_base_dir()

# Default path where the generated Enterprise Mode Site List XML will be saved.
# Users can change this in the Settings tab.
DEFAULT_XML_PATH = os.path.join(
    os.path.expanduser("~"),          # e.g., C:\Users\<username>
    "edge_ie_sitelist.xml"
)

# ── Windows Registry Constants ──────────────────────────────────────────

# The registry key path where Edge reads its policy settings.
# Both HKLM (machine-wide) and HKCU (per-user) are supported.
REG_PATH = r"SOFTWARE\Policies\Microsoft\Edge"

# Registry hive handles
HIVE_MACHINE = winreg.HKEY_LOCAL_MACHINE  # HKLM — affects all users
HIVE_USER    = winreg.HKEY_CURRENT_USER   # HKCU — affects current user only

# Registry value names that control IE integration:
#   - SITELIST: file:// URL pointing to the XML
#   - IE_MODE : DWORD; 1 = enable IE mode
REG_VAL_SITELIST = "InternetExplorerIntegrationSiteList"
REG_VAL_IE_MODE  = "InternetExplorerIntegrationLevel"

# Path to the JSON file that stores user preferences (sites, paths, etc.)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


# ── UI Color Palette ───────────────────────────────────────────────────

# All colors used throughout the UI. Keeping them centralized makes theme
# changes easy and ensures consistency.
C_BLUE        = "#1A56DB"    # Primary action buttons (Add, Apply)
C_RED         = "#E53E3E"    # Destructive actions (Delete)
C_GREEN       = "#22C55E"    # Success/import actions
C_AMBER       = "#D97706"    # Warning/extend actions
C_GRAY        = "#4A5568"    # Secondary actions (Reload)
C_GRAY_LIGHT  = "#F1F5F9"    # Main background color
C_TOOLBAR     = "#EEF2F7"    # Toolbar row background
C_STATUS_BG   = "#EDF2F7"    # Status bar background


# ═══════════════════════════════════════════════════════════════════════
# Section 2: Configuration Persistence
# ═══════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    """Load application configuration from disk.

    Reads the JSON config file if it exists; otherwise returns a dict filled
    with sensible defaults. The config stores:
      - xml_path       : Where to write the site-list XML
      - expires_days   : How many days from today each site entry expires
      - use_machine_hive: True = write to HKLM (all users),
                           False = write to HKCU (current user only)
      - sites          : List of {url, compat_mode} dicts

    Returns:
        dict: The merged configuration dictionary.
    """
    defaults = {
        "xml_path": DEFAULT_XML_PATH,
        "expires_days": 360,
        "use_machine_hive": True,
        "sites": []
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            # Corrupted or unreadable config — silently use defaults
            pass
    return defaults


def save_config(cfg: dict):
    """Persist the configuration dictionary to disk as formatted JSON.

    Args:
        cfg: The full configuration dictionary to save.
    """
    try:
        os.makedirs(BASE_DIR, exist_ok=True)
    except OSError:
        pass  # If we can't create dir, the open() below will raise naturally
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# Section 3: XML Generation & Parsing Utilities
# ═══════════════════════════════════════════════════════════════════════

def prettify_xml(elem) -> str:
    """Convert an ElementTree element into a pretty-printed XML string.

    Uses minidom for indentation because ElementTree's built-in tostring()
    produces a single-line string which is hard to debug manually.

    Args:
        elem: An xml.etree.ElementTree.Element (the root <site-list>).

    Returns:
        str: A nicely indented XML document string (without XML declaration).
    """
    rough = ET.tostring(elem, encoding="unicode")
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent="  ", encoding=None)


def build_site_list_xml(sites: list, expires_date: str) -> str:
    """Build a complete Enterprise Mode Site List v2 XML from the site list.

    The resulting XML conforms to the Microsoft schema expected by Edge:
    https://learn.microsoft.com/en-us/deployedge/edge-ie-mode-site-list

    Each <site> entry contains:
      - url attribute        : The domain/IP (protocol stripped)
      - <open-in>            : Always "IE11" (forces Trident engine)
      - <compat-mode>        : User-selected mode (Default, IE8Enterprise, etc.)
      - <expires>            : ISO date when this entry stops being enforced

    Args:
        sites:       List of {"url": str, "compat_mode": str} dicts.
        expires_date: ISO format date string (YYYY-MM-DD) for the <expires>
                     element of every site entry.

    Returns:
        str: The complete XML document as a string.
    """
    root = ET.Element("site-list", attrib={"version": "2"})
    created = ET.SubElement(root, "created-by")
    ET.SubElement(created, "tool").text = "Edge IE Manager"
    ET.SubElement(created, "version").text = "2.0"
    ET.SubElement(created, "date-created").text = datetime.date.today().isoformat()

    for si in sites:
        url = si.get("url", "").strip()
        if not url:
            continue  # Skip empty entries
        # Strip protocol prefix and trailing slash — Edge expects bare hostnames
        url_clean = re.sub(r"^https?://", "", url).rstrip("/")
        site_elem = ET.SubElement(root, "site", attrib={"url": url_clean})
        ET.SubElement(site_elem, "open-in").text = "IE11"
        ET.SubElement(site_elem, "compat-mode").text = si.get("compat_mode", "Default")
        ET.SubElement(site_elem, "expires").text = expires_date

    return prettify_xml(root)


def write_xml_file(path: str, content: str):
    """Write XML content to disk, creating parent directories as needed.

    Args:
        path:    Target file path for the XML.
        content: The XML string to write.
    """
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def parse_xml_to_sites(xml_path: str) -> list:
    """Parse an existing site-list XML and extract all site entries.

    Used when importing sites from an existing XML (e.g., one already
    configured by another tool or manually). Only extracts url and
    compat-mode; ignores other attributes.

    Args:
        xml_path: Absolute path to the XML file.

    Returns:
        list: [{"url": str, "compat_mode": str}, ...]
    """
    sites = []
    if not os.path.exists(xml_path):
        return sites
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for site in root.iter("site"):
            url = site.attrib.get("url", "").strip()
            if not url:
                continue
            mode_el = site.find("compat-mode")
            mode = mode_el.text if (mode_el is not None and mode_el.text) else "Default"
            sites.append({"url": url, "compat_mode": mode})
    except Exception:
        pass  # Malformed XML — return empty rather than crash
    return sites


def calc_remaining_days(xml_path: str) -> dict:
    """Calculate how many days remain until each site's expiry date.

    Parses the generated XML, reads each <expires> value, compares it to
    today's date, and returns a mapping of {url: remaining_days}.

    Args:
        xml_path: Path to the site-list XML file.

    Returns:
        dict: {url_string: int_days_remaining_or_None}
    """
    result = {}
    if not os.path.exists(xml_path):
        return result
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        today = datetime.date.today()
        for site in root.iter("site"):
            url_attr = site.attrib.get("url", "")
            exp_el = site.find("expires")
            if exp_el is not None and exp_el.text:
                try:
                    d = datetime.date.fromisoformat(exp_el.text)
                    delta = (d - today).days
                    result[url_attr] = max(delta, 0)  # Never show negative
                except (ValueError, TypeError):
                    result[url_attr] = None  # Unparseable date
    except Exception:
        pass
    return result


def extend_expiry_in_xml(xml_path: str, days: int) -> tuple:
    """Extend the <expires> date for every site entry in the XML.

    Opens the existing XML, sets every <expires> element to
    (today + days) days, and writes it back.

    Args:
        xml_path: Path to the site-list XML.
        days:     Number of days from now to set as the new expiry.

    Returns:
        tuple: (success: bool, count_of_updated_sites: int, new_date_iso: str)
    """
    if not os.path.exists(xml_path):
        return False, "", ""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        new_date = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
        count = 0
        for site in root.iter("site"):
            exp = site.find("expires")
            if exp is not None:
                exp.text = new_date
                count += 1
        write_xml_file(xml_path, prettify_xml(root))
        return True, count, new_date
    except Exception as e:
        return False, 0, ""


def merge_sites_into_config(cfg: dict, new_sites: list) -> int:
    """Merge a list of site dicts into cfg['sites'], skipping duplicates.

    Deduplication is based on the "url" field. New entries that don't already
    exist in the config are appended, and the updated config is saved to disk.

    Args:
        cfg:       The app config dictionary (modified in-place).
        new_sites: List of {"url": str, "compat_mode": str} to merge.

    Returns:
        int: Number of newly added entries.
    """
    existing = {s["url"] for s in cfg["sites"]}
    added = 0
    for ns in new_sites:
        if ns["url"] not in existing:
            cfg["sites"].append(ns)
            existing.add(ns["url"])
            added += 1
    if added > 0:
        save_config(cfg)
    return added


# ═══════════════════════════════════════════════════════════════════════
# Section 4: Windows Registry Operations
# ═══════════════════════════════════════════════════════════════════════

def set_registry_ie_mode(xml_path: str, use_machine: bool = False) -> tuple:
    """Configure the Windows Registry to enable Edge IE mode.

    Writes two values to the Edge policy key:
      1. InternetExplorerIntegrationLevel   = 1 (DWORD)
         Tells Edge to enable IE mode support.
      2. InternetExplorerIntegrationSiteList = file:///path/to/xml (SZ)
         Tells Edge where to find the site list XML.

    Args:
        xml_path:   Absolute local path to the site-list XML file.
        use_machine: If True, writes to HKLM (all users).
                     If False, writes to HKCU (current user only).

    Returns:
        tuple: (success: bool, message: str)
               On success, message contains the registry key and file URL.
               On failure, message contains the exception description.
    """
    hive = HIVE_MACHINE if use_machine else HIVE_USER
    hive_name = "HKLM" if use_machine else "HKCU"
    try:
        key = winreg.CreateKeyEx(hive, REG_PATH, 0, winreg.KEY_SET_VALUE)

        # Enable IE integration (value 1 = IE mode enabled)
        winreg.SetValueEx(key, REG_VAL_IE_MODE, 0, winreg.REG_DWORD, 1)

        # Point Edge to our XML file using file:// protocol URL
        file_url = "file:///" + xml_path.replace("\\", "/")
        winreg.SetValueEx(key, REG_VAL_SITELIST, 0, winreg.REG_SZ, file_url)
        winreg.CloseKey(key)

        msg = "{}\\{} OK\nPath: {}".format(hive_name, REG_PATH, file_url)
        return True, msg
    except Exception as e:
        return False, str(e)


def get_sitelist_xml_from_registry() -> str:
    """Read the sitelist XML file path from Edge's registry settings.

    Checks both HKLM and HKCU hives (in that order). The stored value is
    typically a file:// URL like "file:///C:/path/to/file.xml". This function
    strips the protocol prefix and converts forward slashes back to Windows-style
    backslashes to produce a usable local file path.

    Returns:
        str: The local file path to the existing XML, or empty string if none found.
    """
    for hive in [HIVE_MACHINE, HIVE_USER]:
        try:
            key = winreg.OpenKey(hive, REG_PATH, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, REG_VAL_SITELIST)
            winreg.CloseKey(key)

            s = val.strip()
            # Strip file:/// or file:// prefix
            if s.lower().startswith("file:///"):
                s = s[8:]
            elif s.lower().startswith("file://"):
                s = s[7:]
            # Convert URL-style slashes to Windows path separators
            s = s.replace("/", "\\")
            return s
        except FileNotFoundError:
            continue  # Key or value doesn't exist in this hive — try next
        except Exception:
            continue
    return ""


def read_registry_value() -> dict:
    """Read the current Edge IE mode registry values for display.

    Queries both HKLM and HKCU for the two relevant values and returns
    them as a flat dict keyed by "hive_value_name".

    Returns:
        dict: E.g., {"HKLM_iemode": 1, "HKLM_sitelist": "file:///..."}
    """
    result = {}
    for hive, hn in [(HIVE_USER, "HKCU"), (HIVE_MACHINE, "HKLM")]:
        try:
            key = winreg.OpenKey(hive, REG_PATH, 0, winreg.KEY_READ)
            for vn, rk in [(REG_VAL_SITELIST, "_sitelist"),
                          (REG_VAL_IE_MODE, "_iemode")]:
                try:
                    val, _ = winreg.QueryValueEx(key, vn)
                    result[hn + rk] = val
                except FileNotFoundError:
                    pass  # This particular value isn't set
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass  # Entire key doesn't exist for this hive
    return result


# ═══════════════════════════════════════════════════════════════════════
# Section 5: Browser Control
# ═══════════════════════════════════════════════════════════════════════

def reload_edge_sitelist() -> tuple:
    """Force-close all Microsoft Edge processes so they re-read the site list.

    Edge caches the site list in memory and only reloads it on process start.
    Killing all msedge.exe processes causes the next launch to fetch the
    updated XML. This is equivalent to asking the user to close and reopen
    Edge manually, but automated.

    Uses PowerShell for cross-process termination because taskkill may be
    blocked by some enterprise security policies.

    Returns:
        tuple: (success: bool, error_message_or_empty_str)
    """
    try:
        subprocess.run(
            ["powershell", "-Command",
             "Get-Process msedge -ErrorAction SilentlyContinue | "
             "Stop-Process -Force"],
            capture_output=True,
            timeout=10
        )
        return True, ""
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════
# Section 6: Main Application Window (tkinter GUI)
# ═══════════════════════════════════════════════════════════════════════

class Application(tk.Tk):
    """Main application window for the Edge IE Compatibility Mode Manager.

    Layout structure (top to bottom):
      ┌──────────────────────────────────────────────┐
      │  Title Bar (blue header with app name)       │
      ├──────────────────────────────────────────────┤
      │  Sites Tab                                   │
      │  ┌────────────────────┬─────────────────┐    │
      │  │  Toolbar (input +  │  Action Panel   │    │
      │  │  buttons)          │  (right side)    │    │
      │  ├────────────────────┤                  │    │
      │  │  Site Table        │  Generate&Apply  │    │
      │  │  (Treeview)        │  Extend Validity │    │
      │  │                    │  Reload Edge     │    │
      │  │                    ├─────────────────┤    │
      │  │                    │  Delete Selected │    │
      │  └────────────────────┴─────────────────┘    │
      │  Status Bar                                  │
      ├──────────────────────────────────────────────┤
      │  Settings Tab                                │
      └──────────────────────────────────────────────┘

    Only the Sites and Settings tabs are visible. Registry and Log tabs
    have been removed from this project version for simplicity.
    """

    def __init__(self):
        """Initialize the application window and build the UI.

        Steps performed during initialization:
          1. Load persisted configuration from config.json
          2. Detect and auto-import any existing IE mode sites from the
             currently configured Edge XML (found via registry lookup)
          3. Create the main window with title, geometry, and styling
          4. Build all UI components (toolbar, table, buttons, status bar)
          5. Populate the site table and update the status bar
        """
        super().__init__()

        try:
            # Step 1: Load saved preferences
            self.cfg = load_config()

            # Step 2: Auto-import from existing Edge IE mode XML (if any exists)
            # This ensures sites previously configured by other tools or manual
            # edits appear in the manager on first launch.
            reg_xml = get_sitelist_xml_from_registry()
            if reg_xml:
                existing_sites = parse_xml_to_sites(reg_xml)
                if existing_sites:
                    added = merge_sites_into_config(self.cfg, existing_sites)
                    # Keep track of where the original XML lives
                    if reg_xml != self.cfg.get("xml_path"):
                        self.cfg["xml_path"] = reg_xml
                        save_config(self.cfg)

            # Step 3: Configure main window properties
            self.title("Edge IE Compatibility Mode Manager")
            self.geometry("680x520")
            self.minsize(600, 420)
            self.resizable(True, True)
            self.configure(bg=C_GRAY_LIGHT)

            # Apply custom ttk styles for a modern look
            style = ttk.Style()
            style.theme_use("clam")
            self._setup_styles(style)

            # Step 4: Build all UI sections
            self._build_ui()

            # Step 5: Populate initial data
            self._refresh_site_table()
            self._update_status_bar()

        except Exception as e:
            # Catch any startup error gracefully instead of silent crash
            messagebox.showerror(
                "Startup Error",
                "The application failed to start:\n\n"
                + str(e)
                + "\n\nPlease ensure you are running on Windows with admin rights."
            )
            self.destroy()
            raise

    # ────────────────────────────────────────────────────────────────────
    # Style Configuration
    # ────────────────────────────────────────────────────────────────────

    def _setup_styles(self, style: ttk.Style):
        """Apply custom visual styles to all ttk widgets.

        Overrides default ttk theme colors to create a cohesive, professional
        appearance with consistent fonts, colors, and spacing.

        Args:
            style: The ttk.Style instance to configure.
        """
        # Notebook (tab container) styles
        style.configure("TNotebook", background=C_GRAY_LIGHT, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            font=("Segoe UI", "10"),
            padding=[12, 6]
        )
        # Tab appearance states
        style.map(
            "TNotebook.Tab",
            background=[("selected", "white"), ("active", "#E8EFF7")],
            foreground=[("selected", C_BLUE)]
        )

        # Treeview (data table) styles
        style.configure(
            "Treeview",
            font=("Consolas", 10),
            rowheight=28,
            fieldbackground="white",
            background="white"
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", "9", "bold"),
            background="#E2E8F0",
            foreground="#374151"
        )
        # Remove default Treeview border lines for cleaner look
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # ────────────────────────────────────────────────────────────────────
    # UI Construction
    # ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Assemble the complete UI layout.

        Creates the title bar, notebook with tabs, and delegates to
        individual tab-building methods.
        """
        self._build_title_bar()

        # Notebook (tab container)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Create visible tabs (Registry and Log tabs are intentionally omitted)
        self._build_tab_sites()
        self._build_tab_settings()

    def _build_title_bar(self):
        """Create the blue header bar at the top of the window.

        Displays the application name in white bold text on a blue
        background. No language toggle button in this English-only version.
        """
        hdr = tk.Frame(self, bg=C_BLUE, height=42, cursor="fleur")
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)  # Prevent child widgets from shrinking it

        tk.Label(
            hdr,
            text="Edge IE Compatibility Mode Manager",
            font=("Segoe UI", 11, "bold"),
            fg="white",
            bg=C_BLUE,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=14, pady=8)

    # ────────────────────────────────────────────────────────────────────
    # Tab 1: Sites (Main workspace)
    # ────────────────────────────────────────────────────────────────────

    def _build_tab_sites(self):
        """Build the primary "Sites" tab — the main workspace.

        Contains three horizontal regions (top to bottom):
          1. Toolbar: input field, mode selector, add/import/export buttons
          2. Main area: left = site table (Treeview), right = action buttons
          3. Status bar: shows site count, config path, and last action time
        """
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  Sites  ")

        # ════ 1. Toolbar Row ════
        bar = tk.Frame(f, bg=C_TOOLBAR, height=44)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)

        # -- Input field for new site URL --
        tk.Label(bar, text="New Site:", bg=C_TOOLBAR,
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(10, 2))
        self.entry_url = tk.Entry(bar, width=24, font=("Consolas", 10))
        self.entry_url.pack(side=tk.LEFT, padx=4, pady=6)
        self.entry_url.bind("<Return>", lambda e: self._add_site())
        # Pressing Enter triggers the same as clicking "Add"

        # -- Compat mode dropdown --
        tk.Label(bar, text="Mode:", bg=C_TOOLBAR,
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(8, 2))
        self.compat_var = tk.StringVar(value="Default")
        cmb = ttk.Combobox(
            bar,
            textvariable=self.compat_var,
            width=11,
            values=["Default", "IE8Enterprise", "IE7Enterprise", "IE11"],
            state="readonly",
            font=("Segoe UI", 9)
        )
        cmb.pack(side=tk.LEFT, padx=4)

        # -- Action buttons in toolbar --
        tk.Button(
            bar, text="+ Add", command=self._add_site,
            bg=C_BLUE, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=10, pady=4
        ).pack(side=tk.LEFT, padx=(10, 4))

        tk.Button(
            bar, text="Import", command=self._import_txt,
            bg=C_GREEN, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9), padx=8, pady=4
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            bar, text="Export", command=self._export_txt,
            bg=C_AMBER, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9), padx=8, pady=4
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            bar, text="From XML", command=self._import_from_xml,
            bg="#7C3AED", fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9), padx=8, pady=4
        ).pack(side=tk.LEFT, padx=2)

        # ════ 2. Main Area: Table (left) + Button Panel (right) ════
        main = tk.Frame(f)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # ---- Left: Data Table (Treeview) ----
        tv_frame = tk.Frame(main, bg="white")
        tv_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Define columns: URL, Compatibility Mode, Remaining Days
        cols = ("url", "mode", "days")
        self.tree = ttk.Treeview(
            tv_frame,
            columns=cols,
            show="headings",
            selectmode="extended"  # Allow multi-select with Ctrl/Cmd
        )

        # Column headers
        self.tree.heading("url",  text="Site URL",           anchor=tk.W)
        self.tree.heading("mode", text="Compat Mode",        anchor=tk.CENTER)
        self.tree.heading("days", text="Expires In",         anchor=tk.CENTER)

        # Column widths and alignment
        self.tree.column("url",  width=270, minwidth=180, anchor=tk.W)
        self.tree.column("mode", width=110, minwidth=90,  anchor=tk.CENTER)
        self.tree.column("days", width=100, minwidth=80,  anchor=tk.CENTER)

        # Vertical scrollbar for the table
        vsb = ttk.Scrollbar(tv_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tv_frame.grid_rowconfigure(0, weight=1)
        tv_frame.grid_columnconfigure(0, weight=1)

        # ---- Right: Action Button Panel (fixed-width sidebar) ----
        side = tk.Frame(main, bg=C_GRAY_LIGHT, width=130,
                        relief=tk.GROOVE, borderwidth=0)
        side.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        side.pack_propagate(False)  # Maintain fixed width regardless of content

        # --- Actions Group ---
        tk.Label(
            side, text="Actions",
            font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg=C_GRAY_LIGHT
        ).pack(pady=(10, 4))

        # Primary action: generate XML and apply registry settings
        tk.Button(
            side, text="Generate XML\n& Apply",
            command=self._apply_all,
            bg=C_BLUE, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9, "bold"), width=13, height=3
        ).pack(padx=6, pady=3)

        # Extend validity dates for all entries
        tk.Button(
            side, text="Extend\nValidity",
            command=self._extend_expiry,
            bg=C_AMBER, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9, "bold"), width=13, height=3
        ).pack(padx=6, pady=3)

        # Restart Edge to reload site list
        tk.Button(
            side, text="Reload Edge",
            command=self._reload_edge,
            bg=C_GRAY, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9, "bold"), width=13, height=2
        ).pack(padx=6, pady=3)

        # Visual separator between groups
        sep = tk.Frame(side, height=1, bg="#CBD5E1")
        sep.pack(fill=tk.X, padx=6, pady=8)

        # --- Manage Group ---
        tk.Label(
            side, text="Manage",
            font=("Segoe UI", 9, "bold"), fg="#94A3B8", bg=C_GRAY_LIGHT
        ).pack(pady=(0, 4))

        # Delete selected rows from the table and config
        tk.Button(
            side, text="Delete Selected",
            command=self._del_site,
            bg=C_RED, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9, "bold"), width=13, height=2
        ).pack(padx=6, pady=3)

        # ════ 3. Status Bar (bottom of Sites tab) ════
        status_frame = tk.Frame(f, bg=C_STATUS_BG)
        status_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        self.status_left_lbl = tk.Label(
            status_frame, text="", anchor=tk.W,
            font=("Consolas", 9), fg="#64748B", bg=C_STATUS_BG
        )
        self.status_left_lbl.pack(side=tk.LEFT, padx=8, pady=3)

        self.status_right_lbl = tk.Label(
            status_frame, text="", anchor=tk.E,
            font=("Segoe UI", 9), fg="#94A3B8", bg=C_STATUS_BG
        )
        self.status_right_lbl.pack(side=tk.RIGHT, padx=8, pady=3)

        self._update_status_bar()

    # ────────────────────────────────────────────────────────────────────
    # Tab 2: Settings
    # ────────────────────────────────────────────────────────────────────

    def _build_tab_settings(self):
        """Build the "Settings" tab for configuring program options.

        Allows the user to customize:
          - Output path for the generated XML file
          - Default number of days until site entries expire
          - Registry scope (HKLM for all users vs HKCU for current user only)
        """
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="  Settings  ")

        pad = {"padx": 20, "pady": 10, "sticky": tk.W}

        # -- XML File Path setting --
        tk.Label(
            f, text="XML File Path:",
            font=("Segoe UI", 10)
        ).grid(row=0, column=0, **pad)

        self.var_xml_path = tk.StringVar(value=self.cfg["xml_path"])
        tk.Entry(
            f, textvariable=self.var_xml_path, width=48,
            font=("Consolas", 9)
        ).grid(row=0, column=1, **pad)

        tk.Button(
            f, text="...", command=self._browse_xml,
            font=("Segoe UI", 10), width=3
        ).grid(row=0, column=2, padx=4, pady=10)

        # -- Expiry Days setting --
        tk.Label(
            f, text="Expiry Extension Days:",
            font=("Segoe UI", 10)
        ).grid(row=1, column=0, **pad)

        self.var_days = tk.IntVar(value=self.cfg["expires_days"])
        tk.Spinbox(
            f, from_=1, to=1000,
            textvariable=self.var_days,
            width=8, font=("Consolas", 10)
        ).grid(row=1, column=1, **pad)

        # -- Registry Scope setting --
        tk.Label(
            f, text="Registry Scope:",
            font=("Segoe UI", 10)
        ).grid(row=2, column=0, **pad)

        self.var_hive = tk.BooleanVar(value=self.cfg["use_machine_hive"])
        tk.Radiobutton(
            f, text="Current User (HKCU)",
            variable=self.var_hive, value=False,
            font=("Segoe UI", 10)
        ).grid(row=2, column=1, **pad)
        tk.Radiobutton(
            f, text="All Users (HKLM)",
            variable=self.var_hive, value=True,
            font=("Segoe UI", 10)
        ).grid(row=3, column=1, **pad)

        # Save button
        tk.Button(
            f, text="Save Settings", command=self._save_settings,
            bg=C_BLUE, fg="white", relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 10, "bold"), padx=16, pady=5
        ).grid(row=4, column=1, **pad)

        # Tips / help text box
        tip_box = tk.Text(
            f, height=6, wrap=tk.WORD,
            font=("Segoe UI", 9),
            bg="#EBF4FF", fg="#475569",
            relief=tk.GROOVE, padx=10, pady=8, state=tk.NORMAL
        )
        tip_text = (
            "Tips:\n"
            "- Program auto-elevates to administrator on launch.\n"
            "- The XML path supports both local paths and UNC network paths.\n"
            "- After the expiry date passes, Edge will stop forcing IE mode "
            "for those sites.\n"
            "- Click \"Extend Validity\" regularly, or set up a scheduled "
            "task to do it automatically."
        )
        tip_box.insert("1.0", tip_text)
        tip_box.config(state=tk.DISABLED)  # Read-only
        tip_box.grid(row=5, column=0, columnspan=3, padx=20, pady=16,
                     sticky=tk.W + tk.E)

    # ────────────────────────────────────────────────────────────────────
    # Internal Helper Methods
    # ────────────────────────────────────────────────────────────────────

    def _update_status_bar(self):
        """Refresh the status bar text with current counts and timestamps.

        Left side: number of sites + truncated config file path.
        Right side: timestamp of last update (current time).
        """
        n = len(self.cfg.get("sites", []))
        p = self.cfg.get("xml_path", "")[:50]  # Truncate very long paths
        ts = datetime.datetime.now().strftime("%m-%d %H:%M")

        left_msg = "{} sites | Config: {}".format(n, p)
        right_msg = "Last action: {}".format(ts)

        self.status_left_lbl.config(text=left_msg)
        self.status_right_lbl.config(text=right_msg)

    def _refresh_site_table(self):
        """Rebuild the entire site table from the current config.

        For each site, looks up its remaining days from the XML file and
        displays a color-coded badge:
          - Green (>30 days): plenty of time remaining
          - Amber (7–30 days): approaching expiry, plan to extend soon
          - Red (<7 days): urgent — will expire very soon
          - Gray dash (-): no XML generated yet or no parseable date
        """
        # Clear all existing rows
        for row in self.tree.get_children():
            self.tree.delete(row)

        xml_p = self.cfg.get("xml_path", DEFAULT_XML_PATH)
        days_map = calc_remaining_days(xml_p)

        for s in self.cfg.get("sites", []):
            url = s["url"]
            mode = s["compat_mode"]
            rem = days_map.get(url)

            if rem is not None and rem >= 0:
                # Format with plural-aware label
                days_txt = "{} day{}".format(rem, "s" if rem != 1 else "")
                # Choose color based on urgency threshold
                if rem > 30:
                    color = C_GREEN
                elif rem >= 7:
                    color = C_AMBER
                else:
                    color = C_RED
            else:
                days_txt = "-"
                color = "#94A3B8"  # Gray for unknown/no-data

            self.tree.insert("", tk.END, values=(url, mode, days_txt),
                             tags=(color,))

        # Apply tag-specific formatting (foreground color + bold font)
        self.tree.tag_configure(C_GREEN, foreground=C_GREEN,
                                 font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure(C_AMBER, foreground=C_AMBER,
                                 font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure(C_RED, foreground=C_RED,
                                 font=("Segoe UI", 10, "bold"))

        self._update_status_bar()

    # ────────────────────────────────────────────────────────────────────
    # Event Handlers: Site Management
    # ────────────────────────────────────────────────────────────────────

    def _add_site(self):
        """Handle the "Add" button click or Enter key press in the input field.

        Validates the input URL, checks for duplicates, adds the new site to
        the config, updates the table, clears the input field, and logs the
        action.
        """
        url_raw = self.entry_url.get().strip()
        if not url_raw:
            messagebox.showwarning("", "Please enter an IP address or domain name.")
            return

        # Normalize: strip http(s):// prefix and trailing slash
        url_clean = re.sub(r"^https?://", "", url_raw).rstrip("/")
        compat = self.compat_var.get()

        # Check for duplicate
        existing_urls = [s["url"] for s in self.cfg["sites"]]
        if url_clean in existing_urls:
            messagebox.showinfo("", "{} is already in the list.".format(url_clean))
            return

        # Append to config and persist
        self.cfg["sites"].append({"url": url_clean, "compat_mode": compat})
        save_config(self.cfg)

        # Insert into the visible table immediately (no full refresh needed)
        self.tree.insert("", tk.END, values=(url_clean, compat, "-"),
                         tags=("#94A3B8",))
        self.entry_url.delete(0, tk.END)  # Clear input for next entry
        self._update_status_bar()

    def _del_site(self):
        """Remove all selected rows from both the table and the config.

        Prompts if nothing is selected. Supports multi-select (Ctrl+click).
        After deletion, saves the updated config to disk.
        """
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("", "Please select items to delete first.")
            return

        for item in selected:
            url = self.tree.item(item)["values"][0]
            # Remove from config by filtering out matching URL
            self.cfg["sites"] = [s for s in self.cfg["sites"]
                                 if s["url"] != url]
            self.tree.delete(item)  # Remove visual row

        save_config(self.cfg)
        self._update_status_bar()

    def _import_txt(self):
        """Import sites from a plain-text file (one URL per line).

        Opens a file dialog for the user to pick a .txt file, then reads
        each non-empty, non-comment line as a URL to add. Skips duplicates.
        Lines starting with '#' are treated as comments.
        """
        path = filedialog.askopenfilename(
            title="Select IP / Domain List File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return

        added = 0
        existing = {s["url"] for s in self.cfg["sites"]}

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                url = line.strip()
                if not url or url.startswith("#"):
                    continue  # Skip blank lines and comments
                url_clean = re.sub(r"^https?://", "", url).rstrip("/")
                if url_clean and url_clean not in existing:
                    self.cfg["sites"].append({
                        "url": url_clean,
                        "compat_mode": "Default"
                    })
                    existing.add(url_clean)
                    added += 1

        save_config(self.cfg)
        self._refresh_site_table()
        messagebox.showinfo("", "{} addresses imported successfully.".format(added))

    def _export_txt(self):
        """Export all site URLs to a plain-text file (one per line).

        Useful for sharing the site list or editing externally before
        importing back.
        """
        path = filedialog.asksaveasfilename(
            title="Export Site List",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            for s in self.cfg["sites"]:
                f.write(s["url"] + "\n")

        messagebox.showinfo("", "Exported to: {}".format(path))

    def _import_from_xml(self):
        """Import sites from an existing Edge site-list XML file.

        Allows loading sites from any compatible Enterprise Mode Site List
        XML (v2 schema), merging them into the current config without
        creating duplicates.
        """
        path = filedialog.askopenfilename(
            title="Select Existing Site-List XML",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )
        if not path:
            return

        sites = parse_xml_to_sites(path)
        if not sites:
            messagebox.showwarning("", "Failed to parse XML or file is empty.")
            return

        added = merge_sites_into_config(self.cfg, sites)
        # Update the config's XML path to point to the imported file
        self.cfg["xml_path"] = path
        save_config(self.cfg)

        self._refresh_site_table()
        messagebox.showinfo("", "Successfully imported {} sites from XML.".format(added))

    # ────────────────────────────────────────────────────────────────────
    # Event Handlers: Settings
    # ────────────────────────────────────────────────────────────────────

    def _save_settings(self):
        """Persist the current Settings tab values to config.json.

        Reads the values from the input fields (XML path, days, hive choice)
        and writes them to the config file. Shows a confirmation message.
        Validates that expiry days does not exceed 1000.
        """
        MAX_EXPIRY_DAYS = 1000
        self.cfg["xml_path"] = self.var_xml_path.get().strip()
        days_val = self.var_days.get()

        if days_val > MAX_EXPIRY_DAYS:
            messagebox.showwarning(
                "Warning",
                f"The maximum allowed value is {MAX_EXPIRY_DAYS} days.\n"
                f"Your input ({days_val}) exceeds this limit.\n\n"
                f"Please adjust the 'Expiry Extension Days' field to "
                f"{MAX_EXPIRY_DAYS} or below."
            )
            return

        self.cfg["expires_days"] = days_val
        self.cfg["use_machine_hive"] = self.var_hive.get()
        save_config(self.cfg)
        messagebox.showinfo("", "Settings saved.")

    def _browse_xml(self):
        """Open a "Save As" dialog for choosing the XML output path."""
        path = filedialog.asksaveasfilename(
            title="Choose XML Save Location",
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml")]
        )
        if path:
            self.var_xml_path.set(path)

    # ────────────────────────────────────────────────────────────────────
    # Event Handlers: Core Actions (Generate, Extend, Reload)
    # ────────────────────────────────────────────────────────────────────

    def _apply_all(self):
        """Generate the site-list XML file and write Edge registry settings.

        This is the primary action method. It performs these steps in order:

          1. Validate that there is at least one site in the list.
          2. Calculate the expiry date as (today + configured days).
          3. Call ``build_site_list_xml()`` to generate the XML content.
          4. Call ``write_xml_file()`` to save it to disk.
          5. Call ``set_registry_ie_mode()`` to configure the registry.
          6. Refresh the display and show a success/error dialog.

        If the registry write succeeds, the user must restart Edge (or use
        the "Reload Edge" button) for changes to take effect.
        """
        sites = self.cfg.get("sites", [])
        if not sites:
            messagebox.showwarning("", "Site list is empty. Please add IPs or domains first.")
            return

        # Gather configuration values
        xml_path = self.cfg["xml_path"]
        days = self.cfg["expires_days"]

        # Validate expiry days limit (max 1000)
        if days > 1000:
            messagebox.showwarning(
                "Warning",
                f"Expiry Extension Days ({days}) exceeds the maximum of 1000.\n"
                f"Please adjust this value in Settings and try again."
            )
            return

        expires_date = (datetime.date.today()
                        + datetime.timedelta(days=days)).isoformat()
        use_machine = self.cfg["use_machine_hive"]

        # Step 3 & 4: Build and save XML
        try:
            content = build_site_list_xml(sites, expires_date)
            write_xml_file(xml_path, content)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        # Step 5: Write registry
        ok, msg = set_registry_ie_mode(xml_path, use_machine)
        if ok:
            # Success — refresh display to reflect new state
            self._refresh_site_table()
            detail_msg = (
                "Done!\n\n"
                "XML Path: {}\n"
                "Expires:  {}\n\n"
                "{}\n\n"
                "Please restart Edge to apply the configuration."
            ).format(xml_path, expires_date, msg)
            messagebox.showinfo("OK", detail_msg)
        else:
            messagebox.showerror("Error", msg)

    def _extend_expiry(self):
        """Push forward the expiration date for all sites in the XML.

        Opens the existing XML file, replaces every <expires> value with
        (today + configured extension days), and saves the modified XML back.
        This is useful when the current expiry is approaching and you need
        to keep IE mode active for longer without re-generating everything.
        """
        xml_path = self.cfg["xml_path"]
        days = self.cfg["expires_days"]

        # Validate expiry days limit (max 1000)
        if days > 1000:
            messagebox.showwarning(
                "Warning",
                f"Expiry Extension Days ({days}) exceeds the maximum of 1000.\n"
                f"Please adjust this value in Settings and try again."
            )
            return

        ok, cnt, new_date = extend_expiry_in_xml(xml_path, days)
        if ok:
            summary = "{} records updated, expires {}".format(cnt, new_date)
            self._refresh_site_table()  # Re-read and update badge colors
            messagebox.showinfo("OK", summary +
                                "\n\nIf Edge is open, restart it to reload the site list.")
        else:
            messagebox.showerror("Error",
                                 "XML file not found. Please generate it first using "
                                 "\"Generate XML & Apply\".")

    def _reload_edge(self):
        """Force-close all Edge processes to trigger a site-list reload.

    Shows a confirmation dialog first since this closes all open Edge
    windows (including any unsaved work in web apps). After confirmation,
    uses PowerShell to terminate msedge.exe processes.
        """
        if not messagebox.askyesno("", (
            "This will close all Edge windows to reload the site list.\n"
            "Make sure you have saved any work in web applications.\n\n"
            "Continue?"
        )):
            return

        ok, err = reload_edge_sitelist()
        if ok:
            messagebox.showinfo("OK",
                "Reload command sent. All Edge processes have been closed.\n"
                "Restart Edge to apply the updated site list.")
        else:
            messagebox.showerror("Error", "Reload failed: {}".format(err))


# ═══════════════════════════════════════════════════════════════════════
# Section 7: Entry Point — Auto-Elevation to Administrator
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # On Windows, automatically request administrator privileges via UAC
    # if the program is not already running with elevated rights.
    # This is required because writing to HKLM registry requires admin.
    if sys.platform == "win32":
        try:
            # IsUserAnAdmin() returns nonzero if the process has admin rights
            if not ctypes.windll.shell32.IsUserAnAdmin():
                # Re-launch this same script/exe with "runas" verb to trigger UAC
                script = os.path.abspath(sys.argv[0])
                # Build parameter string (quote args containing spaces)
                params = " ".join(
                    ('"' + a + '"' if " " in a else a)
                    for a in sys.argv[1:]
                )
                ctypes.windll.shell32.ShellExecuteW(
                    None,           # hwnd (no parent window)
                    "runas",        # lpOperation (request elevation)
                    sys.executable, # lpFile (Python interpreter or exe itself)
                    '"' + script + '" ' + params,  # lpParameters
                    None,           # lpDirectory (default working directory)
                    1               # nShowCmd (SW_SHOWNORMAL)
                )
                sys.exit(0)  # Exit the non-elevated copy immediately
        except Exception:
            pass  # If elevation fails for any reason, continue anyway

    # Create the main application window and start the event loop
    app = Application()
    app.mainloop()
