# Minecraft Server Manager

A polished desktop tool for running and managing your own Minecraft server from a Windows PC.

## Why this project is useful
- Start, stop, and restart your server from one place
- Choose server type and Minecraft version easily
- Manage plugins, mods, and console output
- Detect Java automatically and help you set up everything needed
- Works well for local hosting so you can run your own server at home

## Main features
- Select a server folder and profile
- Detect or configure Java runtime
- Create base server files such as `server.properties`, `eula.txt`, and `ops.json`
- Add or remove plugin and mod jars
- Start and stop the server with live console output
- Save settings and profiles for quick reuse

## Project layout
- `app.py` – main GUI and server management logic
- `config/settings.json` – saved settings and profiles
- `scripts/setup_windows.ps1` – installs Python, Java, and dependencies if needed
- `scripts/run_server_manager.bat` – easy launcher for Windows
- `dist/app.exe` – packaged executable (if built)

## Quick start on Windows
1. Download or clone this repository.
2. Open PowerShell in the project folder.
3. Run the setup script once:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
   ```
4. After setup, launch the app with:
   ```powershell
   py app.py
   ```
5. Or simply double-click `scripts/run_server_manager.bat`.

## What the setup script does
The setup script will:
- check if Python is installed
- install Python if it is missing
- check Java and install Java 21 if needed
- install required Python packages
- prepare the project so it can run immediately

## Recommended setup for hosting a server
For Paper/Purpur-style servers, Java 21+ is recommended.
If Java is already installed, the app will try to detect it automatically.

## Build your own EXE (optional)
If you want to package the app into a downloadable Windows executable:

```powershell
py -m pip install pyinstaller
pyinstaller --onefile --noconsole app.py
```

The output executable will be created in the `dist` folder.

## Notes for GitHub users
When this project is shared on GitHub, users can:
- download it as a ZIP
- run the setup script once
- launch the application locally
- host their own Minecraft server on their own PC

This makes the project easy to distribute and simple for other users to run without needing advanced setup knowledge.
