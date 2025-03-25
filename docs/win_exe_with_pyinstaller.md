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
python -m venv myenv

# activate an environment
.\myenv\Scripts\Activate.bat 

# install require packages
pip install -r requirements.txt

#install pyinstaller
pip install pyinstaller
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
mkdir artifacts
cp -r dist artifacts/
cp -r build artifacts/
cp run_app.spec artifacts/ 
cp D:/a/streamlit-template/streamlit-template/myenv/Lib/site-packages/streamlit/web/cli.py artifacts/ 
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
