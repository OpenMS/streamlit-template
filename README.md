# FLASHViewer

FLASHViewer for visualizing FLASHDeconv's results \
This app is based on [OpenMS streamlit template project](https://github.com/OpenMS/streamlit-template).

run locally:

`streamlit run Template.py local`

### Working with submodules

This project uses a git submodule to integrate openms-streamlit-vue-component.

When checking out this repository you will need to run a few extra commands:

`git submodule init`

`git submodule update`

If you would like to update the submodule to the latest commit, use the following:

`git submodule update --remote`

See [https://git-scm.com/book/en/v2/Git-Tools-Submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
for more documentation on submodules

## Build

To build FLASHViewer, you first need to build the `openms-streamlit-vue-component`
and copy the build from `./openms-streamlit-vue-component/dist` to 
`./js-component/dist`.

You then should set streamlit to production in two locations:

* in `./.streamlit/config.toml` set `developmentMode` to `false`
* in `./src/components.py` set `_RELEASE` to `True`

These steps should be done before building any version of FLASHViewer.

### Docker

First you need to build an image locally.

`build image with: docker build -f Dockerfile --no-cache -t flashviewer:latest --build-arg GITHUB_TOKEN=<your-github-token> .`

You should see a successful output, but you can check if an image is built with:

`docker image ls`

After it has been built you can run the image with:

`docker run -p 8501:8501 flashviewer:latest`

Navigate to `http://localhost:8501` in your browser.