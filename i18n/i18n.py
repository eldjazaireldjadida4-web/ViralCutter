import json
import locale
import os

_LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locale")

# Default UI language. Override with the VIRALCUTTER_LANG environment
# variable (e.g. VIRALCUTTER_LANG=en_US) to run in another language.
DEFAULT_LANGUAGE = os.getenv("VIRALCUTTER_LANG", "ar_SA")


def load_language_list(language):
    with open(
        os.path.join(_LOCALE_DIR, f"{language}.json"), "r", encoding="utf-8"
    ) as f:
        language_list = json.load(f)
    return language_list


class I18nAuto:
    def __init__(self, language=None):
        if language in ["Auto", None]:
            language = locale.getdefaultlocale()[
                0
            ]  # getlocale can't identify the system's language ((None, None))
        if not os.path.exists(os.path.join(_LOCALE_DIR, f"{language}.json")):
            language = "en_US"
        self.language = language
        self.language_map = load_language_list(language)

    def __call__(self, key):
        return self.language_map.get(key, key)
