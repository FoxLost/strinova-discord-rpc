@echo off
echo Initializing Git...
if not exist .git (
    git init
    echo Initialized empty Git repository
) else (
    echo Git repository already initialized
)

echo Adding files...
git add .
git commit -m "Initial commit of Strinova Discord RPC v1.0.0" 2>nul
git branch -M main

echo Configuring Remote...
git remote remove origin 2>nul
git remote add origin https://github.com/FoxLost/strinova-discord-rpc.git

echo Creating Tag v1.0.0...
git tag v1.0.0 2>nul

echo Pushing to GitHub...
echo Note: If prompted, please enter your GitHub username and Personal Access Token (or password).
git push -u origin main
git push origin v1.0.0

echo Done!
pause
