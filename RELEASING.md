# Releasing (GitHub → HACS)

This integration updates via **HACS** — it polls this repo's GitHub Releases and offers a
one-click update (then HA restarts). HACS is to this Python component what OTA is to the
gateway firmware.

## Versioning

- Releases use plain **`v*`** semver tags (e.g. `v0.2.0`).
- The **tag is the single source of version truth**: the `release` workflow stamps it into
  `custom_components/oselia/manifest.json`, so the committed manifest version is just a dev
  default and can't drift from what ships.
- `hacs.json` sets `zip_release` + `filename: oselia.zip`, so HACS installs the workflow's
  built asset (not the repo tree).

## Cut a release

1. Land your changes on `main` (the `Validate` workflow — hassfest + HACS action — runs on
   every PR).
2. Create a GitHub Release on a new `v*` tag — UI, or:
   ```sh
   gh release create v0.2.0 --generate-notes --title "v0.2.0"
   ```
3. The **`release` workflow** (`.github/workflows/release.yml`) fires on *release
   published*: it gates on `py_compile`, stamps the tag version into `manifest.json`, zips
   the component, and attaches **`oselia.zip`** to the release.

HACS reads the version from the manifest inside that zip, so what installs matches the tag.

## Distribution

- **Now:** users add this repo as a HACS *custom repository* (category: Integration).
- **Later:** PRs to [`hacs/default`](https://github.com/hacs/default) (HACS store, no manual
  URL) and [`home-assistant/brands`](https://github.com/home-assistant/brands) for the icon
  (assets in [`brands/`](brands/)).

## Notes

- **Beta channel:** mark a release as a *prerelease* (e.g. `v0.3.0-rc1`); HACS only offers
  prereleases to users who opt into betas for the repository.
- **Firmware vs integration:** gateway firmware ships separately from the
  [main project](https://github.com/vmyronovych/oselia) via its own OTA flow. If a firmware
  change alters the MQTT wire format or adds entities, cut a matching integration release
  (and mirror it in the provisioning tool there).
