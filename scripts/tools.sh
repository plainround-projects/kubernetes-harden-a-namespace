#!/usr/bin/env bash
# Download the pinned command-line tools into ./.bin (k3d and kubeconform), verifying each SHA-256.
# Nothing is installed system-wide. kubectl is not downloaded: use any kubectl within one minor version of
# the cluster (the cluster here is Kubernetes 1.35).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/.bin"
K3D_VERSION="v5.9.0"
KUBECONFORM_VERSION="v0.8.0"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) platform="darwin-arm64"; k3d_sha="fe106541d5d0a3f18debcd4d432a16f8c0ce3e6ddc06f8fbb6f696a122313e00"; conform_sha="f84f4dfbebf4a6b0b230385fa065a39ea35e02608c2b50d025dcf64775a69d67" ;;
  Darwin-x86_64) platform="darwin-amd64"; k3d_sha="b4aabc37534f95b9c764e7823f2df923f50d57600837aa60a06266cce47db732"; conform_sha="71dbc87ac9f24099a62b93570e65aa06312ba6ac8aea63b7f86e9d999edf5a92" ;;
  Linux-x86_64) platform="linux-amd64"; k3d_sha="06d8f25bc3a971c4eb29e0ff08429b180402db0f4dec838c9eac427e296800a0"; conform_sha="9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883" ;;
  Linux-aarch64 | Linux-arm64) platform="linux-arm64"; k3d_sha="03cde5cf23e6e8e67de5a039ecf26e5b85aca82fba3e5d13dadf904cd218a250"; conform_sha="1f53fc8e81258197a35e8603054162a5af1de8c5af13746c71ab680d9534ed87" ;;
  *) echo "unsupported platform $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

check_sha() { # file expected
  local actual
  actual="$(shasum -a 256 "$1" | cut -d' ' -f1)"
  [ "$actual" = "$2" ] || { echo "checksum mismatch for $1: expected $2, got $actual" >&2; rm -f "$1"; exit 1; }
}

mkdir -p "$BIN"
if [ ! -x "$BIN/k3d" ] || ! "$BIN/k3d" version 2>/dev/null | grep -q "k3d version $K3D_VERSION"; then
  echo "downloading k3d $K3D_VERSION ($platform)"
  curl -fsSL -o "$BIN/k3d" "https://github.com/k3d-io/k3d/releases/download/$K3D_VERSION/k3d-$platform"
  check_sha "$BIN/k3d" "$k3d_sha"
  chmod +x "$BIN/k3d"
fi
if [ ! -x "$BIN/kubeconform" ] || ! "$BIN/kubeconform" -v | grep -q "${KUBECONFORM_VERSION#v}"; then
  echo "downloading kubeconform $KUBECONFORM_VERSION ($platform)"
  archive="$(mktemp)"
  curl -fsSL -o "$archive" "https://github.com/yannh/kubeconform/releases/download/$KUBECONFORM_VERSION/kubeconform-$platform.tar.gz"
  check_sha "$archive" "$conform_sha"
  tar -xzf "$archive" -C "$BIN" kubeconform
  rm -f "$archive"
fi
echo "tools ready in $BIN: $("$BIN/k3d" version | head -1), kubeconform $("$BIN/kubeconform" -v)"
