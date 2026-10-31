# Harmoni Agent update release contract

The desktop app checks `https://api.github.com/repos/Mahfud-PG/harmoni-agent/releases/latest` only after the user opts in (or manually presses **Periksa Pembaruan**). It never silently installs anything.

For each stable release, tag it `vX.Y.Z` and attach exactly these two release assets:

- `HarmoniAgent-Setup.exe` (Windows installer)
- `update-manifest.json` containing `{"version":"X.Y.Z","asset":"HarmoniAgent-Setup.exe","sha256":"<64 lowercase hexadecimal characters>"}`

Compute SHA-256 **from the final installer bytes** before uploading, e.g. `sha256sum HarmoniAgent-Setup.exe`. Keep `APP_VERSION` in `app_desktop.py` aligned with the installed release and update the installer version to match. Never publish a manifest with a placeholder hash. No private key, token, or API secret belongs in a release asset.

The downloaded installer is staged under `%APPDATA%\HarmoniAgent\updates\X.Y.Z\`, checked against the manifest SHA-256, and rechecked immediately before launch. The user must confirm both download and installer launch. The updater never terminates processes; the native installer handles any subsequent application-restart requirements. This protects against accidental/corrupt downloads, **not** against a compromised GitHub release account or malicious release manifest; release publication access must be secured independently.
