; Installateur Inno Setup — TICTAC Studio Regie
; La version est injectée par Build-Release.ps1 via /DMyAppVersion=...
; (fallback ci-dessous si compilation manuelle).

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif

#define MyAppName "TICTAC Studio Regie"
#define MyAppPublisher "STICK RDC SARLU"
#define MyAppURL "https://tictachebdo.cd"
#define MyAppExeName "TICTAC-Studio-Regie.exe"

#ifndef MyAppSourceDir
  #define MyAppSourceDir "..\dist"
#endif

#ifndef MyOutputDir
  #define MyOutputDir "..\dist\installer"
#endif

[Setup]
AppId={{8F3C2A1B-9D4E-4B6A-A7C1-2E5F8D0B91A3}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\TICTAC-Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#MyOutputDir}
OutputBaseFilename=TICTAC-Studio-Regie-Setup-{#MyAppVersion}
SetupIconFile=
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x86compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Même AppId → MAJ in-place sur une ancienne install (pas de 2e entrée Programmes).
CloseApplications=yes
UsePreviousAppDir=yes
UninstallDisplayName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (C) STICK RDC SARLU
ShowLanguageDialog=no
InfoBeforeFile=welcome-fr.txt

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
french.WelcomeLabel1=Bienvenue dans l'assistant d'installation de [name]
french.WelcomeLabel2=Ceci installera [name/ver] sur votre ordinateur.%n%nVersion du produit : {#MyAppVersion}%nÉditeur : {#MyAppPublisher}%n%nIl est recommandé de fermer toutes les autres applications avant de continuer.

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"; Flags: unchecked

[Files]
Source: "{#MyAppSourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeWizard(): Boolean;
begin
  Result := True;
  WizardForm.WelcomeLabel2.Caption :=
    'Ceci installera ' + ExpandConstant('{#MyAppName}') + ' sur votre ordinateur.' + #13#10 + #13#10 +
    'Version du produit : ' + ExpandConstant('{#MyAppVersion}') + #13#10 +
    'Éditeur : ' + ExpandConstant('{#MyAppPublisher}') + #13#10 + #13#10 +
    'Il est recommandé de fermer toutes les autres applications avant de continuer.';
end;
