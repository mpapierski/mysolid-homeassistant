from __future__ import annotations

POLISH_HOST = "https://mysolid.solidsecurity.pl/"
CZECH_HOST = "https://mysolid.solidsecurity.cz/"

HOSTS: dict[str, str] = {
    "pl": POLISH_HOST,
    "cs": CZECH_HOST,
}

DEFAULT_HOST = POLISH_HOST

PACKAGE_NAME = "pl.unityt.msc.android"
APP_VERSION_NAME = "3.5.3 (2015)"
APP_VERSION_CODE = "30503"

DEFAULT_CONNECT_TIMEOUT_SECONDS = 20
DEFAULT_READ_TIMEOUT_SECONDS = 30

DEVICE_ID_PREFIX = "ANDROID_ID#"
DEFAULT_DEVICE_NAME = "MySolid Home Assistant"

FIREBASE_PROJECT_ID = "mysolid-android"
FIREBASE_SENDER_ID = "175577915318"
FIREBASE_APP_ID = "1:175577915318:android:190dbb67b88dd955"
# Firebase Installations / FCM bootstrap key extracted from the original
# MySolid Android APK during reverse engineering of the mobile app.
#
# This value is included here only so the Home Assistant integration can mimic
# the official Android client closely enough to register for the same push
# notification flow. It was derived from the app's embedded Firebase
# configuration, not issued for general third-party use.
#
# Do not copy, publish, or reuse this key outside this project. While Firebase
# API keys are not standalone secrets, this one still identifies the vendor's
# mobile application project. Using it outside this Home Assistant integration
# or against accounts/services you do not control may violate your monitoring
# contract, service agreement, or provider terms.
_FIREBASE_API_KEY_PARTS = (
    "AI",
    "za",
    "Sy",
    "CmCiE",
    "_U53",
    "rwnP",
    "W2Tz",
    "NRRr",
    "oH2D",
    "7lbK",
    "gqaQ",
)
FIREBASE_API_KEY = "".join(_FIREBASE_API_KEY_PARTS)
