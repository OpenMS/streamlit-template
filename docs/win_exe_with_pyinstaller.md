## 💻 Create a window executable of streamlit app with pyinstaller
:heavy_check_mark: 
Tested with streamlit v1.29.0, python v3.11.4

:warning: Support until streamlit version `1.29.0`
:point_right: For higher version, try streamlit app with embeddable python #TODO add link 

To create an executable for Streamlit app on Windows, we'll use an pyinstaller.
Here's a step-by-step guide:

### virtual environment 

``` 
# create an environment
python -m venv <myenv>

# activate an environment
.\myenv\Scripts\Activate.bat 

# install require packages
pip install -r requirements.txt

#install pyinstaller
pip install pyinstaller
```

### streamlit files

create a run_app.py and add this lines of codes
```
from streamlit.web import cli

if __name__=='__main__':
    cli._main_run_clExplicit(
        file="app.py", command_line="streamlit run"
    )
    # we will create this function inside our streamlit framework

```

### write function in cli.py

Now, navigate to the inside streamlit environment

here you go

```
<myenv>\Lib\site-packages\streamlit\web\cli.py
```
for using our virtual environment, add this magic function to cli.py file: 
```
#can be modify name as given in run_app.py
#use underscore at beginning 
def _main_run_clExplicit(file, command_line, args=[], flag_options=[]):
    main._is_running_with_streamlit = True
    bootstrap.run(file, command_line, args, flag_options)
```

### Hook folder
Now, need to hook to get streamlit metadata
organized as folder, where the pycache infos will save
like: \hooks\hook-streamlit.py

```
from PyInstaller.utils.hooks import copy_metadata
datas = []
datas += copy_metadata('streamlit')
datas += copy_metadata('pyopenms')
# can add new package e-g
datas += copy_metadata('captcha')
```

### compile the app 
Now, ready for compilation
```
pyinstaller --onefile --additional-hooks-dir ./hooks run_app.py --clean

#--onefile create join binary file ??
#will create run_app.spec file
#--clean delete cache and removed temporary files before building
#--additional-hooks-dir path to search for hook 
```

### streamlit config
To access  streamlit config create file in root 
(or just can be in output folder)
.streamlit\config.toml

```
# content of .streamlit\config.toml
[global]
developmentMode = false

[server]
port = 8502
``` 

### copy necessary files to dist folder
```
cp -r .streamlit dist/.streamlit
cp -r pages dist/pages
cp -r src dist/src
cp -r assets dist/assets
cp app.py dist/

``` 


### add datas in run_app.spec (.spec file)
Add DATAS to the run_app.spec just created by compilation

```
datas=[
        ("myenv/Lib/site-packages/altair/vegalite/v4/schema/vega-lite-schema.json","./altair/vegalite/v4/schema/"),
        ("myenv/Lib/site-packages/streamlit/static", "./streamlit/static"),
        ("myenv/Lib/site-packages/streamlit/runtime", "./streamlit/runtime"),
        ("myenv/Lib/site-packages/pyopenms", "./pyopenms/"),
        # Add new datas e-g we add in hook captcha
        ("myenv/Lib/site-packages/captcha", "./captcha/")
    ]
```    
### run final step to make executable
All the modifications in datas should be loaded with
```
pyinstaller run_app.spec --clean
```
#### 🚀 After successfully completing all these steps, the Windows executable will be available in the dist folder.

:pencil: you can still change the configuration of streamlit app with .streamlit/config.toml file e-g provide different port, change upload size etc

ℹ️ if problem with altair, Try version altair==4.0.1, and again compile

## Build executable in github action automatically
Automate the process of building executables for your project with the GitHub action example [Test streamlit executable for Windows with pyinstaller](https://github.com/OpenMS/streamlit-template/blob/main/.github/workflows/test-win-exe-w-pyinstaller.yaml)
