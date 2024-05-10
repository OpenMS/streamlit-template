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
        .\python-3.11.9\python -m streamlit run app.py local
    ```

2. Create a Clickable Shortcut

    Create a `run_app.bat` file to make running the app easier:
    
    ```batch
    echo @echo off > run_app.bat
    echo .\\python-3.11.9\\python -m streamlit run app.py local >> run_app.bat
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
    
#### 🚀 <code> After successfully completing all these steps, the Streamlit app will be available by running the run_app.bat file.</code>

:pencil: You can still change the configuration of Streamlit app with .streamlit/config.toml file, e.g., provide a different port, change upload size, etc.

## Build executable in github action automatically
Automate the process of building executables for your project with the GitHub action example [Test streamlit executable for Windows with embeddable python](https://github.com/OpenMS/streamlit-template/blob/main/.github/workflows/test-win-exe-w-embed-py.yaml)
</br>
