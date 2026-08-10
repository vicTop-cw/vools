# Auto Discovery

Compiler auto-discovery and configuration module for vools.

## Status

- **Decorator:** N/A (utility module, not a language bridge)
- **LangType:** N/A
- **Async Support:** N/A
- **Dependencies:** N/A
- **Module Code:** N/A
- **Project Compilation:** N/A
- **Tests:** No dedicated test file

## Usage

```python
from vools.bridge.auto_discovery import discover_all

# Discover all installed compilers
result = discover_all()

# View available languages
print('Local:', result['local'].available_languages())

# View WSL languages
for wsl in result['wsl']:
    print(f'{wsl.host}:', wsl.available_languages())

# Print report
print(result['report'])
```

## Requirements

- Python 3.8+
- For WSL support: WSL must be installed and configured

## Notes

- `auto_discovery` is a utility module that discovers compilers on the local system and in WSL environments
- Not a language bridge — it assists with compiler configuration for other bridge modules
- Provides `discover_all()`, `discover_local()`, `discover_wsl()`, `get_discovery_report()`, and `configure_from_discovery()` functions