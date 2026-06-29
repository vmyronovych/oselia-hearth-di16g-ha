# Applying an update · Як застосувати оновлення

The canonical guide for updating the **OSELIA Hearth** Home Assistant integration. Every
release links here. The integration updates through **HACS** — for most people it's two
clicks and a restart.

> **Integration vs firmware.** This guide is for the **HA integration** (the Python
> component, updated via HACS). The gateway's **firmware** updates separately, over-the-air,
> from its own [firmware repo](https://github.com/vmyronovych/oselia-hearth-di16g-firmware) —
> that's the **Install** button on the device's firmware *update* card, not HACS.

<details open>
<summary><b>🇺🇦 Українською</b></summary>

<br>

### 1. Оновіть інтеграцію
HACS → відкрийте **OSELIA Hearth** → **Update / Download** (або ⋮ → **Redownload**).

### 2. Перезапустіть Home Assistant
Коли HA попросить — **перезапустіть** його. Це обов'язково: HACS лише підміняє файли, а нову
версію коду HA завантажує під час перезапуску (на відміну від прошивки «по повітрю», до
перезапуску нічого не змінюється).

### 3. Більше нічого робити не треба
Після перезапуску ваш пристрій, сутності й автоматизації повертаються автоматично. Налаштування
інтеграції (запис конфігурації, параметри пристрою) зберігаються — вводити заново нічого не
потрібно.

### 4. Бета-версії (необов'язково)
Щоб отримувати попередні версії, увімкніть **Show beta versions** у меню ⋮ репозиторію в HACS.

### Перевірка
HACS показує нову версію; пристрій **OSELIA Hearth** і його сутності (зокрема картка
оновлення прошивки `update.hearth_<id>_firmware`) на місці після перезапуску.

</details>

<details>
<summary><b>🇬🇧 English</b></summary>

<br>

### 1. Update the integration
HACS → open **OSELIA Hearth** → **Update / Download** (or ⋮ → **Redownload**).

### 2. Restart Home Assistant
When HA prompts you, **restart** it. This is required: HACS only swaps the files; HA loads
the new code on restart (unlike over-the-air firmware, nothing changes until then).

### 3. Nothing else to do
After the restart your device, entities, and automations come back automatically. The
integration's settings (config entry, device options) are preserved — there's nothing to
re-enter.

### 4. Betas (optional)
To receive prereleases, enable **Show beta versions** in the repository's ⋮ menu in HACS.

### Verify
HACS shows the new version; the **OSELIA Hearth** device and its entities (including the
firmware update card `update.hearth_<id>_firmware`) are present after the restart.

</details>
