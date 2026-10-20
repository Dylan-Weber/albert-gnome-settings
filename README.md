# GNOME Settings

Albert extension that searches GNOME Settings panels by name, description and keywords — the same
data the GNOME Shell / Ubuntu launcher search uses — and opens the selected panel.

- Panels come from the `X-GNOME-Settings-Panel` desktop entries installed by
  `gnome-control-center`, so the list follows the installed version (and `OnlyShowIn` rules).
- Names and keywords are translated (inline `Name[xx]` or the Ubuntu gettext domain).
- Results show in the global query and under the `gs ` trigger.

## Install

```sh
ln -s "$PWD" ~/.local/share/albert/python/plugins/gnome_settings
```

Then enable *GNOME Settings* under Albert → Settings → Plugins → Python.
