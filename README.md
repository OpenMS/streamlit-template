# FLASHViewer

FLASHViewer for visualizing FLASHDeconv's results \
This app is based on [OpenMS streamlit template project](https://github.com/OpenMS/streamlit-template).

run locally:

`streamlit run Template.py local`

## Working with submodules

This project uses a git submodule to integrate openms-streamlit-vue-component.

When checking out this repository you will need to run a few extra commands:

`git submodule init`

`git submodule update`

If you would like to update the submodule to the latest commit, use the following:

`git submodule update --remote`

See [https://git-scm.com/book/en/v2/Git-Tools-Submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
for more documentation on submodules
