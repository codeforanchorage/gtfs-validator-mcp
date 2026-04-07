#!/bin/bash
# Downloads MobilityData GTFS Validator JAR and builds Etalab transport-validator
set -e

VALIDATORS_DIR="$(cd "$(dirname "$0")" && pwd)/bin"
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

# --- Etalab transport-validator (build from source, pinned to edition 2021) ---
# Pinned to 738d1b1c (Oct 2024) — last commit using Rust edition 2021,
# compatible with stable Rust on Replit. Later commits require edition 2024.
ETALAB_COMMIT="738d1b1c60"
ETALAB_BIN="$VALIDATORS_DIR/transport-validator"

if [ ! -f "$ETALAB_BIN" ]; then
  echo "Building Etalab transport-validator from source (commit ${ETALAB_COMMIT})..."
  ETALAB_BUILD_DIR=$(mktemp -d)
  git clone https://github.com/etalab/transport-validator.git "$ETALAB_BUILD_DIR"
  cd "$ETALAB_BUILD_DIR"
  git checkout "$ETALAB_COMMIT"
  cargo build --release --no-default-features
  # Find the built binary — name varies by Cargo version
  echo "Build artifacts:"
  ls -la target/release/
  # Try known possible names
  if [ -f target/release/main ]; then
    cp target/release/main "$ETALAB_BIN"
  elif [ -f target/release/validator ]; then
    cp target/release/validator "$ETALAB_BIN"
  else
    echo "ERROR: Could not find built binary. Contents of target/release/:"
    find target/release/ -maxdepth 1 -type f -executable
    exit 1
  fi
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
