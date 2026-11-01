"""Countries of incorporation offered on the details screen. Any other country can be typed in.

Companies House and the FCA register only cover UK companies, so their checks run only for the United Kingdom.
"""

UNITED_KINGDOM = "United Kingdom"
COUNTRIES = [
    UNITED_KINGDOM, "Ireland", "Jersey", "Guernsey", "Isle of Man", "Gibraltar", "United States", "Canada",
    "France", "Germany", "Netherlands", "Luxembourg", "Belgium", "Spain", "Italy", "Malta", "Cyprus", "Switzerland",
    "Lithuania", "Estonia", "Sweden", "Cayman Islands", "British Virgin Islands", "Bermuda", "Singapore", "Hong Kong",
    "United Arab Emirates", "India", "Nigeria", "South Africa", "Kenya", "Australia",
]


def is_uk(country: str) -> bool:
    """Reviews saved before the country was asked for are UK companies."""
    return (country or UNITED_KINGDOM) == UNITED_KINGDOM
