---
name: integration-release-rollout
description: >-
  Attach the right bilingual end-user rollout note whenever a PR or GitHub Release for this
  repo changes the OSELIA Home Assistant integration (a diff under custom_components/oselia/**
  or a new release). The integration updates via HACS, so the note is short — update in HACS
  and restart HA. Adapted from the oselia-waveshare-relay-ha "blueprint-release-rollout"
  skill. Use when asked to "open a PR" / "cut a release" / "write release notes" / "draft the
  PR body" and the diff touches custom_components/**, or when reminding a user what to do
  after an integration update.
---

# Integration release rollout

This is the **OSELIA Hearth Home Assistant integration** (domain `oselia`). It updates via
**HACS**: HACS polls this repo's GitHub Releases, offers a one-click update, and **HA
restarts** to load the new Python (`RELEASING.md`). HACS is to this component what OTA is to
the gateway firmware — and the integration also provides the firmware `update` card, but the
*firmware* itself ships separately from the firmware repo.

**Lead with the consumer, then go technical.** Every PR body and release note must be
ordered **non-technical first**: open with a plain-language description of *the problem this
release solves for the user* and the outcome they get (no jargon, no file names), then the
how-to-apply link — and only **after** that, a separate `## Technical details` section
(summary of changes, verification) for engineers. The bilingual rollout blocks below are the
consumer-first part and go at the **top**; the technical detail goes underneath.

What the consumer-first rollout note must convey:

- **The problem and the outcome in plain words** — what was wrong / what gets better, framed
  for a homeowner or installer, not a developer.
- **Update *OSELIA Hearth* in HACS, then restart Home Assistant when prompted. That's it** —
  the restart is mandatory (HACS swaps the files; HA loads the new code on restart). The
  device, entities, and automations come back automatically afterwards; nothing to re-enter.
- **Your setup is safe.** The config entry, device, and per-unit settings are preserved
  across an integration update.

## Required layout (do not drop any of these)

The rollout section the user receives **must**:

1. Come **first**, at the top of the PR body / release notes (before any technical
   section). It is the consumer-facing part.
2. Be **two root-level collapsible `<details>` blocks, one per language, Ukrainian first**
   (`<details open>`) and English second (`<details>`). GitHub-Flavored Markdown has no
   tabs; `<details>` is the native equivalent. There is **no** shared summary outside the
   blocks — a reader opens one block and has everything in their language.
3. Contain, in each block: (a) the release's **plain-language problem + outcome** in that
   language (what gets better for the user, no jargon), then (b) a **link to `UPGRADING.md`**
   for how to apply. The how-to-apply *steps* are not repeated in the note — they live in
   the canonical `UPGRADING.md`. **Every release note and PR body must carry this link.**
4. Be followed by a `## Technical details` section (summary of changes + verification) for
   engineers — never above the consumer blocks.

`rollout-snippet.md` encodes this; fill only `<SUMMARY_UA>` / `<SUMMARY_EN>` with the
per-release plain-language problem + outcome in each language. If you edit the snippet,
preserve the layout and the upgrade-guide link.

## What to do

When the diff (PR) or the release contents (since the previous tag) change the integration
(touch `custom_components/oselia/**`):

1. Confirm it: `git diff --name-only <base>..<head> -- 'custom_components/**'` (PR) or
   `git diff --name-only <prev_tag>..<new_tag> -- 'custom_components/**'` (release).
2. Take the canonical text from [`rollout-snippet.md`](rollout-snippet.md) and fill only
   `<SUMMARY_UA>` / `<SUMMARY_EN>` (the plain-language problem + outcome in each language).
   Paste it **whole** — it already is the two `<details>` blocks plus the `UPGRADING.md`
   link.
   - **PR body:** paste the filled snippet as its own section, first.
   - **Release notes:** paste it into the body (`gh release create --generate-notes` won't
     add it — append it yourself, or `gh release edit vX.Y.Z --notes-file …`).
3. If the release changes *how updates work* (not just this fix), update **`UPGRADING.md`**
   too — it is the single source of the apply steps every release links to.

## Keep it consistent

`rollout-snippet.md` is the single source of the user-facing wording — edit it there, not
inline, so PR bodies and release notes never drift. This mirrors the human-facing
`RELEASING.md` (release-engineer-facing) and `UPGRADING.md` (end-user-facing).
