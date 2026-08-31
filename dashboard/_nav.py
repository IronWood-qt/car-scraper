"""Shared sidebar chrome for every dashboard script (🚗_Dashboard.py and
pages/1_⚙️_App_Settings.py) - not a page itself (no digit/emoji prefix, so
Streamlit's page auto-discovery skips it).

Streamlit's own multipage nav list (which would otherwise put "Dashboard"
and "App Settings" together at the very top) is disabled via
`--client.showSidebarNavigation=false` (see run.sh / dashboard/Dockerfile),
so each script calls `render_nav()` instead: a "Dashboard" link pinned to
the top, optional page-specific sidebar content (a car's "Go to <site>"
buttons) in between, and a "Settings" link pinned to the bottom via CSS
flex - not just appended after, so it stays put regardless of how much
page-specific content sits above it.
"""

from collections.abc import Callable

import streamlit as st

# - block-container padding-top: Streamlit's default leaves a lot of dead
#   space above the title on this wide, description-less layout.
# - stHeader: kept in the layout (NOT display:none) because the "expand
#   sidebar" control only exists inside it, and only while the sidebar is
#   collapsed - hiding the whole header makes a collapsed sidebar
#   unrecoverable. Only the Community-Cloud bits (Deploy button, the
#   kebab "main menu", any per-element toolbar) are hidden individually.
# - the sidebar's last direct child (always the Settings link - see
#   render_nav below) gets margin-top:auto in a flex column, pinning it to
#   the bottom regardless of how much page-specific content precedes it.
_CSS = """
<style>
div.block-container{padding-top:0.5rem;}
header[data-testid="stHeader"]{background:transparent;}
div[data-testid="stToolbarActions"]{display:none;}
div[data-testid="stAppDeployButton"]{display:none;}
span[data-testid="stMainMenu"]{display:none;}
[data-testid="stSidebarUserContent"]{height:100%;}
[data-testid="stSidebarUserContent"] > div{height:100%;}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"]{
    display:flex;flex-direction:column;height:100%;
}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"]
    > div[data-testid="stElementContainer"]:last-child{margin-top:auto;}
</style>
"""


def render_nav(sidebar_extra: Callable[[], None] | None = None) -> None:
    """Inject the shared CSS and render Dashboard (top) / Settings (bottom),
    with ``sidebar_extra()`` - if given - rendered in the sidebar between them.
    """
    st.markdown(_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.page_link("🚗_Dashboard.py", label="Dashboard", icon="🚗")
        if sidebar_extra:
            sidebar_extra()
        st.page_link("pages/1_⚙️_App_Settings.py", label="Settings", icon="⚙️")
