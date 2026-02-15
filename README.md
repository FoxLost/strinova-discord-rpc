# Strinova Discord RPC

A Python application that displays your current **Strinova** character and match status on Discord Rich Presence by reading weapon names from game screenshots via OCR.

![Strinova Discord RPC Demo](https://placehold.co/600x400?text=Strinova+Discord+RPC+Screenshot)

## Features

- **Character Detection**: Identifies your character based on the equipped weapon name (OCR).
- **Match Status**: Shows "In Match" with elapsed timer when objective is active.
- **Menu Detection**: Automatically resets status to "In Menu" when match ends.
- **Customizable**: Configurable screenshot regions, match duration, and display options.
- **Standalone**: Can be run as a portable `.exe` or Python script.

## Setup

### Prerequisites

1.  **Tesseract OCR** (Required for text recognition)
    -   Download & Install: [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
    -   Make sure to note the installation path (default: `C:\Program Files\Tesseract-OCR\tesseract.exe`)

2.  **Discord Developer Application** (For Rich Presence assets)
    -   Go to [Discord Developer Portal](https://discord.com/developers/applications)
    -   Create a new Application.
    -   Copy the **Application ID** (Client ID).
    -   Go to **Rich Presence > Art Assets**.
    -   Upload character icons with names matching `character_icons.json` (e.g., `galatea`, `lawine`, `strinova_logo`).

### Installation

1.  Download the latest release from the [Releases](https://github.com/yourusername/strinova-discord-rpc/releases) page.
2.  Extract the ZIP file.
3.  Edit `config.json` if needed:
    -   `discord.client_id`: Your Discord Application ID.
    -   `ocr.tesseract_path`: Path to your `tesseract.exe`.
    -   `regions`: Adjust screen coordinates if your resolution/UI scale differs (default 1920x1080).

### Usage

Run `StrinovaRPC.exe`. Keep the console window open to see logs.

## Configuration

-   `config.json`: Main settings.
-   `character_weapon_map.json`: Maps in-game weapon names to character names.
-   `character_icons.json`: Maps character names to Discord Asset Keys.

## Building from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Run directly
python main.py

# Build EXE
build.bat
```

## Troubleshooting

-   **Character not updating?** Check `config.json` → `regions.weapon_name` coordinates. If your resolution is different, take a screenshot and measure the fractional coordinates (0.0 to 1.0).
-   **Tesseract Error?** Ensure `tesseract_path` in `config.json` points to the correct executable.

## License

MIT License
