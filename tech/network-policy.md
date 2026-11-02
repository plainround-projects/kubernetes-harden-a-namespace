# NetworkPolicy

## 1. What it is

By default every pod in a Kubernetes cluster can open a connection to every other pod, in any namespace. A **NetworkPolicy** object changes that for the pods it selects. It has:

- a `podSelector`: which pods the policy is about (`{}` means all pods in the namespace);
- `policyTypes`: `Ingress` (traffic coming in to those pods), `Egress` (traffic going out), or both;
- `ingress` / `egress` rules: the *allowed* peers (selected by pod labels, namespace labels or IP ranges) and **ports**.

Once any policy selects a pod for a direction, that direction becomes **deny by default** for that pod and only what some policy allows is permitted; policies only add allowances and are combined with OR. Kubernetes stores the policy, but a **network plugin** must enforce it. k3s ships one (kube-router's policy controller), which is why the lesson can run on k3d.

## 2. Why this repository uses it

Control 3, stopping attack 3: a compromised web pod in team A opens a connection to team B's database port. The hardened namespaces deny everything, then allow exactly three things: DNS lookups, the web pods talking to their own database, and the database accepting only that.

## 3. Where it appears

| File | Role |
| --- | --- |
| `manifests/controls/network-policy/default-deny.yaml` | Deny all traffic, both directions. |
| `manifests/controls/network-policy/allow-dns.yaml` | Allow name lookups. |
| `manifests/controls/network-policy/web-to-db.yaml` | The one flow the app needs, stated at both ends. |
| `manifests/controls/network-policy/kustomization.yaml` | The control as a Component. |
| `attacks/03-cross-namespace-db.sh` | The attack it stops. |

## 4. How it works underneath

Pods get IP addresses from the cluster network. The policy controller on each node turns the NetworkPolicy objects into packet-filter rules (in k3s, `iptables`/`ipset` rules managed by kube-router). A connection attempt that matches no allow rule is stopped by the node: k3s's controller **rejects** it, so the client sees `Connection refused` at once, while a plugin that drops packets silently would show a **timeout** instead. Both mean blocked, and the attack script accepts either as the proof; it first checks the team's *own* database is reachable so it never calls a broken namespace "blocked".

Names inside the cluster are resolved by CoreDNS, a pod in `kube-system` labelled `k8s-app=kube-dns`. A default-deny egress policy also blocks DNS, which makes every name lookup fail and the whole namespace look broken; hence the `allow-dns` policy. Because the kubelet's own health probes come from the node itself, k3s lets node traffic through, so probes keep working.

## 5. Walkthrough of this repository's use

### `manifests/controls/network-policy/default-deny.yaml`

```yaml
# Both directions, every pod. A default-deny for ingress only would leave every pod free to start
# connections to anywhere, including the other team's database.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
```

The comment says why both directions: ingress-only would leave every pod free to start connections anywhere. `kind: NetworkPolicy`, name `default-deny`, `podSelector: {}` (all pods) and `policyTypes: [Ingress, Egress]` with no rules at all, so nothing is allowed in either direction.

### `manifests/controls/network-policy/allow-dns.yaml`

```yaml
# The rule every default-deny egress policy needs first: without it no pod can resolve any name, including
# the Service names it was supposed to be allowed to reach, and the whole namespace looks broken.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

The comment explains the DNS rule: without it no pod can resolve any name. The policy `allow-dns` applies to all pods, type `Egress`. Its one rule allows traffic `to` pods that match both selectors: a namespace labelled `kubernetes.io/metadata.name: kube-system` (Kubernetes sets this label on every namespace) and a pod labelled `k8s-app: kube-dns`; on UDP and TCP port 53.

### `manifests/controls/network-policy/web-to-db.yaml`

```yaml
# The one flow the application needs, stated at both ends: the web pods may open port 5432 to this
# namespace's database pods, and the database pods accept port 5432 from this namespace's web pods. Nothing
# else is allowed, so the web pods cannot reach the other team's database, and nothing but the web pods
# can reach this one.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: web-egress-to-db
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes: [Egress]
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: db
      ports:
        - protocol: TCP
          port: 5432
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: db-ingress-from-web
spec:
  podSelector:
```

The comment names the single flow the app needs, stated at both ends. The first policy, `web-egress-to-db`, selects pods `app: web`, type Egress, and allows traffic to pods `app: db` (in the same namespace, since no namespace selector is given) on TCP 5432. After `---` the second policy, `db-ingress-from-web`, begins: it selects pods `app: db`, type `Ingress`.

```yaml
    matchLabels:
      app: db
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: web
      ports:
        - protocol: TCP
          port: 5432
```

Its rule allows traffic `from` pods `app: web` on TCP 5432. Nothing else can reach the database, and the web pods can reach nothing else but DNS.

### `manifests/controls/network-policy/kustomization.yaml`

```yaml
# Control 3, NetworkPolicy: deny all traffic in both directions, then allow only DNS, web to its own
# database, and the database's acceptance of exactly that. Needs a cluster whose network layer enforces
# policy (k3s does). The kubelet's health probes still reach the pods: k3s lets traffic from its own node through.
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
labels:
  - pairs:
      platform.example/control: network-policy
    includeSelectors: false
resources:
  - default-deny.yaml
  - allow-dns.yaml
  - web-to-db.yaml
```

The comment lists what is allowed (DNS, web to its own database, and the database's acceptance of exactly that), notes the control needs a network layer that enforces policy (k3s does) and says the kubelet's health probes still reach the pods because k3s lets traffic from its own node through. A Component labelled `platform.example/control: network-policy` listing the three files.

### `attacks/03-cross-namespace-db.sh`

```bash
#!/usr/bin/env bash
# Attack 3: from inside team A's web pod, open a connection to team B's database port. Only NetworkPolicy
# stands in the way. Team A's own database is tried first: if that fails too, the test says so instead of
# calling a broken namespace "blocked".
set -uo pipefail
# shellcheck source=attacks/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

probe() { # host -> connected | timed out | refused | <error>
  kubectl -n "$ATTACKER_TEAM" exec deploy/web -- python -c '
import socket, sys
connection = socket.socket()
connection.settimeout(4)
try:
    connection.connect((sys.argv[1], 5432))
    print("connection succeeded")
except TimeoutError:
    print("connect: Connection timed out")
except OSError as error:
    print("connect: " + str(error))
' "$1" 2>&1 | tail -1
}
```

The header comment: from inside team A's web pod, open a connection to team B's database port; own database is tried first. `set -uo pipefail` (no `-e`: the script handles failures itself), then sources the shared attack library. The function `probe` (host in, one word of result out) runs a short Python program inside the web pod with `kubectl exec deploy/web -- python -c '...'`: it opens a TCP socket with a 4-second timeout, connects to the given host on port 5432 and prints `connection succeeded`, or `connect: Connection timed out` on a timeout, or `connect: <error>` for any other OS error. `"$1" 2>&1 | tail -1` passes the host as the program's first argument and keeps the last output line.

```bash
own="$(probe "db.$ATTACKER_TEAM.svc.cluster.local")"
other="$(probe "db.$VICTIM_TEAM.svc.cluster.local")"
printf '    %s web -> %s db:  %s\n' "$ATTACKER_TEAM" "$ATTACKER_TEAM" "$own"
printf '    %s web -> %s db:  %s\n' "$ATTACKER_TEAM" "$VICTIM_TEAM" "$other"
if [ "$own" != "connection succeeded" ]; then
  echo "INCONCLUSIVE (the team's own database is unreachable too, so nothing was proven)"
  exit 2
fi
if [ "$other" = "connection succeeded" ]; then
  succeeded "reached $VICTIM_TEAM's database from $ATTACKER_TEAM"
else
  blocked "NetworkPolicy: $other"
fi
```

It probes the team's own database (`db.team-a.svc.cluster.local`) and the victim's, and prints both results. If the team's own database does not connect, the script prints `INCONCLUSIVE` and exits with status 2, because nothing was proven. If the other connects, it reports `SUCCEEDED`; otherwise `BLOCKED (NetworkPolicy: <what was seen>)`.


## 6. Try it yourself

```bash
kubectl get networkpolicy -n team-a
```

Four policies when hardened: `default-deny`, `allow-dns`, `web-egress-to-db`, `db-ingress-from-web`.

```bash
bash attacks/03-cross-namespace-db.sh
```

Hardened: prints `team-a web -> team-a db:  connection succeeded`, `team-a web -> team-b db:  connect: [Errno 111] Connection refused`, then `BLOCKED (NetworkPolicy: ...)`. Baseline: both lines say `connection succeeded` and the verdict is `SUCCEEDED`.

```bash
kubectl -n team-a exec deploy/web -- python -c "import socket; print(socket.gethostbyname('db.team-a.svc.cluster.local'))"
```

Prints the database Service's address, proving DNS still works under default-deny.

## 7. Mistakes people make

- **Default-deny for ingress only.** Pods can still start connections anywhere, including another team's database.
- **Forgetting DNS.** Egress deny without `allow-dns` breaks every name lookup.
- **Using a plugin that ignores policies.** The objects are accepted and nothing is enforced.
- **Allowing too wide a selector.** `podSelector: {}` in an allow rule opens the port to every pod in scope.
- **Testing only that the attack fails.** A broken network also makes it fail; the script proves the team's own database is reachable first.

## 8. Check yourself

1. What does `podSelector: {}` select? *Every pod in the namespace.*
2. Why does a blocked connection here answer `Connection refused`? *k3s's policy controller rejects the connection instead of silently dropping it; a dropping plugin would give a timeout.*
3. Why is a rule needed on both the web side and the database side? *Egress from web and ingress to db are separate directions, each denied by default.*
4. What does `allow-dns` allow? *UDP and TCP port 53 to the CoreDNS pods in `kube-system`.*
5. Who enforces NetworkPolicy here? *k3s's bundled kube-router policy controller.*

## 9. Further reading

- Network Policies: https://kubernetes.io/docs/concepts/services-networking/network-policies/
- Declare a network policy: https://kubernetes.io/docs/tasks/administer-cluster/declare-network-policy/
- DNS for Services and pods: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- k3s networking: https://docs.k3s.io/networking/basic-network-options
