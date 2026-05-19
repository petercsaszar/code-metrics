#!/bin/bash
# entrypoint.sh
# Wrapper script that reads config.yml to auto-configure UNITY_PATH if mounted

set -e

CONFIG_FILE="${ANALYZER_CONFIG:-/opt/bulk_analyzer/config.yml}"

# Try to extract unity_path from config.yml using Python
UNITY_PATH_FROM_CONFIG=$(python3 -c "
import yaml
try:
    with open('${CONFIG_FILE}', 'r') as f:
        cfg = yaml.safe_load(f)
    unity_path = cfg.get('analyzer', {}).get('unity_path', '')
    print(unity_path if unity_path else '')
except Exception as e:
    print('', file=__import__('sys').stderr)
" 2>/dev/null || echo "")

# If unity_path is set in config and not already set as env var, use it
if [ -n "$UNITY_PATH_FROM_CONFIG" ] && [ -z "$UNITY_PATH" ]; then
    export UNITY_PATH="$UNITY_PATH_FROM_CONFIG"
    if [ -e "$UNITY_PATH" ]; then
        echo "✅ Using Unity from config.yml: $UNITY_PATH"
    else
        echo "⚠️  Warning: unity_path in config.yml is set to '$UNITY_PATH' but the file/directory does not exist in container."
        echo "   Make sure to mount the host Unity directory: -v /host/unity/path:/mnt/unity"
        echo "   And set analyzer.unity_path in config.yml to the container path (e.g., /mnt/unity/Editor/Unity)"
    fi
elif [ -n "$UNITY_PATH" ]; then
    echo "✅ Using UNITY_PATH from environment: $UNITY_PATH"
else
    echo "ℹ️  No Unity path configured. Skipping Unity projects."
fi

# Run analyzer.py with all passed arguments
exec python3 -m bulk_analyzer.analyzer "$@"
