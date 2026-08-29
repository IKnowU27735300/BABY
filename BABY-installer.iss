; BABY — Windows Installer
; Compile: "C:\Users\anish\AppData\Local\Programs\Inno Setup 6\ISCC.exe" BABY-installer.iss

#define MyAppName "BABY"
#define MyAppVersion "1.0.0"
#define MyAppExeName "BABY.exe"
#define MyAppId "{{8E0B2A54-6B1F-4E8A-9C3D-BABY0A1B2C3D}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=BABY
DefaultDirName={localappdata}\Programs\BABY
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=BABY-Setup-x64
SetupIconFile={#SourcePath}dist\BABY.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/fast
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup"; Description: "Start BABY automatically when I sign in to Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "BUILD\BABY\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: ""
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install-startup"; StatusMsg: "Registering BABY to start with Windows..."; Flags: runhidden nowait; Tasks: startup
Filename: "{app}\{#MyAppExeName}"; Description: "Launch BABY now"; Flags: nowait postinstall skipifsilent




