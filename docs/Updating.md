# Updating FireServiceRota Extended from Git

This is an optional update method for users who keep a local Git clone of the repository on Home Assistant.

The example below is intended for **Home Assistant OS / Supervised** installations where the `ha` CLI is available.

It does four important things:

1. explicitly follows the `extended` branch;
2. compares the local and remote repository commit;
3. checks whether `custom_components/fireservicerota` itself changed;
4. runs `ha core check` and restarts Home Assistant only when the integration changed.

This means README/docs-only updates can be pulled without unnecessarily restarting Home Assistant.

## Example directory layout

```text
/config/fireservicerota-extended/
/config/custom_components/fireservicerota/
/config/update_fsr.sh
```

Clone the repository once, for example from a terminal/add-on shell:

```bash
git clone --branch extended https://github.com/bjedelijn/home-assistant-fireservicerota.git /config/fireservicerota-extended
```

## Update script

Save this as:

```text
/config/update_fsr.sh
```

```bash
#!/bin/bash
set -e

REPO="/config/fireservicerota-extended"
TARGET="/config/custom_components/fireservicerota"
BRANCH="extended"
COMPONENT_PATH="custom_components/fireservicerota"

echo "========================================"
echo " FireServiceRota Extended updater"
echo "========================================"

cd "$REPO"

echo
echo "[1/7] Branch controleren..."

CURRENT_BRANCH="$(git branch --show-current)"

if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo "FOUT: repository staat op branch '$CURRENT_BRANCH'."
    echo "Verwacht: '$BRANCH'."
    exit 1
fi

echo "Branch: $CURRENT_BRANCH"

echo
echo "[2/7] Remote informatie ophalen..."
git fetch origin "$BRANCH"

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

echo
echo "Nieuwe repository-versie gevonden."

LOCAL_COMPONENT_TREE="$(git rev-parse "$LOCAL_COMMIT:$COMPONENT_PATH")"
REMOTE_COMPONENT_TREE="$(git rev-parse "$REMOTE_COMMIT:$COMPONENT_PATH")"

echo
echo "[4/7] Repository bijwerken..."
git pull --ff-only origin "$BRANCH"

echo
echo "Nieuwe commit:"
echo -n "Commit: "
git rev-parse --short HEAD
echo -n "Omschrijving: "
git log -1 --pretty=%s

if [ "$LOCAL_COMPONENT_TREE" = "$REMOTE_COMPONENT_TREE" ]; then
    echo
    echo "Alleen documentatie of andere repository-bestanden zijn gewijzigd."
    echo "De FireServiceRota integratie zelf is ongewijzigd."
    echo "Home Assistant wordt niet herstart."
    echo
    echo "========================================"
    echo " Repository bijgewerkt"
    echo "========================================"
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
echo "========================================"
echo " Update voltooid"
echo "========================================"
```

Make it executable:

```bash
chmod +x /config/update_fsr.sh
```

Run it manually:

```bash
/config/update_fsr.sh
```

## Expected behavior

If nothing changed:

```text
Geen update beschikbaar.
Home Assistant wordt niet herstart.
```

If only documentation or other non-integration files changed:

```text
Alleen documentatie of andere repository-bestanden zijn gewijzigd.
De FireServiceRota integratie zelf is ongewijzigd.
Home Assistant wordt niet herstart.
```

If the integration changed, the script:

```text
pulls the new commit
copies custom_components/fireservicerota
runs ha core check
restarts Home Assistant
```

## Notes

- The script deliberately follows `extended` even though it is also the repository default branch.
- `git pull --ff-only` stops instead of creating an unexpected local merge commit.
- Local uncommitted changes in the clone can cause the update to stop; resolve those before retrying.
- The script removes and replaces only the installed `custom_components/fireservicerota` directory.
- Keep a backup before using automated/custom update workflows.
- This is an optional convenience script, not part of Home Assistant's built-in update mechanism.
