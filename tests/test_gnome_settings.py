"""
Tests for the GNOME Settings extension. Run from the repository root with

    python3 -m unittest discover -s tests -v

The extension is loaded with a fake ``albert`` module (see fake_albert.py) and every test runs with
its own environment and temporary XDG data dirs, so results do not depend on the host system.
"""

import importlib.util
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
import fake_albert  # noqa: E402

sys.modules["albert"] = fake_albert

_spec = importlib.util.spec_from_file_location("gnome_settings", TESTS_DIR.parent / "__init__.py")
gs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gs)

# Environment variables the extension reads. Tests start with all of them unset.
ENV_VARS = ("XDG_DATA_HOME", "XDG_DATA_DIRS", "XDG_CURRENT_DESKTOP", "LC_ALL", "LC_MESSAGES", "LANG")

SOUND_PANEL = """\
    [Desktop Entry]
    Name=Sound
    Comment=Change sound levels, inputs, outputs, and alert sounds
    Exec=gnome-control-center sound
    Icon=org.gnome.Settings-sound-symbolic
    Type=Application
    NoDisplay=true
    Categories=GNOME;GTK;Settings;HardwareSettings;X-GNOME-Settings-Panel;X-GNOME-DevicesSettings;
    OnlyShowIn=GNOME;Unity;
    Keywords=Card;Microphone;Volume;Fade;Balance;Bluetooth;Headset;Audio;Output;Input;
    """


def entry(text: str):
    """Parses a desktop entry given as (indented) text."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "test.desktop"
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return gs._read_desktop_entry(path)


class EnvTestCase(unittest.TestCase):
    """Runs every test with the extension's environment variables unset."""

    def setUp(self):
        fake_albert.reset()
        gs._brush = None
        env = {k: v for k, v in os.environ.items() if k not in ENV_VARS}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_env(self, **values):
        os.environ.update(values)


class XdgTestCase(EnvTestCase):
    """Provides a temporary XDG_DATA_HOME and two XDG_DATA_DIRS to put desktop files in."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.home = root / "home"
        self.system = root / "system"
        self.vendor = root / "vendor"
        self.set_env(
            XDG_DATA_HOME=str(self.home),
            XDG_DATA_DIRS=f"{self.system}:{self.vendor}",
            XDG_CURRENT_DESKTOP="ubuntu:GNOME",
            LANG="C",
        )

    def write(self, data_dir: Path, name: str, text: str) -> Path:
        apps = data_dir / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        path = apps / name
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def panel(self, data_dir: Path, panel_id: str, name: str, **keys):
        """Writes a minimal settings panel desktop file. Keys can override or add lines."""
        lines = {
            "Name": name,
            "Exec": f"gnome-control-center {panel_id}",
            "Categories": "GNOME;Settings;X-GNOME-Settings-Panel;",
            **keys,
        }
        body = "\n".join(f"{k}={v}" for k, v in lines.items() if v is not None)
        return self.write(data_dir, f"gnome-{panel_id}-panel.desktop", f"[Desktop Entry]\n{body}\n")


class DataDirsTest(EnvTestCase):

    def test_defaults(self):
        self.assertEqual(gs._data_dirs(), [
            Path.home() / ".local/share", Path("/usr/local/share"), Path("/usr/share")])

    def test_home_comes_first_then_data_dirs_in_order(self):
        self.set_env(XDG_DATA_HOME="/h", XDG_DATA_DIRS="/a:/b")
        self.assertEqual(gs._data_dirs(), [Path("/h"), Path("/a"), Path("/b")])

    def test_empty_entries_are_dropped(self):
        self.set_env(XDG_DATA_HOME="/h", XDG_DATA_DIRS="/a::/b:")
        self.assertEqual(gs._data_dirs(), [Path("/h"), Path("/a"), Path("/b")])

    def test_empty_variables_use_defaults(self):
        self.set_env(XDG_DATA_HOME="", XDG_DATA_DIRS="")
        self.assertEqual(gs._data_dirs(), [
            Path.home() / ".local/share", Path("/usr/local/share"), Path("/usr/share")])


class LocaleSuffixesTest(EnvTestCase):

    def test_language_and_country(self):
        self.set_env(LANG="de_DE.UTF-8")
        self.assertEqual(gs._locale_suffixes(), ["de_DE", "de"])

    def test_language_only(self):
        self.set_env(LANG="de")
        self.assertEqual(gs._locale_suffixes(), ["de"])

    def test_modifier_variants_come_first(self):
        for lang in ("sr_RS.UTF-8@latin", "sr_RS@latin"):
            with self.subTest(lang=lang):
                self.set_env(LANG=lang)
                self.assertEqual(gs._locale_suffixes(), ["sr_RS@latin", "sr@latin", "sr_RS", "sr"])

    def test_c_and_posix_locales_have_no_suffixes(self):
        for lang in ("C", "C.UTF-8", "POSIX"):
            with self.subTest(lang=lang):
                self.set_env(LANG=lang)
                self.assertEqual(gs._locale_suffixes(), [])

    def test_lc_all_overrides_lc_messages_overrides_lang(self):
        self.set_env(LANG="fr_FR.UTF-8", LC_MESSAGES="es_ES.UTF-8", LC_ALL="de_DE.UTF-8")
        self.assertEqual(gs._locale_suffixes(), ["de_DE", "de"])
        del os.environ["LC_ALL"]
        self.assertEqual(gs._locale_suffixes(), ["es_ES", "es"])
        del os.environ["LC_MESSAGES"]
        self.assertEqual(gs._locale_suffixes(), ["fr_FR", "fr"])

    def test_empty_variables_are_skipped(self):
        self.set_env(LC_ALL="", LANG="it_IT.UTF-8")
        self.assertEqual(gs._locale_suffixes(), ["it_IT", "it"])

    def test_falls_back_to_process_locale(self):
        with mock.patch.object(gs.locale, "getlocale", return_value=("pt_BR", "UTF-8")):
            self.assertEqual(gs._locale_suffixes(), ["pt_BR", "pt"])

    def test_no_locale_at_all(self):
        with mock.patch.object(gs.locale, "getlocale", return_value=(None, None)):
            self.assertEqual(gs._locale_suffixes(), [])


class DesktopMatchesTest(unittest.TestCase):

    def test_no_restrictions(self):
        self.assertTrue(gs._desktop_matches({}, {"gnome"}))

    def test_only_show_in(self):
        e = {"OnlyShowIn": "GNOME;Unity;"}
        self.assertTrue(gs._desktop_matches(e, {"gnome"}))
        self.assertTrue(gs._desktop_matches(e, {"ubuntu", "unity"}))
        self.assertFalse(gs._desktop_matches(e, {"kde"}))

    def test_not_show_in(self):
        e = {"NotShowIn": "KDE;"}
        self.assertFalse(gs._desktop_matches(e, {"kde"}))
        self.assertTrue(gs._desktop_matches(e, {"gnome"}))

    def test_not_show_in_wins_over_only_show_in(self):
        e = {"OnlyShowIn": "GNOME;", "NotShowIn": "ubuntu;"}
        self.assertFalse(gs._desktop_matches(e, {"ubuntu", "gnome"}))

    def test_case_insensitive(self):
        self.assertTrue(gs._desktop_matches({"OnlyShowIn": "Ubuntu;"}, {"ubuntu"}))


class CurrentDesktopsTest(EnvTestCase):

    def test_defaults_to_gnome(self):
        self.assertEqual(gs._current_desktops(), {"gnome"})

    def test_colon_separated_and_lowercase(self):
        self.set_env(XDG_CURRENT_DESKTOP="ubuntu:GNOME")
        self.assertEqual(gs._current_desktops(), {"ubuntu", "gnome"})


class DesktopFilesTest(XdgTestCase):

    def test_earlier_dirs_shadow_later_ones(self):
        self.write(self.vendor, "a.desktop", "[Desktop Entry]\n")
        self.write(self.system, "a.desktop", "[Desktop Entry]\n")
        self.write(self.home, "a.desktop", "[Desktop Entry]\n")
        self.write(self.vendor, "b.desktop", "[Desktop Entry]\n")
        files = {p.name: p for p in gs._desktop_files()}
        self.assertEqual(files, {
            "a.desktop": self.home / "applications/a.desktop",
            "b.desktop": self.vendor / "applications/b.desktop",
        })

    def test_only_desktop_files(self):
        self.write(self.system, "a.desktop", "[Desktop Entry]\n")
        self.write(self.system, "mimeinfo.cache", "")
        self.assertEqual([p.name for p in gs._desktop_files()], ["a.desktop"])

    def test_missing_dirs_are_skipped(self):
        self.assertEqual(gs._desktop_files(), [])


class ReadDesktopEntryTest(unittest.TestCase):

    def test_keys_keep_their_case(self):
        e = entry("""\
            [Desktop Entry]
            Name=Sound
            Name[de]=Klang
            """)
        self.assertEqual(e["Name"], "Sound")
        self.assertEqual(e["Name[de]"], "Klang")

    def test_percent_signs_are_not_interpolated(self):
        self.assertEqual(entry("[Desktop Entry]\nExec=foo %U\n")["Exec"], "foo %U")

    def test_missing_desktop_entry_section(self):
        self.assertIsNone(entry("[Desktop Action new]\nName=New\n"))

    def test_malformed_file(self):
        self.assertIsNone(entry("no section header\n"))

    def test_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.desktop"
            path.write_bytes(b"[Desktop Entry]\nName=\xff\xfe\n")
            self.assertIsNone(gs._read_desktop_entry(path))

    def test_duplicate_keys_do_not_fail(self):
        self.assertEqual(entry("[Desktop Entry]\nName=A\nName=B\n")["Name"], "B")


class IsVisiblePanelTest(unittest.TestCase):

    def test_requires_settings_panel_category(self):
        self.assertTrue(gs._is_visible_panel({"Categories": "Settings;X-GNOME-Settings-Panel;"}, {"gnome"}))
        self.assertFalse(gs._is_visible_panel({"Categories": "Settings;"}, {"gnome"}))
        self.assertFalse(gs._is_visible_panel({}, {"gnome"}))

    def test_category_must_match_exactly(self):
        self.assertFalse(gs._is_visible_panel({"Categories": "X-GNOME-Settings-PanelFoo;"}, {"gnome"}))

    def test_hidden_entries(self):
        e = {"Categories": "X-GNOME-Settings-Panel;", "Hidden": "True"}
        self.assertFalse(gs._is_visible_panel(e, {"gnome"}))
        e["Hidden"] = "false"
        self.assertTrue(gs._is_visible_panel(e, {"gnome"}))

    def test_respects_desktop_restrictions(self):
        e = {"Categories": "X-GNOME-Settings-Panel;", "OnlyShowIn": "ubuntu;"}
        self.assertTrue(gs._is_visible_panel(e, {"ubuntu", "gnome"}))
        self.assertFalse(gs._is_visible_panel(e, {"gnome"}))


class ExecCommandTest(unittest.TestCase):

    def test_plain_command(self):
        self.assertEqual(gs._exec_command({"Exec": "gnome-control-center system about"}),
                         ["gnome-control-center", "system", "about"])

    def test_field_codes_are_removed(self):
        self.assertEqual(gs._exec_command({"Exec": "app %U --flag %f"}), ["app", "--flag"])

    def test_quoted_arguments(self):
        self.assertEqual(gs._exec_command({"Exec": '"/opt/my app/bin" "two words"'}),
                         ["/opt/my app/bin", "two words"])

    def test_missing_or_empty(self):
        self.assertEqual(gs._exec_command({}), [])
        self.assertEqual(gs._exec_command({"Exec": ""}), [])

    def test_unbalanced_quotes(self):
        self.assertEqual(gs._exec_command({"Exec": 'app "unterminated'}), [])


class LocalizedTest(unittest.TestCase):

    def test_most_specific_inline_translation_wins(self):
        e = {"Name": "Color", "Name[en]": "Colour (en)", "Name[en_GB]": "Colour"}
        self.assertEqual(gs._localized(e, "Name", None, ["en_GB", "en"]), ("Color", "Colour"))
        self.assertEqual(gs._localized(e, "Name", None, ["en_AU", "en"]), ("Color", "Colour (en)"))

    def test_inline_translation_wins_over_gettext(self):
        e = {"Name": "Sound", "Name[de]": "Klang"}
        with mock.patch.object(gs.gettext, "dgettext", return_value="Ton") as dgettext:
            self.assertEqual(gs._localized(e, "Name", "domain", ["de"]), ("Sound", "Klang"))
        dgettext.assert_not_called()

    def test_gettext_domain(self):
        with mock.patch.object(gs.gettext, "dgettext", return_value="Ton") as dgettext:
            self.assertEqual(gs._localized({"Name": "Sound"}, "Name", "gcc", ["de"]), ("Sound", "Ton"))
        dgettext.assert_called_once_with("gcc", "Sound")

    def test_no_translation(self):
        self.assertEqual(gs._localized({"Name": "Sound"}, "Name", None, ["de"]), ("Sound", "Sound"))

    def test_missing_key_is_not_looked_up_in_gettext(self):
        # dgettext("") returns the catalog's header, which must never end up as a name
        with mock.patch.object(gs.gettext, "dgettext", return_value="Project-Id-Version: ...") as dgettext:
            self.assertEqual(gs._localized({}, "Comment", "gcc", ["de"]), ("", ""))
        dgettext.assert_not_called()


class MergeKeywordsTest(unittest.TestCase):

    def test_order_and_duplicates(self):
        self.assertEqual(gs._merge_keywords("Ton;Lautstärke;Audio;", "Sound;Volume;Audio;"),
                         ["Ton", "Lautstärke", "Audio", "Sound", "Volume"])

    def test_blanks_and_whitespace(self):
        self.assertEqual(gs._merge_keywords(" a ; ;b;;", ""), ["a", "b"])

    def test_nothing(self):
        self.assertEqual(gs._merge_keywords(), [])


class PanelFromEntryTest(EnvTestCase):

    def test_fields(self):
        panel = gs._panel_from_entry("gnome-sound-panel", entry(SOUND_PANEL), [])
        self.assertEqual(panel.panel_id, "gnome-sound-panel")
        self.assertEqual(panel.name, "Sound")
        self.assertEqual(panel.comment, "Change sound levels, inputs, outputs, and alert sounds")
        self.assertEqual(panel.icon_name, "org.gnome.Settings-sound-symbolic")
        self.assertEqual(panel.command, ["gnome-control-center", "sound"])
        self.assertEqual(panel.keywords, ["Card", "Microphone", "Volume", "Fade", "Balance",
                                          "Bluetooth", "Headset", "Audio", "Output", "Input"])

    def test_no_command(self):
        self.assertIsNone(gs._panel_from_entry("p", entry("[Desktop Entry]\nName=P\n"), []))

    def test_missing_optional_keys(self):
        panel = gs._panel_from_entry("p", entry("[Desktop Entry]\nName=P\nExec=p\n"), [])
        self.assertEqual((panel.comment, panel.icon_name, panel.keywords), ("", "", []))

    def test_translated_and_untranslated_keywords_are_searchable(self):
        e = entry("""\
            [Desktop Entry]
            Name=Sound
            Exec=gnome-control-center sound
            Keywords=Volume;Audio;
            Keywords[de]=Lautstärke;Audio;
            """)
        self.assertEqual(gs._panel_from_entry("p", e, ["de"]).keywords, ["Lautstärke", "Audio", "Volume"])

    def test_ubuntu_gettext_domain_wins_over_gnome_one(self):
        e = entry("""\
            [Desktop Entry]
            Name=Sound
            Exec=gnome-control-center sound
            X-GNOME-Gettext-Domain=gnome
            X-Ubuntu-Gettext-Domain=ubuntu
            """)
        with mock.patch.object(gs.gettext, "dgettext", side_effect=lambda d, s: f"{d}:{s}"):
            self.assertEqual(gs._panel_from_entry("p", e, []).name, "ubuntu:Sound")

    def test_gnome_gettext_domain(self):
        e = entry("[Desktop Entry]\nName=Sound\nExec=x\nX-GNOME-Gettext-Domain=gnome\n")
        with mock.patch.object(gs.gettext, "dgettext", side_effect=lambda d, s: f"{d}:{s}"):
            self.assertEqual(gs._panel_from_entry("p", e, []).name, "gnome:Sound")


class LoadPanelsTest(XdgTestCase):

    def ids(self):
        return [p.panel_id for p in gs.load_panels()]

    def test_sorted_case_insensitively_by_name(self):
        self.panel(self.system, "wifi", "Wi-Fi")
        self.panel(self.system, "about", "about")
        self.panel(self.system, "sound", "Sound")
        self.assertEqual([p.name for p in gs.load_panels()], ["about", "Sound", "Wi-Fi"])

    def test_id_is_the_desktop_file_name(self):
        self.panel(self.system, "sound", "Sound")
        self.assertEqual(self.ids(), ["gnome-sound-panel"])

    def test_skips_non_panels(self):
        self.panel(self.system, "sound", "Sound")
        self.write(self.system, "org.gnome.Nautilus.desktop",
                   "[Desktop Entry]\nName=Files\nExec=nautilus\nCategories=GNOME;Utility;\n")
        self.assertEqual(self.ids(), ["gnome-sound-panel"])

    def test_skips_hidden_panels(self):
        self.panel(self.system, "sound", "Sound", Hidden="true")
        self.assertEqual(self.ids(), [])

    def test_skips_panels_for_other_desktops(self):
        self.panel(self.system, "ubuntu", "Ubuntu Desktop", OnlyShowIn="ubuntu;")
        self.panel(self.system, "kde", "KDE only", OnlyShowIn="KDE;")
        self.assertEqual(self.ids(), ["gnome-ubuntu-panel"])
        self.set_env(XDG_CURRENT_DESKTOP="GNOME")
        self.assertEqual(self.ids(), [])

    def test_skips_panels_without_command(self):
        self.panel(self.system, "sound", "Sound", Exec=None)
        self.assertEqual(self.ids(), [])

    def test_skips_unreadable_files(self):
        self.panel(self.system, "sound", "Sound")
        (self.system / "applications/broken.desktop").write_bytes(b"\xff\xfe garbage")
        self.assertEqual(self.ids(), ["gnome-sound-panel"])

    def test_user_file_shadows_system_panel(self):
        self.panel(self.system, "sound", "Sound")
        self.panel(self.home, "sound", "Sound", Hidden="true")
        self.assertEqual(self.ids(), [])

    def test_uses_locale(self):
        self.panel(self.system, "sound", "Sound", **{"Name[de]": "Klang"})
        self.assertEqual([p.name for p in gs.load_panels()], ["Sound"])
        self.set_env(LANG="de_DE.UTF-8")
        self.assertEqual([p.name for p in gs.load_panels()], ["Klang"])


class PanelTest(EnvTestCase):

    def make(self, **kwargs):
        args = dict(panel_id="gnome-sound-panel", name="Sound", comment="Change sound levels",
                    icon_name="org.gnome.Settings-sound-symbolic",
                    command=["gnome-control-center", "sound"], keywords=["Volume", "Audio"])
        return gs.Panel(**{**args, **kwargs})

    def test_texts(self):
        panel = self.make()
        self.assertEqual(panel.id(), "gnome-sound-panel")
        self.assertEqual(panel.text(), "Sound")
        self.assertEqual(panel.subtext(), "Change sound levels")
        self.assertEqual(panel.inputActionText(), "Sound")

    def test_subtext_without_comment(self):
        self.assertEqual(self.make(comment="").subtext(), "GNOME Settings panel")

    def test_icon_is_the_panel_icon_on_a_light_tile(self):
        kind, inner, brush = self.make().icon()
        self.assertEqual(kind, "iconified")
        self.assertEqual(inner, ("theme", "org.gnome.Settings-sound-symbolic"))
        self.assertIsInstance(brush, fake_albert.Brush)
        self.assertEqual((brush.color.r, brush.color.g, brush.color.b), (240, 240, 240))

    def test_tile_brush_is_shared(self):
        self.assertIs(self.make().icon()[2], self.make(panel_id="other").icon()[2])

    def test_icon_without_icon_name_is_the_settings_app_icon(self):
        self.assertEqual(self.make(icon_name="").icon(), ("theme", "org.gnome.Settings"))

    def test_open_action_runs_the_command(self):
        actions = self.make().actions()
        self.assertEqual([(a.id, a.text) for a in actions], [("open", "Open")])
        self.assertEqual(fake_albert.detached_processes, [])
        actions[0].callable()
        self.assertEqual(fake_albert.detached_processes, [["gnome-control-center", "sound"]])

    def test_search_strings(self):
        self.assertEqual(self.make().search_strings(),
                         ["Sound", "Volume", "Audio", "Change sound levels"])
        self.assertEqual(self.make(comment="", keywords=[]).search_strings(), ["Sound"])


class PluginTest(XdgTestCase):

    def test_trigger_and_synopsis(self):
        plugin = gs.Plugin()
        self.assertEqual(plugin.defaultTrigger(), "gs ")
        self.assertEqual(plugin.synopsis(""), "<panel name or keyword>")

    def test_indexes_every_search_string_of_every_panel(self):
        self.panel(self.system, "sound", "Sound", Comment="Change sound levels", Keywords="Volume;")
        self.panel(self.system, "about", "About")
        plugin = gs.Plugin()
        plugin.updateIndexItems()
        self.assertEqual([(i.item.panel_id, i.string) for i in plugin.index_items], [
            ("gnome-about-panel", "About"),
            ("gnome-sound-panel", "Sound"),
            ("gnome-sound-panel", "Volume"),
            ("gnome-sound-panel", "Change sound levels"),
        ])
        self.assertIs(plugin.index_items[1].item, plugin.index_items[2].item)
        self.assertIn("Indexed 2 settings panels", fake_albert.debug_messages)

    def test_no_panels(self):
        plugin = gs.Plugin()
        plugin.updateIndexItems()
        self.assertEqual(plugin.index_items, [])


class MetadataTest(unittest.TestCase):

    def test_albert_metadata(self):
        self.assertEqual(gs.md_iid, "5.0")
        self.assertEqual(gs.md_name, "GNOME Settings")
        self.assertEqual(gs.md_bin_dependencies, ["gnome-control-center"])
        self.assertEqual(gs.md_platforms, ["Linux"])


@unittest.skipUnless(Path("/usr/share/applications/gnome-sound-panel.desktop").exists(),
                     "GNOME Settings is not installed")
class InstalledPanelsTest(unittest.TestCase):
    """Smoke test against the panels installed on this system."""

    def test_installed_panels_load(self):
        with mock.patch.dict(os.environ, {"XDG_DATA_DIRS": "/usr/share", "XDG_DATA_HOME": "/nonexistent",
                                          "XDG_CURRENT_DESKTOP": "GNOME", "LANG": "C"}):
            panels = {p.panel_id: p for p in gs.load_panels()}
        self.assertIn("gnome-sound-panel", panels)
        self.assertEqual(panels["gnome-sound-panel"].command, ["gnome-control-center", "sound"])
        for panel in panels.values():
            with self.subTest(panel=panel.panel_id):
                self.assertTrue(panel.name)
                self.assertTrue(panel.command)


if __name__ == "__main__":
    unittest.main()
