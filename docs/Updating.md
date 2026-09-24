# Updating FireServiceRota Extended from Git

This is an optional update method for users who keep a local Git clone of the repository on Home Assistant OS / Supervised, where the `ha` CLI is available.

The stable development branch is `extended`. Release-candidate testers can select a branch explicitly, for example:

```bash
/config/update_fsr.sh 1.2.0-rc
```

The example script below defaults to `extended` when no branch is supplied.

It:

1. refuses to overwrite local uncommitted repository changes;
2. fetches the requested remote branch;
3. switches to that branch when necessary;
4. compares the local and remote commit;
5. checks whether `custom_components/fireservicerota` actually changed;
6. runs `ha core check` before restarting when integration files changed.

Documentation-only updates therefore do not require a Home Assistant restart.

## Example directory layout

```text
/config/fireservicerota-extended/
/config/custom_components/fireservicerota/
/config/update_fsr.sh
```

Clone the repository once:

```bash
git clone --branch extended https://github.com/bjedelijn/home-assistant-fireservicerota.git /config/fireservicerota-extended
```

## Update script

Save this as `/config/update_fsr.sh`:

```bash
#!/bin/bash
set -e

REPO="/config/fireservicerota-extended"
TARGET="/config/custom_components/fireservicerota"
COMPONENT_PATH="custom_components/fireservicerota"
BRANCH="${1:-extended}"

echo "========================================"
echo " FireServiceRota Extended updater"
echo " Branch: $BRANCH"
echo "========================================"

cd "$REPO"

if [ -n "$(git status --porcelain)" ]; then
    echo "FOUT: lokale wijzigingen gevonden in $REPO."
    echo "Werk deze eerst weg voordat de updater van branch wisselt of pullt."
    exit 1
fi

echo
echo "[1/7] Remote informatie ophalen..."
git fetch origin "$BRANCH"

CURRENT_BRANCH="$(git branch --show-current)"
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo
    echo "[2/7] Wisselen van $CURRENT_BRANCH naar $BRANCH..."
    if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
        git switch "$BRANCH"
    else
        git switch --track -c "$BRANCH" "origin/$BRANCH"
    fi
else
    echo
    echo "[2/7] Branch: $CURRENT_BRANCH"
fi

LOCAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(git rev-parse "origin/$BRANCH")"

echo
echo "[3/7] Versiecontrole:"
echo "Lokaal : $(git rev-parse --short "$LOCAL_COMMIT")"
echo "Remote : $(git rev-parse --short "$REMOTE_COMMIT")"

if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
    echo
    echo "Geen update beschikbaar."
    echo "Home Assistant wordt niet herstart."
    exit 0
fi

LOCAL_COMPONENT_TREE="$(git rev-parse "$LOCAL_COMMIT:$COMPONENT_PATH")"
REMOTE_COMPONENT_TREE="$(git rev-parse "$REMOTE_COMMIT:$COMPONENT_PATH")"

echo
echo "[4/7] Repository bijwerken..."
git pull --ff-only origin "$BRANCH"

if [ "$LOCAL_COMPONENT_TREE" = "$REMOTE_COMPONENT_TREE" ]; then
    echo
    echo "Alleen documentatie of andere repository-bestanden zijn gewijzigd."
    echo "De FireServiceRota integratie zelf is ongewijzigd."
    echo "Home Assistant wordt niet herstart."
    exit 0
fi

echo
echo "[5/7] Integratie kopieren..."
rm -rf "$TARGET"
cp -r "$REPO/$COMPONENT_PATH" "$TARGET"

echo
echo "Geinstalleerde integratie:"
grep -E '"name"|"version"' "$TARGET/manifest.json"

echo
echo "[6/7] Home Assistant configuratie controleren..."
ha core check

echo
echo "[7/7] Home Assistant herstarten..."
ha core restart

echo
echo "Update voltooid."
```

Make it executable:

```bash
chmod +x /config/update_fsr.sh
```

Update the stable branch:

```bash
/config/update_fsr.sh
```

Test the 1.2.0 release candidate:

```bash
/config/update_fsr.sh 1.2.0-rc
```

Return to the stable branch:

```bash
/config/update_fsr.sh extended
```

## Notes

- `git pull --ff-only` stops instead of creating an unexpected local merge commit.
- The script refuses to continue when the repository has local uncommitted changes.
- It removes and replaces only the installed `custom_components/fireservicerota` directory.
- Keep a Home Assistant backup before using automated/custom update workflows.
- This is an optional convenience script, not part of Home Assistant's built-in update mechanism.
