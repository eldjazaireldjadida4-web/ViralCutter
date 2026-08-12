# -*- coding: utf-8 -*-
"""
Secure API config — stop storing Gemini keys in plaintext.

Roadmap item 4.4 ("مفتاح API مشفّر"). Priority order for resolving the
Gemini key:

    1. env VIRALCUTTER_GEMINI_KEY / GEMINI_API_KEY   (recommended, CI-safe)
    2. encrypted store (api_config.secure.json, Fernet AES)   [new]
    3. legacy plaintext api_config.json (with a warning)

Encryption: uses `cryptography` (Fernet) when installed
otherwise falls
back to a scrypt-derived XOR obfuscation and warns that it is NOT
real encryption — install `cryptography` for real protection. The
passphrase never touches the file
it is asked once interactively or via
the VIRALCUTTER_CONFIG_PASSPHRASE env var.

API: resolve_api_key(), set_key(), get_key(), load_api_config() (returns
the merged config dict the rest of the app already expects).
"""

import base64
import hashlib
import json
import os
import tempfile

SECURE_CONFIG = "api_config.secure.json"
LEGACY_CONFIG = "api_config.json"

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


def _base_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def secure_config_path(base_dir=None):
    return os.path.join(base_dir or _base_dir(), SECURE_CONFIG)


def legacy_config_path(base_dir=None):
    return os.path.join(base_dir or _base_dir(), LEGACY_CONFIG)


def _derive_key(passphrase, salt):
    """32-byte key from passphrase + salt (scrypt)."""
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)



def _encrypt_blob(plain: bytes, passphrase: str) -> str:
    # SECURITY: the insecure XOR "obfuscation" format (v1) was removed in
    # 7.0.0-pro — credential storage now fails closed: without real
    # encryption available we refuse to write anything.
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("cryptography is required for secure credential storage")
    salt = os.urandom(16)
    key = base64.urlsafe_b64encode(_derive_key(passphrase, salt))
    token = Fernet(key).encrypt(plain)
    return json.dumps({"v": 2, "salt": base64.b64encode(salt).decode(),
                       "token": token.decode()})


def _decrypt_blob(payload: str, passphrase: str) -> bytes:
    data = json.loads(payload)
    salt = base64.b64decode(data["salt"])
    if data.get("v") == 2:
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError("this config needs 'cryptography' (pip install cryptography)")
        key = base64.urlsafe_b64encode(_derive_key(passphrase, salt))
        return Fernet(key).decrypt(data["token"].encode())
    raise RuntimeError("insecure legacy credential format is not supported")


def set_key(api_key, passphrase=None, base_dir=None):
    """Store the key encrypted. Returns the secure config path."""
    if not passphrase:
        passphrase = os.getenv("VIRALCUTTER_CONFIG_PASSPHRASE", "").strip()
    if not passphrase:
        raise ValueError("a passphrase is required (or set VIRALCUTTER_CONFIG_PASSPHRASE)")
    if not HAS_CRYPTOGRAPHY:
        raise RuntimeError("cryptography is required for secure credential storage")
    path = secure_config_path(base_dir)
    data = {"gemini": {"api_key": _encrypt_blob(api_key.encode("utf-8"), passphrase)}}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try: os.chmod(path, 0o600)
        except OSError: pass
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except OSError: pass
    return path


def get_key(passphrase=None, base_dir=None):
    """Read the encrypted key. Returns None when absent or passphrase wrong."""
    path = secure_config_path(base_dir)
    if not os.path.exists(path):
        return None
    if not passphrase:
        passphrase = os.getenv("VIRALCUTTER_CONFIG_PASSPHRASE", "").strip()
    if not passphrase:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _decrypt_blob(data["gemini"]["api_key"], passphrase).decode("utf-8")
    except Exception:
        return None


def _legacy_key(base_dir=None):
    path = legacy_config_path(base_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = (data.get("gemini") or {}).get("api_key", "") or ""
        if key and key not in ("SUA_KEY_AQUI", "YOUR_KEY_HERE"):
            return key
    except Exception:
        pass
    return None


def resolve_api_key(base_dir=None, warn=True):
    """Recommended key resolution order (env → encrypted → legacy plaintext)."""
    for env in ("VIRALCUTTER_GEMINI_KEY", "GEMINI_API_KEY"):
        val = os.getenv(env, "").strip()
        if val:
            return val
    secure = get_key(base_dir=base_dir)
    if secure:
        return secure
    legacy = _legacy_key(base_dir)
    if legacy and warn:
        print("[secure-config] WARNING: reading Gemini key from plaintext "
              "api_config.json. Move it to the encrypted store with "
              "`python -m scripts.secure_config --set`.")
    return legacy


def load_api_config(base_dir=None):
    """Merged config dict (same shape api_config.json users expect), with the
    resolved key injected so downstream code needs no changes."""
    path = legacy_config_path(base_dir)
    config = {
        "selected_api": "gemini",
        "gemini": {"api_key": "", "model": "gemini-2.5-flash-lite-preview-09-2025",
                   "chunk_size": 20000},
        "g4f": {"model": "gpt-4o-mini", "chunk_size": 2000},
    }
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                config.update(loaded)
                if isinstance(loaded.get("gemini"), dict):
                    config["gemini"].update(loaded["gemini"])
                if isinstance(loaded.get("g4f"), dict):
                    config["g4f"].update(loaded["g4f"])
        except Exception:
            pass
    key = resolve_api_key(base_dir)
    if key:
        config["gemini"]["api_key"] = key
    return config


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ViralCutter secure API config.")
    parser.add_argument("--set", metavar="KEY", help="store an API key (encrypted)")
    parser.add_argument("--get", action="store_true", help="print the resolved key")
    parser.add_argument("--passphrase", default=None,
                        help="passphrase (or VIRALCUTTER_CONFIG_PASSPHRASE env)")
    parser.add_argument("--no-warn", action="store_true")
    args = parser.parse_args()
    if args.set:
        path = set_key(args.set, args.passphrase)
        print("key stored encrypted in {}".format(path))
        if not HAS_CRYPTOGRAPHY:
            print("WARNING: 'cryptography' not installed — using obfuscation only. "
                  "Run: pip install cryptography")
    elif args.get:
        key = resolve_api_key(warn=not args.no_warn)
        print(key or "(no key configured)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
