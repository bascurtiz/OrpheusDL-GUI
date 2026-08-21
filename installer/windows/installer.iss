
#define MyAppName "OrpheusDL GUI"
#include "version.iss"
#define MyAppPublisher "OrpheusDL"
#define MyAppURL "https://github.com/bascurtiz/orpheusdl-gui"
#define MyAppExeName "OrpheusDL_GUI.exe"
#define SourcePath "..\..\dist"
#define RepoDir "..\.."

[Setup]

AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
AppMutex=OrpheusDL-GUI-Mutex
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#MyAppName}

OutputDir=..\..\dist
OutputBaseFilename=OrpheusDL_GUI-Setup-{#MyAppVersion}
SetupIconFile=..\..\icon.ico
WizardImageFile=wizard_image.bmp
WizardSmallImageFile=wizard_small_image.bmp

Compression=lzma2
SolidCompression=yes

WizardStyle=modern
PrivilegesRequired=lowest

AllowNoIcons=yes
DisableProgramGroupPage=yes
CloseApplications=force
UpdateUninstallLogAppName=yes

[Types]

Name: "full"; Description: "Full installation"
Name: "compact"; Description: "Compact installation"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]

Name: "main"; Description: "OrpheusDL-GUI Core (required)"; Types: full compact custom; Flags: fixed

Name: "ffmpeg"; Description: "FFmpeg (Included - Recommended for conversions)"; Types: full custom; Flags: fixed
Name: "deno"; Description: "Deno (Required for YouTube module)"; Types: full custom; Flags: fixed

Name: "modules"; Description: "Music Platform Modules"; Types: full custom
Name: "modules\amazonmusic"; Description: "Amazon Music support"; Types: full custom
Name: "modules\applemusic"; Description: "Apple Music support"; Types: full custom
Name: "modules\beatport"; Description: "Beatport support"; Types: full custom
Name: "modules\deezer"; Description: "Deezer support"; Types: full custom
Name: "modules\musixmatch"; Description: "Musixmatch support"; Types: full custom
Name: "modules\lrclib"; Description: "LRCLIB support"; Types: full custom
Name: "modules\qobuz"; Description: "Qobuz support"; Types: full custom
Name: "modules\soundcloud"; Description: "SoundCloud support"; Types: full custom
Name: "modules\spotify"; Description: "Spotify support"; Types: full custom
Name: "modules\tidal"; Description: "Tidal support"; Types: full custom
Name: "modules\youtube"; Description: "YouTube support"; Types: full custom


[Tasks]

Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]

Source: "{#SourcePath}\{#MyAppExeName}"; DestDir: "{app}"; Components: main; Flags: ignoreversion

Source: "{#SourcePath}\config\settings.json"; DestDir: "{app}\config"; Components: main; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall
Source: "{#SourcePath}\config\cookies.txt"; DestDir: "{app}\config"; Components: main; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "{#SourcePath}\config\youtube-cookies.txt"; DestDir: "{app}\config"; Components: main; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "{#SourcePath}\config\*"; Excludes: "settings.json,cookies.txt,youtube-cookies.txt"; DestDir: "{app}\config"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

Source: "{#RepoDir}\orpheus\*"; DestDir: "{app}\orpheus"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#RepoDir}\utils\*"; DestDir: "{app}\utils"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#RepoDir}\orpheus.py"; DestDir: "{app}"; Components: main; Flags: ignoreversion skipifsourcedoesntexist

Source: "..\..\icon.ico"; DestDir: "{app}"; Components: main; Flags: ignoreversion
Source: "..\..\icon.png"; DestDir: "{app}"; Components: main; Flags: ignoreversion

Source: "..\..\platforms\*"; DestDir: "{app}\platforms"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

Source: "..\..\ffmpeg.exe"; DestDir: "{app}"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\..\ffprobe.exe"; DestDir: "{app}"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist

Source: "..\..\deno.exe"; DestDir: "{app}"; Components: deno; Flags: ignoreversion skipifsourcedoesntexist

Source: "..\..\packager-win-x64.exe"; DestDir: "{app}"; Components: main; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\..\mp4decrypt.exe"; DestDir: "{app}"; Components: main; Flags: ignoreversion skipifsourcedoesntexist

Source: "{#RepoDir}\modules\amazonmusic\*"; DestDir: "{app}\modules\amazonmusic"; Components: modules\amazonmusic; Flags: recursesubdirs
Source: "{#RepoDir}\modules\applemusic\*"; DestDir: "{app}\modules\applemusic"; Components: modules\applemusic; Flags: recursesubdirs
Source: "{#RepoDir}\modules\beatport\*"; DestDir: "{app}\modules\beatport"; Components: modules\beatport; Flags: recursesubdirs
Source: "{#RepoDir}\modules\deezer\*"; DestDir: "{app}\modules\deezer"; Components: modules\deezer; Flags: recursesubdirs
Source: "{#RepoDir}\modules\musixmatch\*"; DestDir: "{app}\modules\musixmatch"; Components: modules\musixmatch; Flags: recursesubdirs
Source: "{#RepoDir}\modules\lrclib\*"; DestDir: "{app}\modules\lrclib"; Components: modules\lrclib; Flags: recursesubdirs
Source: "{#RepoDir}\modules\qobuz\*"; DestDir: "{app}\modules\qobuz"; Components: modules\qobuz; Flags: recursesubdirs
Source: "{#RepoDir}\modules\soundcloud\*"; DestDir: "{app}\modules\soundcloud"; Components: modules\soundcloud; Flags: recursesubdirs
Source: "{#RepoDir}\modules\spotify\*"; DestDir: "{app}\modules\spotify"; Components: modules\spotify; Flags: recursesubdirs
Source: "{#RepoDir}\Spotify.dll"; DestDir: "{app}"; Components: modules\spotify; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#RepoDir}\modules\tidal\*"; DestDir: "{app}\modules\tidal"; Components: modules\tidal; Flags: recursesubdirs
Source: "{#RepoDir}\modules\youtube\*"; DestDir: "{app}\modules\youtube"; Components: modules\youtube; Flags: recursesubdirs


Source: "..\..\modules\__init__.py"; DestDir: "{app}\modules"; Components: main; Flags: ignoreversion skipifsourcedoesntexist

[Icons]

Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]

Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
