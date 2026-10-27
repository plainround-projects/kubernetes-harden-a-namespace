#!/usr/bin/env bash
# Download the pinned command-line tools into ./.bin (kind and kubeconform), verifying each SHA-256.
# Nothing is installed system-wide. kubectl is not downloaded: use any kubectl within one minor version of
# the cluster (the cluster here is Kubernetes 1.35).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/.bin"
KIND_VERSION="v0.33.0"
KUBECONFORM_VERSION="v0.8.0"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) platform="darwin-arm64"; kind_sha="0c8c7dbe5e23594a198b786c4bc13dacc101fa6196b0cb0b23a1ca44e61f4b4f"; conform_sha="f84f4dfbebf4a6b0b230385fa065a39ea35e02608c2b50d025dcf64775a69d67" ;;
  Darwin-x86_64) platform="darwin-amd64"; kind_sha="5a99f26f57246dc9319dd294803313197a0f34d33c525b3ea8b655db5916ece0"; conform_sha="71dbc87ac9f24099a62b93570e65aa06312ba6ac8aea63b7f86e9d999edf5a92" ;;
  Linux-x86_64) platform="linux-amd64"; kind_sha="aee6151561422756b764a4ae28e7f44cda5af5a9eead3cc9985112b1de8d8e0d"; conform_sha="9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883" ;;
  Linux-aarch64 | Linux-arm64) platform="linux-arm64"; kind_sha="20022bee6cfcd5086cb7234d218e3454e6090022f2a8f55d1fa7fcf42c3867a2"; conform_sha="1f53fc8e81258197a35e8603054162a5af1de8c5af13746c71ab680d9534ed87" ;;
  *) echo "unsupported platform $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

check_sha() { # file expected
  local actual
  actual="$(shasum -a 256 "$1" | cut -d' ' -f1)"
  [ "$actual" = "$2" ] || { echo "checksum mismatch for $1: expected $2, got $actual" >&2; rm -f "$1"; exit 1; }
}

mkdir -p "$BIN"
if [ ! -x "$BIN/kind" ] || [ "$("$BIN/kind" version | awk '{print $2}')" != "$KIND_VERSION" ]; then
  echo "downloading kind $KIND_VERSION ($platform)"
  curl -fsSL -o "$BIN/kind" "https://github.com/kubernetes-sigs/kind/releases/download/$KIND_VERSION/kind-$platform"
  check_sha "$BIN/kind" "$kind_sha"
  chmod +x "$BIN/kind"
fi
if [ ! -x "$BIN/kubeconform" ] || ! "$BIN/kubeconform" -v | grep -q "${KUBECONFORM_VERSION#v}"; then
  echo "downloading kubeconform $KUBECONFORM_VERSION ($platform)"
  archive="$(mktemp)"
  curl -fsSL -o "$archive" "https://github.com/yannh/kubeconform/releases/download/$KUBECONFORM_VERSION/kubeconform-$platform.tar.gz"
  check_sha "$archive" "$conform_sha"
  tar -xzf "$archive" -C "$BIN" kubeconform
  rm -f "$archive"
fi
echo "tools ready in $BIN: $("$BIN/kind" version | cut -d' ' -f1-2), kubeconform $("$BIN/kubeconform" -v)"
