; CRYPTO NOCTURNE v4.5.1 - Windows installer (Inno Setup 6)
; Source: generated PyInstaller ONEDIR bundle, never raw wallet data.
#define AppName "CRYPTO NOCTURNE"
#define AppVersion "4.5.1"
#define ExeName "CRYPTO_NOCTURNE.exe"

[Setup]
AppId={{DC6E2F6D-11DA-4E4E-AE51-3DBEC5B40CE2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher=CRYPTO NOCTURNE Project
DefaultDirName={localappdata}\Programs\CRYPTO NOCTURNE
DefaultGroupName=CRYPTO NOCTURNE
UninstallDisplayIcon={app}\{#ExeName}
OutputDir=..\release
OutputBaseFilename=CRYPTO_NOCTURNE_Setup_v{#AppVersion}
SetupIconFile=brand_assets\CRYPTO_NOCTURNE.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=yes
; Data protection: never delete user data on uninstall.
; User-created vaults/ledgers are outside {app}; installer never modifies them.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Recursively copy the entire signed-off onedir bundle, not project source files.
Source: "..\dist\CRYPTO_NOCTURNE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CRYPTO NOCTURNE"; Filename: "{app}\{#ExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#ExeName}"
Name: "{autodesktop}\CRYPTO NOCTURNE"; Filename: "{app}\{#ExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch CRYPTO NOCTURNE"; Flags: nowait postinstall skipifsilent
