; DrawCheck Pro 安裝檔（Inno Setup 6）。由 build_installer.ps1 呼叫，傳入 /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "DrawCheck Pro"
#define AppFullName "DrawCheck Pro｜工程圖檢核專家"
#define AppExe "DrawCheckPro.exe"
#define ProgId "DrawCheckPro.pdf"

[Setup]
AppId={{6F1B2C7E-4D3A-4E8B-9C21-5A7D0E3F9B42}
AppName={#AppFullName}
AppVersion={#AppVersion}
AppVerName={#AppFullName} {#AppVersion}
AppPublisher=DrawCheck Pro
DefaultDirName={autopf}\DrawCheckPro
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SourceDir=..
OutputDir=dist
OutputBaseFilename=DrawCheckPro-Setup-{#AppVersion}
SetupIconFile=app\resources\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppFullName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ChangesAssociations=yes

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\ChineseTraditional.isl")
Name: "zh_tw"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"
#elif FileExists(AddBackslash(SourcePath) + "ChineseTraditional.isl")
Name: "zh_tw"; MessagesFile: "installer\ChineseTraditional.isl"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[CustomMessages]
DesktopIcon=建立桌面捷徑
AssocPdf=加入 PDF 的「開啟檔案」選單
Launch=啟動 {#AppName}

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "assocpdf"; Description: "{cm:AssocPdf}"

[Files]
Source: "dist\DrawCheckPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; 只加入「開啟檔案」清單，不搶預設的 PDF 開啟程式
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "PDF（{#AppName}）"; Flags: uninsdeletekey; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey; Tasks: assocpdf

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent
