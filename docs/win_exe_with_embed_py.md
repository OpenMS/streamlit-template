## 💻 Create a window executable of a Streamlit App with embeddable Python

To create an executable for Streamlit app on Windows, we'll use an embeddable version of Python.</br>
Here's a step-by-step guide:

### Download and Extract Python Embeddable Version

1. Download a suitable Python embeddable version. For example, let's download Python 3.11.9:

   ```bash
   # use curl command or manually download
   curl -O https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip
   ```

2. Extract the downloaded zip file:

   ```bash
   mkdir python-3.11.9

   unzip python-3.11.9-embed-amd64.zip -d python-3.11.9

   rm python-3.11.9-embed-amd64.zip
   ```

### Install pip

1. Download `get-pip.py`:

   ```bash
   # use curl command or manually download
   curl -O https://bootstrap.pypa.io/get-pip.py
   ```

2. Install pip:

   ```bash
   ./python-3.11.9/python get-pip.py --no-warn-script-location

   # no need anymore get-pip.py
   rm get-pip.py
   ```

### Configure Python Environment

1. Uncomment 'import site' in the `._pth` file:

   ```bash
   # Uncomment to run site.main() automatically
   # Remove hash from python-3.11.9/python311._pth file
   import site

   # Or use command
   sed -i '/^\s*#\s*import\s\+site/s/^#//' python-3.11.9/python311._pth
   ```

### Install Required Packages

Install all required packages from `requirements.txt`:

```bash
./python-3.11.9/python -m pip install -r requirements.txt --no-warn-script-location
```

### Test and create `run_app.bat` file

1. Test by running app

   ```batch
       .\python-3.11.9\python -m streamlit run app.py
   ```

2. Create a Clickable Shortcut

   Create a `run_app.bat` file to make running the app easier:

   ```batch
   echo @echo off > run_app.bat
   echo .\\python-3.11.9\\python -m streamlit run app.py >> run_app.bat
   ```

### Create one executable folder

1. Create a folder for your Streamlit app:

   ```bash
   mkdir ../streamlit_exe
   ```

2. Copy environment and app files:

   ```bash
   # move Python environment folder
   mv  python-3.11.9 ../streamlit_exe

   # move run_app.bat file
   mv  run_app.bat ../streamlit_exe

   # copy streamlit app files
   cp -r src pages .streamlit assets example-data ../streamlit_exe
   cp app.py ../streamlit_exe
   ```

#### 🚀 After successfully completing all these steps, the Streamlit app will be available by running the run_app.bat file.

:pencil: You can still change the configuration of Streamlit app with .streamlit/config.toml file, e.g., provide a different port, change upload size, etc.

## Build executable in github action automatically

Automate the process of building executables for your project with the GitHub action example [Test streamlit executable for Windows with embeddable python](https://github.com/OpenMS/streamlit-template/blob/main/.github/workflows/test-win-exe-w-embed-py.yaml)
</br>

## Create MSI Installer using WiX Toolset

After creating your executable folder, you can package it into an MSI installer using WiX Toolset. Here's how:

### 1. Set Environment Variables

Set these variables for consistent naming throughout the process:

```batch
APP_NAME=OpenMS-StreamlitTemplateApp
APP_UpgradeCode=4abc2e23-3ba5-40e4-95c9-09e6cb8ecaeb
```

To create a new GUID for your application's UpgradeCode, you can use:

-  PowerShell: `[guid]::NewGuid().ToString()`
-  Online GUID generator: https://www.guidgen.com/
-  Windows Command Prompt: `powershell -Command "[guid]::NewGuid().ToString()"`

### 2. Install WiX Toolset

1. Download WiX Toolset binaries:
   ```batch
   curl -LO https://github.com/wixtoolset/wix3/releases/download/wix3111rtm/wix311-binaries.zip
   unzip wix311-binaries.zip -d wix
   ```

### 3. Prepare Installation Files

1. Create a SourceDir structure:

   ```batch
   mkdir SourceDir
   move streamlit_exe\* SourceDir
   ```

2. Create Readme.txt:

   ```batch
   # Create a Readme.txt file in the SourceDir folder with instructions
   # for launching the application
   ```

3. Add necessary assets:
   -  Copy license file: `copy assets\openms_license.rtf SourceDir\`
   -  Copy app icon: `copy assets\openms.ico SourceDir\`
   -  Create success message script:
      ```vbscript
      ' ShowSuccessMessage.vbs
      MsgBox "The " & "%APP_NAME%" & " application is successfully installed.", vbInformation, "Installation Complete"
      ```

### 4. Generate WiX Source Files

1. Generate component list from your files:

   ```batch
   wix\heat.exe dir SourceDir -gg -sfrag -sreg -srd -template component -cg StreamlitExeFiles -dr AppSubFolder -out streamlit_exe_files.wxs
   ```

2. Create main WiX configuration file (streamlit_exe.wxs):

   ```xml
   <?xml version="1.0"?>
   <Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
     <Product Id="*" Name="$(env.APP_NAME)" Language="1033" Version="1.0.0.0"
              Manufacturer="OpenMS Developer Team" UpgradeCode="$(env.APP_UpgradeCode)">
       <Package Id="*" InstallerVersion="300" Compressed="yes" InstallPrivileges="elevated" Platform="x64" />
       <Media Id="1" Cabinet="streamlit.cab" EmbedCab="yes" />

       <!-- Directory structure -->
       <Property Id="WIXUI_INSTALLDIR" Value="INSTALLFOLDER" />
       <Directory Id="TARGETDIR" Name="SourceDir">
         <Directory Id="ProgramFilesFolder">
           <Directory Id="INSTALLFOLDER" Name="$(env.APP_NAME)">
             <Directory Id="AppSubFolder" Name="$(env.APP_NAME)" />
             <Component Id="CreateAppFolder" Guid="95dbfa06-d36a-427f-995c-e87769ac2e59">
               <CreateFolder>
                 <Permission User="Everyone" GenericAll="yes" />
               </CreateFolder>
             </Component>
           </Directory>
         </Directory>
         <Directory Id="DesktopFolder" />
       </Directory>

       <!-- Features -->
       <Feature Id="MainFeature" Title="Main Application" Level="1">
         <ComponentGroupRef Id="StreamlitExeFiles" />
         <ComponentRef Id="CreateAppFolder" />
         <ComponentRef Id="DesktopShortcutComponent" />
         <ComponentRef Id="InstallDirShortcutComponent" />
       </Feature>

       <!-- Desktop Shortcut -->
       <Component Id="DesktopShortcutComponent" Guid="3597b243-9180-4d0b-b105-30d8b0d1a334" Directory="DesktopFolder">
         <Shortcut Id="DesktopShortcut" Name="$(env.APP_NAME)"
                   Description="Launch $(env.APP_NAME)"
                   Target="[AppSubFolder]$(env.APP_NAME).bat"
                   WorkingDirectory="AppSubFolder"
                   Icon="AppIcon" />
         <RegistryValue Root="HKCU" Key="Software\OpenMS\$(env.APP_NAME)"
                       Name="DesktopShortcut" Type="integer" Value="1" KeyPath="yes" />
       </Component>

       <!-- Installation Directory Shortcut -->
       <Component Id="InstallDirShortcutComponent" Guid="c2df9472-3b45-4558-a56d-6034cf7c8b72" Directory="AppSubFolder">
         <Shortcut Id="InstallDirShortcut" Name="$(env.APP_NAME)"
                   Description="Launch $(env.APP_NAME)"
                   Target="[AppSubFolder]$(env.APP_NAME).bat"
                   WorkingDirectory="AppSubFolder"
                   Icon="AppIcon" />
         <RegistryValue Root="HKCU" Key="Software\OpenMS\$(env.APP_NAME)"
                       Name="InstallFolderShortcut" Type="integer" Value="1" KeyPath="yes" />
       </Component>

       <!-- UI and Icon -->
       <Icon Id="AppIcon" SourceFile="SourceDir/openms.ico" />
       <UI>
         <UIRef Id="WixUI_InstallDir" />
         <UIRef Id="WixUI_ErrorProgressText" />
       </UI>

       <!-- Success Message -->
       <Binary Id="ShowMessageScript" SourceFile="SourceDir/ShowSuccessMessage.vbs" />
       <CustomAction Id="ShowSuccessMessage" BinaryKey="ShowMessageScript" VBScriptCall="" Execute="immediate" Return="check" />

       <!-- Custom Actions Sequence -->
       <InstallExecuteSequence>
         <Custom Action="ShowSuccessMessage" After="InstallFinalize">NOT Installed</Custom>
       </InstallExecuteSequence>

       <!-- License -->
       <WixVariable Id="WixUILicenseRtf" Value="SourceDir/openms_license.rtf" />
     </Product>
   </Wix>
   ```

### 5. Build the MSI

1. Compile WiX source files:

   ```batch
   # Generate wixobj files from the WiX source files
   wix\candle.exe streamlit_exe.wxs streamlit_exe_files.wxs
   ```

2. Link and create MSI:
   ```batch
   # Create the MSI installer from the wixobj files
   # The -sice:ICE60 flag stops a warning about duplicate component GUIDs, which can happen when heat.exe auto-generates components
   wix\light.exe -ext WixUIExtension -sice:ICE60 -o %APP_NAME%.msi streamlit_exe_files.wixobj streamlit_exe.wixobj
   ```

### 6. Additional Notes

-  The generated MSI will create desktop and start menu shortcuts
-  Installation requires elevated privileges
-  A success message will be shown after installation
-  The installer includes a proper license agreement page
-  All files will be installed in Program Files by default

For more detailed customization options, refer to the [WiX Toolset documentation](https://wixtoolset.org/documentation/).

:warning: The `APP_UpgradeCode` GUID should be unique for your application. Generate a new one if you're creating a different app.
