; Inno Setup 6 script - produces the client-facing Windows installer.
; Prerequisite: run packaging\build.ps1 first (creates backend\dist\AcademyManagement).
; Compile with:  iscc installer\setup.iss

#define AppName "Academy Management"
#define AppVersion "1.2.1"
#define AppExe "AcademyManagement.exe"

[Setup]
AppId={{7E2B4A31-9C55-4D8E-B1F2-3A6C0DE4F512}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=AcademyManagement-Setup-{#AppVersion}
OutputDir=..\dist-installer
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\backend\dist\AcademyManagement\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; WebView2 is preinstalled on Windows 10/11. For stripped machines, put
; MicrosoftEdgeWebView2Setup.exe next to this script and uncomment BOTH the
; [Files] entry and the [Run] line below:
;   [Files]  Source: "MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
; Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; \
;   StatusMsg: "Installation de WebView2..."; Flags: waituntilterminated
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The database in %APPDATA%\AcademyManagement is deliberately NOT deleted:
; the client's money records survive an uninstall.
