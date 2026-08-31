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

Collapsing the sidebar (the » / « arrow) shrinks it to an icon-only rail
instead of hiding it completely: Dashboard/Settings stay as clickable
icons (their label text is hidden), and any page-specific content between
them (a car's buttons) is hidden outright - see the DOM structure notes
inline below, reverse-engineered from Streamlit's own PageLink.*.js since
none of this is documented/stable API.
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

/* Collapsed (aria-expanded="false") = icon rail, not fully hidden.
   stSidebar normally both shrinks to width:0 AND slides out via
   translateX(-<full-width>px) on collapse (a CSS class swap, not inline
   style) - !important overrides both without touching the transition
   itself, so it still animates, just to a narrower resting width instead
   of sliding fully off-screen. */
[data-testid="stSidebar"][aria-expanded="false"]{
    width:4.5rem!important;min-width:4.5rem!important;transform:none!important;
}
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"]{
    width:4.5rem!important;
}
/* Page-specific content (a car's "All cars"/source-link buttons) sits
   between the pinned first (Dashboard) and last (Settings) children -
   hide just that middle section, keep the two nav icons. */
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stVerticalBlock"]
    > div[data-testid="stElementContainer"]:not(:first-child):not(:last-child){
    display:none;
}
/* st.page_link (icon_position defaults to "left", which we always use)
   renders <a data-testid="stPageLink-NavLink"><span>icon-wrapper</span>
   <span>label</span></a> - neither direct child carries a data-testid
   (the icon's own stIconEmoji/stIconMaterial span is nested one level
   deeper inside the first one), so position is the only reliable hook:
   hide the second (label) span, keep the first (icon). */
[data-testid="stSidebar"][aria-expanded="false"] a[data-testid="stPageLink-NavLink"]
    > span:nth-child(2){
    display:none;
}
/* stSidebarCollapseButton ("«", inside the sidebar) only had no visible
   space to render in while width was forced to 0 - now that collapsed
   has a real width again it reappears, duplicating stExpandSidebarButton
   ("»", floats in the main content's top-left, outside the sidebar, only
   while collapsed - see the header-hiding rules above). Keep just one
   toggle visible: the header's. */
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"]{
    display:none;
}
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
