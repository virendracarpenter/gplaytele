# Project Structure

```
gplaytele/
├── .github/
│   └── workflows/
│       ├── 32bit.yml       # 32-bit BGMI download & upload (device: sm_j5_prime)
│       └── 64bit.yml       # 64-bit BGMI download & upload (device: px_7a)
├── .kiro/
│   └── steering/           # AI assistant steering rules
├── .vscode/
│   └── settings.json       # Editor settings
├── .gitignore              # Python, IDE, and build artifact ignores
└── README.md
```

## Architecture Notes
- This is a configuration-driven project with no application source code.
- All logic lives in GitHub Actions workflow YAML files under `.github/workflows/`.
- Python code is embedded inline within workflow steps (not in standalone `.py` files).
- The two workflows are nearly identical, differing only in device profile (32-bit vs 64-bit) and upload caption.
- Workflow timeout is set to 60 minutes.
- File verification step ensures the APK exists before attempting upload.
