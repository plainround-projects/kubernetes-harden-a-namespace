# Bash (the scripts)

## 1. What it is

A **shell** is a program that reads commands you type and runs them. **Bash** is the most common shell on Linux and macOS. A **shell script** is a text file of commands that Bash runs from top to bottom, with variables, `if` tests, loops and functions added. The files in `scripts/` are Bash scripts; the first line `#!/usr/bin/env bash` (the **shebang**) tells the operating system to run the file with Bash.

Words you need:

- A **variable** holds text: `name="value"`, read back as `$name` or `${name}`. Always put double quotes around a use (`"$name"`) so spaces do not split it into several words.
- `$(command)` runs the command and gives its output as text. `$1`, `$2` are the script's arguments; `$@` is all of them; `$#` counts them; `$?` is the exit status of the last command.
- An **exit status** is a number every command returns: 0 means success, anything else failure. `if`, `&&` (and then) and `||` (or else) all work on it.
- **Standard output** and **standard error** are the two output channels. `>file` sends output to a file, `2>&1` joins error to output, `>/dev/null` throws output away, `|` (pipe) feeds one command's output to the next one's input, `<file` feeds a file in.
- `&` at the end of a command runs it in the **background**; `$!` is its process number.
- `trap 'commands' EXIT` runs the commands when the script ends, however it ends.

## 2. Why this repository uses it

`make` targets are one-liners; the real work (create a cluster, build and retag images, put two teams in a stage, switch one control off, run the attacks) takes several steps with checks. Bash is on every machine, needs no installation and is the natural glue around `kubectl`, `docker` and `curl`. Each script is small and does one job.

## 3. Where it appears

| Script | Job |
| --- | --- |
| `scripts/lib.sh` | Settings (cluster, teams, image names) and helper functions, sourced by the others. |
| `scripts/tools.sh` | Download `k3d` and `kubeconform` into `.bin`, verifying checksums. |
| `scripts/cluster-start.sh` | Create the cluster under a lock and wait for the node. |
| `scripts/cluster-down.sh` | Delete the cluster. |
| `scripts/build-images.sh` | Build the web image, retag Postgres and pause under the approved registry's name, import all three. |
| `scripts/create-secrets.sh` | Create each team's namespace and database Secret (see `postgres.md`). |
| `scripts/db.sh` | Run the SQL scripts inside a team's database pod (see `postgres.md`). |
| `scripts/stage.sh` | Put both teams into baseline, hardened or hardened-minus-one-control. |
| `scripts/run-attacks.sh` | Run the attacks and print a verdict each (see `attacks.md`). |
| `attacks/lib.sh`, `attacks/02-*.sh`, `attacks/03-*.sh` | The shell attacks (see `attacks.md`). |

## 4. How it works underneath

When you run `scripts/deploy.sh local`, the operating system reads the shebang, starts Bash with the file and the argument `local`. Bash runs each line in order. External commands (`kubectl`, `docker`) are separate programs that Bash starts and waits for. `source file` (also written `. file`) runs another file's lines inside the current shell, so its variables and functions become available: that is how `lib.sh` shares settings.

`set -euo pipefail` at the top makes scripts fail loudly instead of continuing after a mistake: `-e` stops at the first command that fails, `-u` treats an unset variable as an error, and `pipefail` makes a pipeline fail if any part fails (normally only the last part counts).

`${NAME:-default}` means "the value of `NAME`, or `default` if it is unset or empty". `[ -d dir ]` tests that a directory exists, `[ -f file ]` a file, `[ -x file ]` an executable, `[ -n s ]` a non-empty string. `case "$x" in pattern) ...;; esac` chooses by pattern. `until cmd; do ...; done` repeats while `cmd` fails. Arrays are written `names=(a b c)` and read `"${names[@]}"`.

The lock in `cluster-start.sh` uses a trick: `mkdir` either creates a directory or fails, and the operating system makes that check-and-create **atomic** (it cannot be interrupted halfway), so only one script can win. The winner writes its process number into the directory and removes the directory on exit; a waiting script that finds a lock whose owner process no longer exists (`kill -0` tests existence without sending a signal) removes the stale lock.

## 5. Walkthrough of this repository's use

### `scripts/tools.sh`

```bash
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
```

The comment says what is downloaded and that nothing is installed system-wide. `set -euo pipefail` as explained above. `ROOT` as in `lib.sh` (this script does not source it because it runs before anything else exists). `BIN` is the `.bin` folder. `K3D_VERSION="v5.9.0"` and `KUBECONFORM_VERSION="v0.8.0"` pin the versions. The `case "$(uname -s)-$(uname -m)" in` looks at the operating system and processor architecture (`Darwin-arm64` is an Apple-silicon Mac, `Linux-x86_64` an ordinary Linux server and so on). Each branch sets `platform` (the name used in download file names) and two SHA-256 hashes: `k3d_sha` for the k3d program and `conform_sha` for the kubeconform archive; the `;;` ends the branch. These hashes were taken from the official releases; if a download differs by one bit the script refuses it. The `|` in `Linux-aarch64 | Linux-arm64` lets either name match. The `*)` branch prints an error for any other machine and exits.

```bash
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
```

`check_sha()` is a function: `local actual` declares a private variable, `shasum -a 256 "$1" | cut -d' ' -f1` computes the file's hash and keeps the first column, and `[ "$actual" = "$2" ] || { ...; exit 1; }` compares it with the expected value, and on a mismatch prints both, deletes the file and exits. `mkdir -p "$BIN"` makes the folder. The first `if` downloads k3d unless an executable with the right version is already there: `! -x` tests "not executable", `k3d version | grep -q` tests the version text. `curl -fsSL -o file url` downloads quietly (`-f` fail on HTTP errors, `-s` silent, `-S` still show errors, `-L` follow redirects), then `check_sha` verifies, then `chmod +x` makes it runnable. The second `if` does the same for kubeconform, which comes as a `.tar.gz` archive: `mktemp` makes a temporary file name, `tar -xzf ... -C "$BIN" kubeconform` unpacks just that one file into `.bin`, and `rm -f` deletes the archive. `${KUBECONFORM_VERSION#v}` strips a leading `v`. The last `echo` prints the versions that are ready.

### `scripts/cluster-start.sh`

```bash
#!/usr/bin/env bash
# Create the local k3d cluster (idempotent) and wait for its node to be Ready.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
```

Shebang, a comment, `set -euo pipefail`, then `# shellcheck source=lib.sh` (tells the checker where the sourced file is) and `source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"` to load the shared settings.

```bash
"$ROOT/scripts/tools.sh" >/dev/null
mkdir -p "$(dirname "$KUBECONFIG")"
if "$K3D" cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
  log "cluster $CLUSTER_NAME already exists"
  "$K3D" cluster start "$CLUSTER_NAME" >/dev/null 2>&1 || true
else
  log "creating k3d cluster $CLUSTER_NAME (Kubernetes 1.35, one node)"
  # One cluster is created at a time on this machine: take the lock directory, wait if another run holds it.
  lock=/tmp/plainround-kind-create.lock
  until mkdir "$lock" 2>/dev/null; do
    holder="$(cat "$lock/pid" 2>/dev/null || true)"
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$lock"; continue; fi
    log "another cluster is being created (pid ${holder:-unknown}); waiting 30 seconds"
    sleep 30
  done
  echo $$ >"$lock/pid"
  trap 'rm -rf "$lock"' EXIT
  # The project's own kubeconfig is written below; ~/.kube/config is left alone.
  "$K3D" cluster create "$CLUSTER_NAME" --config "$ROOT/cluster/k3d-config.yaml" \
    --kubeconfig-update-default=false --kubeconfig-switch-context=false
fi
"$K3D" kubeconfig write "$CLUSTER_NAME" --output "$KUBECONFIG" >/dev/null
kubectl wait --for=condition=Ready nodes --all --timeout=600s
kubectl get nodes
```

`"$ROOT/scripts/tools.sh" >/dev/null` makes sure the tools exist, hiding its output; `mkdir -p "$(dirname "$KUBECONFIG")"` creates the `.kube` folder. The `if` asks k3d for its cluster list without a header (`--no-headers`), keeps the first column with `awk '{print $1}'` and tests with `grep -qx` whether a line equals the cluster name exactly (`-q` quiet, `-x` whole line). If the cluster exists, say so and try `k3d cluster start` (so a stopped cluster is revived; `|| true` ignores the failure). Otherwise: log, then take the lock described above: `lock=/tmp/plainround-kind-create.lock`; `until mkdir "$lock" 2>/dev/null; do` repeats until the directory can be created; inside, `holder` reads the owner's number; if there is one and `kill -0` shows that process is dead, the stale lock is removed and the loop continues; otherwise it logs and sleeps 30 seconds. After winning, `echo $$ >"$lock/pid"` records this script's own process number (`$$`) and `trap 'rm -rf "$lock"' EXIT` removes the lock when the script ends. The lock exists because creating several clusters at once on one laptop made all of them time out. Then `k3d cluster create` with `--config` (the YAML in `k3d.md`), `--kubeconfig-update-default=false` and `--kubeconfig-switch-context=false` (do not touch the user's own kubeconfig). After the `fi`, `k3d kubeconfig write ... --output "$KUBECONFIG"` saves the credentials in the project's file, `kubectl wait --for=condition=Ready nodes --all --timeout=600s` waits up to ten minutes for the node and `kubectl get nodes` shows it.

### `scripts/cluster-down.sh`

```bash
#!/usr/bin/env bash
# Delete the local k3d cluster and its kubeconfig.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [ -x "$K3D" ] && "$K3D" cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
  "$K3D" cluster delete "$CLUSTER_NAME"
else
  log "no cluster named $CLUSTER_NAME"
fi
rm -rf "$ROOT/.kube"
```

Same header. If the k3d binary exists (`-x`) and the cluster is listed, `k3d cluster delete` removes it; otherwise it logs that there is nothing to delete. Finally `rm -rf "$ROOT/.kube"` removes the generated credentials, so after `make down` nothing of the cluster remains.

### `scripts/lib.sh`

```bash
#!/usr/bin/env bash
# shellcheck shell=bash
# Shared settings for the scripts. Sourced, not run.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-harden}"
TEAMS="team-a team-b"
# The approved registry is a name only. No registry exists: images are built or retagged with this prefix
# and loaded into the nodes, and the admission policy in manifests/platform allows nothing else.
REGISTRY="${REGISTRY:-registry.example.test/platform}"
WEB_IMAGE="$REGISTRY/tenant-web:0.1.0"
DB_IMAGE="$REGISTRY/postgres:17-alpine"
PAUSE_IMAGE="$REGISTRY/pause:3.10"
K3D="$ROOT/.bin/k3d"
export ROOT CLUSTER_NAME TEAMS REGISTRY WEB_IMAGE DB_IMAGE PAUSE_IMAGE K3D
# A kubeconfig of its own: this project never reads or changes ~/.kube/config.
export KUBECONFIG="${KUBECONFIG:-$ROOT/.kube/config}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
```

Shebang and the hint `# shellcheck shell=bash`; the file is **sourced**, never run. `ROOT` is found as in the other scripts (the folder above `scripts/`). Settings with overridable defaults: `CLUSTER_NAME` (`harden`), `TEAMS="team-a team-b"` (a space-separated list the other scripts split), `REGISTRY` (the approved registry's name; the comment says no registry exists, images are retagged with this prefix and imported into the node, and the admission policy allows nothing else), and the three image names built from it: `WEB_IMAGE`, `DB_IMAGE` and `PAUSE_IMAGE`. `K3D` is the downloaded binary. `export` makes them visible to programs the scripts start, and `KUBECONFIG` points `kubectl` at the project's own credentials file. `log()` prints a line starting with `==>`; `die()` prints an error on standard error and exits with status 1.

```bash
require_cluster() {
  kubectl get nodes >/dev/null 2>&1 || die "no cluster reachable through $KUBECONFIG; run: make up"
}

# Render a Kustomize directory. The database init scripts are read from sql/ at the repository root, which
# is outside the kustomization, so the load restrictor is relaxed (files only, and only inside this repository).
render() { kubectl kustomize --load-restrictor=LoadRestrictionsNone "$@"; }
```

`require_cluster()` runs `kubectl get nodes` with output discarded and, if that fails, calls `die` with the hint to run `make up`. `render()` wraps `kubectl kustomize --load-restrictor=LoadRestrictionsNone "$@"`: the comment explains that the database init scripts are in `sql/` at the repository root, outside the kustomization, so the load restrictor is relaxed for this repository's own files.

### `scripts/build-images.sh`

```bash
#!/usr/bin/env bash
# Build the web image and give the three images the approved registry's name, then import them into the
# node of the k3d cluster (there is no registry: the name is what the admission policy checks).
#   tenant-web  built from the Dockerfile
#   postgres    the official image, retagged
#   pause       the Kubernetes pause image, retagged; the attack pods run it because it does nothing
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

log "building $WEB_IMAGE"
docker build --tag "$WEB_IMAGE" "$ROOT"
retag() { # source target
  docker image inspect "$1" >/dev/null 2>&1 || docker pull "$1"
  docker tag "$1" "$2"
}
retag postgres:17-alpine "$DB_IMAGE"
retag registry.k8s.io/pause:3.10 "$PAUSE_IMAGE"
if "$K3D" cluster list --no-headers 2>/dev/null | awk '{print $1}' | grep -qx "$CLUSTER_NAME"; then
  log "importing the images into cluster $CLUSTER_NAME"
  "$K3D" image import "$WEB_IMAGE" "$DB_IMAGE" "$PAUSE_IMAGE" --cluster "$CLUSTER_NAME" --mode direct
fi
```

The comment lists the three images: `tenant-web` is built from the Dockerfile, `postgres` is the official image retagged, `pause` is the Kubernetes pause image retagged (the attack pods run it because it does nothing). `docker build --tag "$WEB_IMAGE" "$ROOT"` builds the web image under the approved name. `retag source target` is a function: if the source image is not yet on the machine (`docker image inspect` fails), `docker pull` fetches it; then `docker tag` gives it the new name. The two retags use `postgres:17-alpine` and `registry.k8s.io/pause:3.10`. If the cluster exists, `k3d image import` copies all three images into the node (`--mode direct`).

### `scripts/stage.sh`

```bash
#!/usr/bin/env bash
# Put both team namespaces into a stage and wait until their workloads are ready.
#   stage.sh baseline          workloads only, plus the careless convenience binding: no control at all
#   stage.sh hardened          every control: RBAC, Pod Security, NetworkPolicy, quota, admission policy
#   stage.sh without <control> hardened with one control switched off (rbac, pod-security, network-policy,
#                              quota or admission-policy), to show that control is what stops its attack
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
require_cluster

CONTROLS=(rbac pod-security network-policy quota admission-policy)
read -ra team_list <<<"$TEAMS"
stage="${1:-hardened}"
off="${2:-}"
case "$stage" in
  baseline | hardened) ;;
  without) printf '%s\n' "${CONTROLS[@]}" | grep -qx "${off:-none}" || die "usage: stage.sh without <${CONTROLS[*]// /|}>" ;;
  *) die "usage: stage.sh baseline|hardened|without <control>" ;;
esac
```

The header documents three stages and the `without <control>` form. After the usual setup, `CONTROLS` is an array of the five control names; `read -ra team_list <<<"$TEAMS"` splits the team list; `stage` and `off` take the first two arguments with defaults. The `case` accepts `baseline` or `hardened`, and for `without` it checks the control name is in the array (`printf '%s\n' "${CONTROLS[@]}" | grep -qx ...`) or dies with the usage; any other word dies with the usage.

```bash
# Remove every object a control created, so a stage never inherits a control from the previous one. Pod
# Security labels live on the namespace, so they are removed from there.
reset_controls() {
  kubectl delete role,rolebinding,networkpolicy,resourcequota,limitrange -A -l platform.example/control --ignore-not-found >/dev/null
  kubectl delete clusterrolebinding,validatingadmissionpolicy,validatingadmissionpolicybinding -l platform.example/control --ignore-not-found >/dev/null
  for team in "${team_list[@]}"; do
    kubectl label namespace "$team" pod-security.kubernetes.io/enforce- pod-security.kubernetes.io/enforce-version- \
      pod-security.kubernetes.io/warn- pod-security.kubernetes.io/audit- >/dev/null 2>&1 || true
  done
}
```

`reset_controls()` removes everything a control created so a stage never inherits one from the last: it deletes Roles, RoleBindings, NetworkPolicies, ResourceQuotas and LimitRanges in all namespaces (`-A`) that carry the label `platform.example/control`, then the cluster-scoped ClusterRoleBindings, admission policies and bindings with that label (`--ignore-not-found` makes it harmless when none exist). Pod Security labels are on the namespace itself, so for each team `kubectl label namespace ... name-` (a trailing dash removes a label) strips the four labels; `|| true` ignores the case where they are absent.

```bash
# hardened minus one control, written to a throwaway kustomization next to the kubeconfig (git-ignored)
generate_without() {
  local dir="$ROOT/.kube/stage" team control
  rm -rf "$dir"
  for team in "${team_list[@]}"; do
    mkdir -p "$dir/$team"
    {
      printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nnamespace: %s\nresources:\n  - ../../../manifests/base\ncomponents:\n' "$team"
      if [ "$off" = "rbac" ]; then printf '  - ../../../manifests/controls/careless-rbac\n'; else printf '  - ../../../manifests/controls/rbac\n'; fi
      for control in pod-security network-policy quota; do
        [ "$control" = "$off" ] || printf '  - ../../../manifests/controls/%s\n' "$control"
      done
      printf '  - ../../../manifests/identity/%s\n' "$team"
    } >"$dir/$team/kustomization.yaml"
  done
  {
    printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n'
    printf '  - %s\n' "${team_list[@]}"
    [ "$off" = "admission-policy" ] || printf '  - ../../manifests/platform/admission-policy\n'
  } >"$dir/kustomization.yaml"
  echo "$dir"
}
```

`generate_without()` builds "hardened minus one control" as a throwaway kustomization under `.kube/stage` (ignored by git). For each team it writes a `kustomization.yaml` with `printf` and a group of commands redirected into the file: header, the base, then components: `careless-rbac` when RBAC is the control being switched off, otherwise `rbac`; then each of `pod-security`, `network-policy` and `quota` unless it is the one switched off; and the team's identity last. It then writes a top-level kustomization listing the teams and, unless the admission policy is the one switched off, the platform policy. It prints the directory's path.

```bash
"$ROOT/scripts/create-secrets.sh"
case "$stage" in
  baseline | hardened) source_dir="$ROOT/manifests/overlays/$stage" ;;
  without) source_dir="$(generate_without)" ;;
esac
log "stage: $stage ${off}"
reset_controls
# Server-side apply: an object this script just took a label or a field from is put back by the apply,
# where a client-side apply would believe nothing had changed.
render "$source_dir" | kubectl apply --server-side --force-conflicts -f - >/dev/null
for team in "${team_list[@]}"; do
  kubectl -n "$team" rollout status deployment/db --timeout=600s
  kubectl -n "$team" rollout status deployment/web --timeout=600s
done
```

`create-secrets.sh` runs first. A `case` chooses the source: the committed overlay for baseline and hardened, or the generated folder for `without`. Then it logs the stage, resets the controls, renders the chosen source and applies it with `kubectl apply --server-side --force-conflicts -f -` (the comment says why: an object this script just took a label or a field from is put back by the apply, where a client-side apply would believe nothing had changed). Finally, for each team it waits until the `db` and `web` Deployments have rolled out (600 seconds each).


## 6. Try it yourself

```bash
bash -n scripts/stage.sh && echo syntax ok
```

`-n` reads the script without running it: prints `syntax ok`.

```bash
.venv/bin/shellcheck -x scripts/*.sh attacks/*.sh && echo clean
```

No output other than `clean` (see `shellcheck.md`).

```bash
scripts/stage.sh nonsense
```

Prints `error: no cluster reachable ...` without a cluster, or `error: usage: stage.sh baseline|hardened|without <control>` with one, and exits with status 1 (`echo $?`).

```bash
make up && scripts/stage.sh without quota && scripts/run-attacks.sh attacks/04-exhaust-memory.yaml
```

The quota is removed from both teams; attack 4 prints `SUCCEEDED (50 of 50 pods were created)`. Restore with `make harden`.

## 7. Mistakes people make

- **Unquoted variables.** `rm -rf $dir/` with an empty `dir` becomes `rm -rf /`. Always `"$dir"`.
- **No `set -e`.** The script carries on after a failed step and reports success. (The attack scripts deliberately omit `-e` because they report failure themselves.)
- **Parsing `ls` output.** The scripts use `grep -qx` and `awk '{print $1}'` on commands made for scripting.
- **Assuming macOS and Linux tools match.** The checksum command is `shasum -a 256` on both here, not `sha256sum`.
- **Leaving a stage half applied.** `stage.sh` first removes every object a control created, so a stage never inherits a control from the previous one.

## 8. Check yourself

1. What does `set -euo pipefail` do? *Stop on errors, on unset variables and on a failing pipeline part.*
2. Why does `stage.sh` call `reset_controls` before applying? *So the new stage starts without leftovers of the previous one.*
3. Why `kubectl apply --server-side --force-conflicts`? *An object whose label or field the script just removed is put back; client-side apply would believe nothing changed.*
4. How does the lock stay safe if a script crashes? *The next script sees the owner process is gone and removes the lock.*
5. What does `stage.sh without rbac` build? *Hardened with the careless binding instead of the RBAC control.*

## 9. Further reading

- Bash reference manual: https://www.gnu.org/software/bash/manual/bash.html
- The set builtin: https://www.gnu.org/software/bash/manual/bash.html#The-Set-Builtin
- Shell parameter expansion: https://www.gnu.org/software/bash/manual/bash.html#Shell-Parameter-Expansion
- Conditional expressions: https://www.gnu.org/software/bash/manual/bash.html#Bash-Conditional-Expressions
