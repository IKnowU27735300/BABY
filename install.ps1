$ErrorActionPreference = "SilentlyContinue"
$dest = "$env:LOCALAPPDATA\BABY"
$build = "S:\CODE\BABY\dist\BABY"

Write-Host "=== BABY Installer ===" -ForegroundColor Cyan

# 1. Stop running instance
Write-Host "[1/6] Stopping BABY..." -ForegroundColor Yellow
Stop-Process -Name BABY -Force
Start-Sleep -Seconds 3

# 2. Backup biometric data
Write-Host "[2/6] Backing up biometric data..." -ForegroundColor Yellow
$backupDir = "$env:TEMP\BABY_biometric_backup"
Remove-Item -Recurse -Force $backupDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

$bioFiles = @(
    "$dest\data\biometrics.db",
    "$dest\data\.biometric.key"
)
foreach ($f in $bioFiles) {
    if (Test-Path $f) {
        $rel = $f.Substring($dest.Length)
        $targetDir = Join-Path $backupDir (Split-Path $rel -Parent)
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        Copy-Item -Force $f (Join-Path $backupDir $rel)
        Write-Host "  Backed up: $rel" -ForegroundColor Green
    }
}

# Also backup config
$configFile = "$dest\data\config.yaml"
if (Test-Path $configFile) {
    Copy-Item -Force $configFile "$backupDir\config.yaml"
    Write-Host "  Backed up: config.yaml" -ForegroundColor Green
}

# 3. Clean install directory (preserves nothing yet)
Write-Host "[3/6] Cleaning old files..." -ForegroundColor Yellow
Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 4. Copy new build (must copy _internal and BABY.exe separately to preserve structure)
Write-Host "[4/6] Copying new build..." -ForegroundColor Yellow
Copy-Item -Recurse -Force "$build\_internal" "$dest\_internal"
Copy-Item -Force "$build\BABY.exe" "$dest\BABY.exe"
Copy-Item -Force "S:\CODE\BABY\assets\BABY.ico" "$dest\BABY.ico"
Write-Host "  Copied to $dest" -ForegroundColor Green

# 5. Restore biometric data
Write-Host "[5/6] Restoring biometric data..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path "$dest\data" -Force | Out-Null

$restoredFiles = Get-ChildItem -Recurse -File $backupDir | Where-Object { $_.Name -ne "config.yaml" }
foreach ($f in $restoredFiles) {
    $rel = $f.FullName.Substring($backupDir.Length)
    $target = Join-Path $dest $rel
    $targetDir = Split-Path $target -Parent
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Copy-Item -Force $f.FullName $target
    Write-Host "  Restored: $rel" -ForegroundColor Green
}

# 6. Create shortcuts
Write-Host "[6/6] Creating shortcuts..." -ForegroundColor Yellow
$shell = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath("Desktop")
$shortcut = $shell.CreateShortcut("$desktop\BABY.lnk")
$shortcut.TargetPath = "$dest\BABY.exe"
$shortcut.IconLocation = "$dest\BABY.ico,0"
$shortcut.Save()

$startMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$shortcut2 = $shell.CreateShortcut("$startMenu\BABY.lnk")
$shortcut2.TargetPath = "$dest\BABY.exe"
$shortcut2.IconLocation = "$dest\BABY.ico,0"
$shortcut2.Save()
Write-Host "  Shortcuts created" -ForegroundColor Green

# 7. Verify biometric DB has admin
Write-Host "`n=== Verifying Admin Profile ===" -ForegroundColor Cyan
python -c "
import sqlite3, os
db = os.path.join(r'$dest', 'data', 'biometrics.db')
if not os.path.exists(db):
    print('  Biometric DB not found - will be created on first launch')
else:
    conn = sqlite3.connect(db)
    rows = conn.execute('SELECT id, name, is_admin FROM profiles WHERE is_admin=1').fetchall()
    conn.close()
    if rows:
        for r in rows:
            print(f'  Admin found: {r[1]} (id={r[0]}, admin={r[2]})')
    else:
        print('  No admin profile found - will need enrollment')
"

Write-Host "`n=== Install Complete ===" -ForegroundColor Green
Write-Host "Launch BABY from Desktop shortcut or Start Menu" -ForegroundColor Cyan




