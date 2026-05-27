#!/bin/bash
# install_hooks.sh — Install pre-commit hook to block secret commits
# Run once: bash scripts/install_hooks.sh

HOOK_PATH=".git/hooks/pre-commit"

cat > "$HOOK_PATH" << 'HOOK'
#!/bin/bash
bash scripts/rotate_check.sh
HOOK

chmod +x "$HOOK_PATH"
echo "Pre-commit hook installed at $HOOK_PATH"
echo "Secrets will now be blocked before every commit."
