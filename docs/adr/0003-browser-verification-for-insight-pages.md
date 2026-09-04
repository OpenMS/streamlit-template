# Results pages are verified in a real browser, not with AppTest

`streamlit.testing.v1.AppTest` executes no JavaScript, so it cannot see
OpenMS-Insight components at all — they are custom bidirectional Vue components
rendered in iframes. A results page built entirely from Insight components passes
every AppTest assertion while rendering nothing. Results pages are therefore gated
by headless Playwright, which asserts that panels render, that clicking a row
changes a linked panel, and that the browser console is clean, plus a screenshot
the model critiques against the style contract.

## Consequences

This is a second test mechanism beside the repo's existing AppTest suite, and it
adds a Playwright dev dependency and a browser download to the development setup.
AppTest is kept for everything it can still see — page boot, Streamlit-native
widgets, parameter round-tripping. During interactive dashboard building a real
Chrome session is driven instead, for the same reason in reverse: the model needs
to look at the page it is designing.
