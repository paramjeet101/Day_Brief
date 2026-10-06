#!/usr/bin/env bash
# Render build step: install deps + collect static assets.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
