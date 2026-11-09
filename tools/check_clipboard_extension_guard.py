"""Compatibility entry point for the maintained clipboard resource check."""
from check_clipboard_resources import *
import verify_features as v

if __name__ == "__main__":
    raise SystemExit(v.main())
