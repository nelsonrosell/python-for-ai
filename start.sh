#!/bin/sh
set -eu

PORT_VALUE="${PORT:-8000}"

exec python -m streamlit run streamlit_app.py \
    --server.port "${PORT_VALUE}" \
    --server.address 0.0.0.0