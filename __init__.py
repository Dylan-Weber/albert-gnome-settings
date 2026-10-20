# -*- coding: utf-8 -*-

"""
Search the panels of GNOME Settings (gnome-control-center), the same way the GNOME Shell / Ubuntu
launcher does: by panel name, description and search keywords.

The panels are read from the ``X-GNOME-Settings-Panel`` desktop entries that gnome-control-center
installs, so the list always matches the installed version. Names and keywords are translated
using either inline ``Name[xx]`` keys or the ``X-Ubuntu-Gettext-Domain`` catalog, like the shell.
"""

import gettext
import locale
import os
import shlex
from configparser import ConfigParser, Error as ConfigParserError
from pathlib import Path

from albert import *

md_iid = "5.0"
md_version = "1.0"
md_name = "GNOME Settings"
md_description = "Search and open GNOME Settings panels"
md_license = "MIT"
md_authors = ["@Dylan-Weber"]
md_platforms = ["Linux"]
md_bin_dependencies = ["gnome-control-center"]

PANEL_CATEGORY = "X-GNOME-Settings-Panel"
DESKTOP_ENTRY = "Desktop Entry"


def _data_dirs() -> list[Path]:
    """XDG data dirs in order of precedence."""
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(d) for d in [home, *dirs.split(":")] if d]


def _locale_suffixes() -> list[str]:
    """Desktop entry locale suffixes to try, most specific first (e.g. de_DE@euro, de_DE, de)."""
    lang = None
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(var):
            lang = os.environ[var]
            break
    if not lang:
        lang = locale.getlocale(locale.LC_MESSAGES)[0] or ""
    lang = lang.split(".")[0]  # drop encoding, keep @modifier handling below
    modifier = ""
    if "@" in lang:
        lang, modifier = lang.split("@", 1)
    base = lang.split("_")[0]
    candidates = []
    if modifier:
        candidates += [f"{lang}@{modifier}", f"{base}@{modifier}"]
    candidates += [lang, base]
    return [c for i, c in enumerate(candidates) if c and c not in ("C", "POSIX") and c not in candidates[:i]]


def _desktop_matches(entry, current_desktops: set[str]) -> bool:
    only = {d for d in entry.get("OnlyShowIn", "").lower().split(";") if d}
    not_ = {d for d in entry.get("NotShowIn", "").lower().split(";") if d}
    if only and not (only & current_desktops):
        return False
    if not_ & current_desktops:
        return False
    return True


_brush = None


def _tile_brush():
    # Icon.iconified() takes an albert.Brush at runtime, although albert.pyi still says Color
    global _brush
    if _brush is None:
        _brush = Brush(Color(240, 240, 240))
    return _brush


class Panel(Item):

    def __init__(self, panel_id: str, name: str, comment: str, icon_name: str,
                 command: list[str], keywords: list[str]):
        Item.__init__(self)
        self.panel_id = panel_id
        self.name = name
        self.comment = comment
        self.icon_name = icon_name
        self.command = command
        self.keywords = keywords

    def id(self):
        return self.panel_id

    def text(self):
        return self.name

    def subtext(self):
        return self.comment or "GNOME Settings panel"

    def inputActionText(self):
        return self.name

    def icon(self):
        if not self.icon_name:
            return Icon.theme("org.gnome.Settings")
        # Panel icons are dark symbolic glyphs, put them on a light tile so they work on any theme
        return Icon.iconified(Icon.theme(self.icon_name), _tile_brush())

    def actions(self):
        return [Action("open", "Open", lambda: runDetachedProcess(self.command))]


def load_panels() -> list[Panel]:
    current_desktops = {
        d for d in os.environ.get("XDG_CURRENT_DESKTOP", "GNOME").lower().split(":") if d
    }
    suffixes = _locale_suffixes()

    def localized(entry, key: str, domain: str | None) -> tuple[str, str]:
        """Returns (untranslated, translated) value of **key**."""
        raw = entry.get(key, "")
        for s in suffixes:
            if f"{key}[{s}]" in entry:
                return raw, entry[f"{key}[{s}]"]
        if raw and domain:
            return raw, gettext.dgettext(domain, raw)
        return raw, raw

    panels: dict[str, Panel] = {}
    seen_files: set[str] = set()

    for data_dir in _data_dirs():
        apps_dir = data_dir / "applications"
        if not apps_dir.is_dir():
            continue
        for path in sorted(apps_dir.glob("*.desktop")):
            # Files earlier in XDG_DATA_DIRS shadow later ones with the same id
            if path.name in seen_files:
                continue
            seen_files.add(path.name)

            parser = ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            try:
                parser.read(path, encoding="utf-8")
            except (ConfigParserError, UnicodeDecodeError, OSError) as e:
                debug(f"Skipping {path}: {e}")
                continue
            if not parser.has_section(DESKTOP_ENTRY):
                continue
            entry = parser[DESKTOP_ENTRY]

            if PANEL_CATEGORY not in entry.get("Categories", "").split(";"):
                continue
            if entry.get("Hidden", "false").lower() == "true":
                continue
            if not _desktop_matches(entry, current_desktops):
                continue

            try:
                command = [
                    arg for arg in shlex.split(entry.get("Exec", ""))
                    if not (len(arg) == 2 and arg.startswith("%"))
                ]
            except ValueError:
                continue
            if not command:
                continue

            domain = entry.get("X-Ubuntu-Gettext-Domain") or entry.get("X-GNOME-Gettext-Domain")
            _, name = localized(entry, "Name", domain)
            _, comment = localized(entry, "Comment", domain)
            raw_kw, kw = localized(entry, "Keywords", domain)

            keywords = []
            for k in [*kw.split(";"), *raw_kw.split(";")]:
                k = k.strip()
                if k and k not in keywords:
                    keywords.append(k)

            panel_id = path.name.removesuffix(".desktop")
            panels[panel_id] = Panel(
                panel_id=panel_id,
                name=name,
                comment=comment,
                icon_name=entry.get("Icon", ""),
                command=command,
                keywords=keywords,
            )

    return sorted(panels.values(), key=lambda p: p.name.lower())


class Plugin(PluginInstance, IndexQueryHandler):

    def __init__(self):
        PluginInstance.__init__(self)
        IndexQueryHandler.__init__(self)

    def defaultTrigger(self):
        return "gs "

    def synopsis(self, query):
        return "<panel name or keyword>"

    def updateIndexItems(self):
        panels = load_panels()
        debug(f"Indexed {len(panels)} settings panels")
        index_items = []
        for panel in panels:
            # Like the shell search provider, match name, description and keywords
            strings = [panel.name, *panel.keywords]
            if panel.comment:
                strings.append(panel.comment)
            index_items += [IndexItem(item=panel, string=s) for s in strings]
        self.setIndexItems(index_items)
