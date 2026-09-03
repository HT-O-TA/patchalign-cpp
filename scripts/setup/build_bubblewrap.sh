#!/bin/bash
set -euo pipefail

VERSION=0.12.0
SOURCE_COMMIT=2a76602a8c71f36c1527cf9fc3417d9149822e0c
CONDA=/persist_data/apps/miniconda3/bin/conda
DESTINATION=${1:-/mingli01/project/ht/.tools/bubblewrap/${VERSION}}
BUILD_ENV=${DESTINATION}/build-env
SOURCE=${DESTINATION}/src
INSTALL=${DESTINATION}/install

test ! -e "${DESTINATION}"
mkdir -p "$(dirname "${DESTINATION}")"

"${CONDA}" create -y -p "${BUILD_ENV}" -c conda-forge \
  python=3.10 meson=1.12.0 ninja=1.13.2 libcap=2.78 pkg-config=0.29.2
git clone --quiet --depth 1 --branch "v${VERSION}" \
  https://github.com/containers/bubblewrap.git "${SOURCE}"
test "$(git -C "${SOURCE}" rev-parse HEAD)" = "${SOURCE_COMMIT}"

export PATH="${BUILD_ENV}/bin:/usr/bin:/bin"
export PKG_CONFIG="${BUILD_ENV}/bin/pkg-config"
export PKG_CONFIG_PATH="${BUILD_ENV}/lib/pkgconfig:${BUILD_ENV}/share/pkgconfig"
export CC=/usr/bin/gcc

"${BUILD_ENV}/bin/meson" setup "${SOURCE}/_build" \
  --prefix="${INSTALL}" \
  -Dpython="${BUILD_ENV}/bin/python" \
  -Dman=disabled \
  -Dselinux=disabled \
  -Dtests=false
"${BUILD_ENV}/bin/meson" compile -C "${SOURCE}/_build"
"${BUILD_ENV}/bin/meson" install -C "${SOURCE}/_build"

"${CONDA}" list --explicit -p "${BUILD_ENV}" > "${DESTINATION}/build-env-explicit.txt"
git -C "${SOURCE}" rev-parse HEAD > "${DESTINATION}/source-commit.txt"
sha256sum "${INSTALL}/bin/bwrap" > "${DESTINATION}/bwrap.sha256"
"${INSTALL}/bin/bwrap" --version
cat "${DESTINATION}/bwrap.sha256"
