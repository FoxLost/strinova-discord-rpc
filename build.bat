@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo Building EXE...
pyinstaller --clean --onefile --console --name "StrinovaRPC" main.py

echo Copying config files...
copy config.json dist\config.json
copy character_weapon_map.json dist\character_weapon_map.json
copy character_icons.json dist\character_icons.json

echo Build complete! Run dist\StrinovaRPC.exe
pause
