# Tech Stack & Build

## Platform
- GitHub Actions (CI/CD-only project, no local build system)

## Languages
- Python (inline scripts in workflow YAML for Telegram uploads)
- Bash (workflow shell steps)
- Rust (only for installing `apkeep` tool via Cargo)

## Key Dependencies
- `apkeep` — Rust CLI tool for downloading APKs from Google Play Store
- `pyrogram` — Python async Telegram client library
- `tgcrypto` — Encryption support for pyrogram

## Secrets (GitHub Secrets)
- `GOOGLE_EMAIL` / `AAS_TOKEN` — Google Play authentication
- `API_ID` / `API_HASH` / `TG_SESSION_STRING` / `TG_CHAT_ID` — Telegram API credentials

## Common Commands
There is no local build or test process. All execution happens in GitHub Actions:

```bash
# Install apkeep (done in CI)
cargo install apkeep

# Install Python deps (done in CI)
pip install pyrogram tgcrypto

# Download APK (requires credentials)
apkeep -a com.pubg.imobile -d google-play -o "device=px_7a,locale=en_IN,include_additional_files=true" -e "$GOOGLE_EMAIL" -t "$AAS_TOKEN" ./pubg_files
```

## Triggers
- Push to `production` branch
- Manual dispatch via GitHub Actions UI
- Scheduled cron (currently commented out)
