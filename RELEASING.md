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

## Testing the update cycle

To verify the full GitHub → HACS → HA path end to end (the integration's analog of firmware
OTA). A version bump alone is enough — no code change is required.

1. **Note the installed version.** HACS → *OSELIA Hearth* shows the current version.
2. **Cut a test release** one patch above it (see *Cut a release* above), e.g.:
   ```sh
   gh release create v0.1.1 --generate-notes --title "v0.1.1"
   ```
3. **Verify the asset built.** The `release` workflow must finish and attach `oselia.zip`
   with the stamped version inside:
   ```sh
   gh run watch "$(gh run list --workflow=release.yml -L1 --json databaseId -q '.[0].databaseId')" --exit-status
   gh release view v0.1.1 --json assets -q '.assets[].name'   # -> oselia.zip
   ```
4. **Make HACS notice it.** HACS doesn't poll instantly — force it: HACS → top-right
   **⋮ → Update information** (or restart HA, which refreshes HACS on startup).
5. **Update.** *OSELIA Hearth* now shows **update available** → **Update/Download** →
   **restart Home Assistant** when prompted. The restart is mandatory: HACS only swaps the
   files; HA loads the new Python on restart (unlike firmware OTA, nothing happens until then).
6. **Confirm.** HACS shows the new version and the device + entities (including
   `update.hearth_<id>_firmware`) come back after the restart.

**Beta path:** to exercise the prerelease channel, cut the release as a *prerelease*
(`gh release create v0.2.0-rc1 --prerelease …`); HACS only offers it after you enable
**Show beta versions** for the repo (its ⋮ menu).

**Cleanup:** a pure cycle test bumps the public "latest". To roll it back, delete the test
release and tag (`gh release delete v0.1.1 --cleanup-tag`) so the previous release is latest
again.

## Distribution

- **Now:** users add this repo as a HACS *custom repository* (category: Integration).
- **Later:** PRs to [`hacs/default`](https://github.com/hacs/default) (HACS store, no manual
  URL) and [`home-assistant/brands`](https://github.com/home-assistant/brands) for the icon
  (assets in [`brands/`](brands/)).

## Notes

- **Beta channel:** mark a release as a *prerelease* (e.g. `v0.3.0-rc1`); HACS only offers
  prereleases to users who opt into betas for the repository.
- **Firmware vs integration:** gateway firmware ships separately from the
  [firmware repo](https://github.com/vmyronovych/oselia-hearth-di16g-firmware) via its own
  OTA flow. If a firmware change alters the MQTT wire format or adds entities, cut a matching
  integration release (and mirror it in the provisioning tool there).
