import os

# Theme configuration with defaults; these can be overridden via environment variables.
THEME_CONFIG = {
    "primaryColor": os.getenv("STREAMLIT_PRIMARY_COLOR", "#F63366"),
    "backgroundColor": os.getenv("STREAMLIT_BACKGROUND_COLOR", "#FFFFFF"),
    "secondaryBackgroundColor": os.getenv("STREAMLIT_SECONDARY_BACKGROUND_COLOR", "#F0F2F6"),
    "textColor": os.getenv("STREAMLIT_TEXT_COLOR", "#000000"),
    "font": os.getenv("STREAMLIT_FONT", "sans serif")
}
