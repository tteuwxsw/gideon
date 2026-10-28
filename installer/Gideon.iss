#define MyAppName "Gideon"
#define MyAppVersion "0.4.6"
#define MyAppPublisher "tteuwxsw"
#define MyAppExeName "Gideon.exe"

[Setup]
AppId={{D75F43A4-BBF7-44E8-9922-F162955DC8DE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Gideon
DefaultGroupName=Gideon
PrivilegesRequired=lowest
DisableDirPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=GideonSetup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Files]
Source: "..\dist\Gideon\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\GideonWake.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\GideonUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dados\modelos\vosk-model-small-pt-0.3\*"; DestDir: "{localappdata}\Gideon\dados\modelos\vosk-model-small-pt-0.3"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist
Source: "..\dist\GideonCtl.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\packaging\gideon.cmd"; DestDir: "{localappdata}\Microsoft\WindowsApps"; Flags: ignoreversion; Tasks: commandline

[InstallDelete]
Type: files; Name: "{localappdata}\Gideon\dados\captura_avatar.png"
Type: files; Name: "{app}\_internal\gideon\web\gideon-cgi.webp"

Type: files; Name: "{userstartup}\Gideon Wake.lnk"
[Icons]
Name: "{group}\Gideon"; Filename: "{app}\Gideon.exe"; Parameters: "--open"; WorkingDir: "{app}"
Name: "{userdesktop}\Gideon"; Filename: "{app}\Gideon.exe"; Parameters: "--open"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "autostart"; Description: "Iniciar o subsistema Gideon ao entrar no Windows (usa o microfone para a palavra de ativacao)"; GroupDescription: "Integracao com o Windows:"; Flags: checkedonce
Name: "commandline"; Description: "Instalar o comando 'gideon' para Windows Terminal e PowerShell"; GroupDescription: "Integracao com o Windows:"; Flags: checkedonce

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Gideon"; ValueData: """{app}\GideonWake.exe"" --headless"; Flags: uninsdeletevalue; Tasks: autostart
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Gideon"; Flags: deletevalue; Tasks: not autostart

[Run]
Filename: "{app}\Gideon.exe"; Parameters: "--self-test"; StatusMsg: "Validando a instalacao da Gideon..."; Flags: runhidden waituntilterminated
Filename: "{app}\GideonWake.exe"; Parameters: "--headless"; Description: "Iniciar o nucleo Gideon"; Flags: nowait postinstall skipifsilent; Tasks: autostart

[UninstallRun]
Filename: "{app}\GideonWake.exe"; Parameters: "--stop"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "StopWake"
Filename: "{app}\GideonCtl.exe"; Parameters: "stop --wait --timeout 30"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "StopCore"

[Code]
var
  LegacyBackupDir: String;

function CopyDirectoryTree(const SourceDir, DestDir: String): Boolean;
var
  FindRec: TFindRec;
  SourcePath, DestPath: String;
begin
  Result := True;
  if not DirExists(SourceDir) then
    exit;
  ForceDirectories(DestDir);
  if FindFirst(AddBackslash(SourceDir) + '*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          SourcePath := AddBackslash(SourceDir) + FindRec.Name;
          DestPath := AddBackslash(DestDir) + FindRec.Name;
          if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then
            Result := Result and CopyDirectoryTree(SourcePath, DestPath)
          else if (CompareText(FindRec.Name, 'runtime.json') <> 0) and
                  (CompareText(FindRec.Name, 'reiniciar.solicitado') <> 0) and
                  (CompareText(FindRec.Name, 'atualizar.solicitado') <> 0) and
                  (CompareText(FindRec.Name, 'gideon_background.log') <> 0) then
          begin
            ForceDirectories(ExtractFileDir(DestPath));
            if not FileExists(DestPath) then
              Result := Result and CopyFile(SourcePath, DestPath, False);
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  LegacyPython, LegacyData, NewData: String;
begin
  Result := '';
  LegacyPython := ExpandConstant('{app}\.venv\Scripts\python.exe');
  LegacyData := ExpandConstant('{app}\dados');
  NewData := ExpandConstant('{localappdata}\Gideon\dados');

  if FileExists(ExpandConstant('{app}\GideonWake.exe')) then
    Exec(ExpandConstant('{app}\GideonWake.exe'), '--stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if FileExists(ExpandConstant('{app}\GideonCtl.exe')) then
    Exec(ExpandConstant('{app}\GideonCtl.exe'), 'stop --wait --timeout 30', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
  else if FileExists(ExpandConstant('{app}\Gideon.exe')) then
    Exec(ExpandConstant('{app}\Gideon.exe'), '--stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if FileExists(LegacyPython) then
    Exec(LegacyPython, '-m gideon.supervisor --stop', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if DirExists(ExpandConstant('{app}\.git')) then
  begin
    if not CopyDirectoryTree(LegacyData, NewData) then
    begin
      Result := 'Nao foi possivel preservar todos os dados da instalacao anterior.';
      exit;
    end;
    LegacyBackupDir := ExpandConstant('{localappdata}\Programs\Gideon.legacy-backup');
    if DirExists(LegacyBackupDir) then
    begin
      Result := 'Ja existe um backup legado em ' + LegacyBackupDir + '. Remova-o somente depois de conferir seus dados.';
      exit;
    end;
    if not RenameFile(ExpandConstant('{app}'), LegacyBackupDir) then
    begin
      Result := 'Nao foi possivel mover a instalacao antiga para backup.';
      exit;
    end;
  end;

  Exec(ExpandConstant('{cmd}'), '/C schtasks /Delete /TN "Gideon" /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
