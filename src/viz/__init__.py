"""The visualization library: OpenMS-Insight components wired as panels.

A panel reads a column contract, not an app's files: each app turns its own
results into the frames a panel reads (its *source*) and draws the panel.
Nothing here imports app code; openms_insight is imported where a panel is
drawn, since it is a dependency of the apps, not of the template.
"""
