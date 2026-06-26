# OSELIA brand assets (for the Home Assistant brands repo)

These PNGs fix the **device-page / integrations-list logo** for the OSELIA custom
integration. HA loads integration brand images from the central
`https://brands.home-assistant.io` CDN, not from a local integration — so until these
are merged there, HA shows a broken-image placeholder for the `oselia` domain. There is
**no local override**; submitting these is the only way to get the logo on the device
page. (The dashboard logo, by contrast, is embedded directly and already works.)

Generated from the hearth logo SVG in the [firmware repo](https://github.com/vmyronovych/oselia-hearth-di16g-firmware/blob/main/homeassistant/hearth_logo.svg)
(the hearth mark for `icon`, the full lockup for
`logo`), transparent background:

```
custom_integrations/oselia/
  icon.png      256x256   square hearth mark
  icon@2x.png   512x512
  logo.png      512x273   full OSELIA lockup (mark + wordmark + tagline)
  logo@2x.png   1024x546
```

## Submitting

1. Fork `home-assistant/brands`.
2. Copy this `custom_integrations/oselia/` folder into the repo root's
   `custom_integrations/`.
3. Open a PR. CI checks sizes/transparency (icons must be square; these comply).
4. Once merged, HA shows the OSELIA logo on the device page and integrations list — no
   integration change needed.

Regenerate (if the SVG changes) with headless Chrome — see the project chat history /
`dashboards/generate.py` sibling tooling for the render commands.
