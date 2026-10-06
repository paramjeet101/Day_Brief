#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main() -> None:
    # Default to dev settings; override with DJANGO_SETTINGS_MODULE in prod.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and available "
            "on your PYTHONPATH? Did you forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
