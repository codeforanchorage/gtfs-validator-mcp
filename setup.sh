#!/bin/bash
# Downloads MobilityData GTFS Validator JAR and builds Etalab transport-validator
set -e

VALIDATORS_DIR="$(dirname "$0")/bin"
mkdir -p "$VALIDATORS_DIR"

# --- MobilityData GTFS Validator ---
MOBILITYDATA_VERSION="7.1.0"
MOBILITYDATA_JAR="$VALIDATORS_DIR/gtfs-validator.jar"

if [ ! -f "$MOBILITYDATA_JAR" ]; then
  echo "Downloading MobilityData GTFS Validator v${MOBILITYDATA_VERSION}..."
  curl -L -o "$MOBILITYDATA_JAR" \
    "https://github.com/MobilityData/gtfs-validator/releases/download/v${MOBILITYDATA_VERSION}/gtfs-validator-${MOBILITYDATA_VERSION}-cli.jar"
  echo "Downloaded: $MOBILITYDATA_JAR"
else
  echo "MobilityData validator already present: $MOBILITYDATA_JAR"
fi

# --- Etalab transport-validator (build from source) ---
ETALAB_BIN="$VALIDATORS_DIR/transport-validator"

if [ ! -f "$ETALAB_BIN" ]; then
  echo "Building Etalab transport-validator from source..."
  ETALAB_BUILD_DIR=$(mktemp -d)
  git clone --depth 1 https://github.com/etalab/transport-validator.git "$ETALAB_BUILD_DIR"
  cd "$ETALAB_BUILD_DIR"
  cargo build --release --no-default-features
  cp target/release/transport-validator "$ETALAB_BIN"
  chmod +x "$ETALAB_BIN"
  cd -
  rm -rf "$ETALAB_BUILD_DIR"
  echo "Built: $ETALAB_BIN"
else
  echo "Etalab validator already present: $ETALAB_BIN"
fi

echo ""
echo "Validators ready in $VALIDATORS_DIR:"
ls -la "$VALIDATORS_DIR"
