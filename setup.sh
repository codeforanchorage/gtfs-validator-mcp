#!/bin/bash
# Downloads MobilityData GTFS Validator JAR and Etalab transport-validator binary
set -e

VALIDATORS_DIR="$(dirname "$0")/bin"
mkdir -p "$VALIDATORS_DIR"

# --- MobilityData GTFS Validator ---
MOBILITYDATA_VERSION="6.0.0"
MOBILITYDATA_JAR="$VALIDATORS_DIR/gtfs-validator.jar"

if [ ! -f "$MOBILITYDATA_JAR" ]; then
  echo "Downloading MobilityData GTFS Validator v${MOBILITYDATA_VERSION}..."
  curl -L -o "$MOBILITYDATA_JAR" \
    "https://github.com/MobilityData/gtfs-validator/releases/download/v${MOBILITYDATA_VERSION}/gtfs-validator-${MOBILITYDATA_VERSION}_cli.jar"
  echo "Downloaded: $MOBILITYDATA_JAR"
else
  echo "MobilityData validator already present: $MOBILITYDATA_JAR"
fi

# --- Etalab transport-validator ---
ETALAB_VERSION="0.49.0"
ETALAB_BIN="$VALIDATORS_DIR/transport-validator"

if [ ! -f "$ETALAB_BIN" ]; then
  echo "Downloading Etalab transport-validator v${ETALAB_VERSION}..."
  curl -L -o "${ETALAB_BIN}.tar.gz" \
    "https://github.com/etalab/transport-validator/releases/download/v${ETALAB_VERSION}/transport-validator-v${ETALAB_VERSION}-x86_64-unknown-linux-gnu.tar.gz"
  tar -xzf "${ETALAB_BIN}.tar.gz" -C "$VALIDATORS_DIR"
  rm "${ETALAB_BIN}.tar.gz"
  chmod +x "$ETALAB_BIN"
  echo "Downloaded: $ETALAB_BIN"
else
  echo "Etalab validator already present: $ETALAB_BIN"
fi

echo ""
echo "Validators ready in $VALIDATORS_DIR:"
ls -la "$VALIDATORS_DIR"
