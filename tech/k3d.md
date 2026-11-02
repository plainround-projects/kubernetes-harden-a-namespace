# k3d and k3s (the local cluster)

## 1. What it is

**k3s** is a small, complete, certified Kubernetes (`kubernetes.md`) packaged as a single program. **k3d** is a command-line tool that starts k3s inside Docker containers: a "node" becomes one Docker container. The result is a real Kubernetes API on your laptop that you can create in a couple of minutes and throw away afterwards. This repository uses k3d 5.9.0 with the image `rancher/k3s:v1.35.8-k3s1`, which is Kubernetes 1.35.8.

## 2. Why this repository uses it

The lesson needs a cluster that really *enforces* NetworkPolicy, Pod Security and admission policies, because the proof is an attack that is stopped. k3s does: it bundles a network-policy controller (kube-router's) next to its flannel network, so a NetworkPolicy object is not just accepted but enforced. (A cluster whose network plugin ignores the objects would accept them and enforce nothing; the comment in the config file shows the flag that reproduces that mistake.) k3s also starts the control plane in about a minute even on a busy machine.

## 3. Where it appears

| File | Role |
| --- | --- |
| `cluster/k3d-config.yaml` | The cluster's description. |
| `scripts/cluster-start.sh` | Creates the cluster (under a machine-wide lock). |
| `scripts/cluster-down.sh` | Deletes it. |
| `scripts/tools.sh` | Downloads the pinned `k3d` binary. |
| `scripts/build-images.sh` | Imports the three images into the cluster. |

## 4. How it works underneath

`k3d cluster create --config file` reads the YAML, asks Docker to start a container from the k3s image (a **server**, which runs the control plane and, with zero **agents**, also runs the pods), waits until the Kubernetes API answers and writes a kubeconfig (the file with the address and credentials `kubectl` needs). Because the "node" is a Docker container, an image built on your machine is not automatically visible to it; `k3d image import` copies the image into the node's container runtime.

k3s bundles extras (Traefik for ingress, a service load balancer, local storage, a Helm controller, a metrics server and a network-policy controller; the last one stays on here because the lesson needs it). Each runs as pods and costs memory; the config switches off the ones this lesson does not use.

The **kubelet** (see `kubernetes.md`) has built-in protections: when a disk is 85 percent full it taints the node `disk-pressure` so pods stop scheduling, and it deletes unused images. The settings `eviction-hard` and `image-gc-*thresholds` relax those so a busy laptop disk does not make the demo hang. Real nodes should keep the defaults.

## 5. Walkthrough of this repository's use

### `cluster/k3d-config.yaml`

```yaml
# One node: a k3s server that also runs the pods, in one Docker container. k3s is a certified Kubernetes
# distribution in a single binary (Kubernetes 1.35.8, k3s v1.35.8-k3s1).
#
# Network policy: k3s ships an embedded network policy controller (kube-router's) next to its flannel
# network, so NetworkPolicy objects are enforced. That is the property the lesson needs from the cluster.
# kind's default network plugin (kindnet), and flannel without that controller, accept NetworkPolicy objects
# and enforce nothing; to see the lesson's first common mistake, add `--disable-network-policy` below.
#
# Traefik, the service load balancer, metrics-server, local storage and the Helm controller are switched off:
# nothing here needs them, and each is one less thing writing to the cluster's database on a busy machine. There is no k3d
# load balancer either, so the API server's port is published on the node itself (a random free port).
# Disk thresholds: the kubelet normally refuses to schedule pods (a disk-pressure taint) and deletes unused
# images once the disk is 85% full. Docker Desktop's disk is shared with every image and volume on the
# machine and is often fuller than that, so a local cluster that obeyed the defaults would sit Pending, or lose the
# images just imported into it. Both limits are relaxed here; a real node keeps the defaults.
apiVersion: k3d.io/v1alpha5
kind: Simple
metadata:
  name: harden
servers: 1
agents: 0
image: rancher/k3s:v1.35.8-k3s1
options:
  k3d:
    wait: true
    timeout: 15m0s
    disableLoadbalancer: true
  k3s:
```

The comment block explains the choices: one node (a k3s server that also runs the pods, in one Docker container); the network-policy paragraph (k3s's embedded controller enforces NetworkPolicy, unlike plugins that accept the objects and enforce nothing; `--disable-network-policy` would reproduce the lesson's first common mistake); the bundled extras switched off; no k3d load balancer, so the API port is published on the node; and the disk thresholds (the kubelet normally taints the node `disk-pressure` and deletes unused images at 85% disk use, which on a shared Docker disk would leave pods Pending or lose the imported images, so both limits are relaxed; a real node keeps the defaults). The settings begin at `apiVersion: k3d.io/v1alpha5` and `kind: Simple`. `metadata.name: harden` names the cluster, and so the node container `k3d-harden-server-0`. `servers: 1`, `agents: 0`: one server and no separate workers. `image: rancher/k3s:v1.35.8-k3s1` is the exact k3s release. Under `options.k3d`: `wait: true` (wait until ready), `timeout: 15m0s`, `disableLoadbalancer: true`. Under `options.k3s.extraArgs` each item has an `arg` (a k3s flag) and `nodeFilters` (which nodes get it). The first, `--kubelet-arg=eviction-hard=nodefs.available<1%,imagefs.available<1%,nodefs.inodesFree<1%`, makes the kubelet treat the disk as under pressure only when less than one percent is free. The next item begins: `--kubelet-arg=image-gc-high-threshold=100`.

```yaml
    extraArgs:
      - arg: --kubelet-arg=eviction-hard=nodefs.available<1%,imagefs.available<1%,nodefs.inodesFree<1%
        nodeFilters:
          - all
      - arg: --kubelet-arg=image-gc-high-threshold=100
        nodeFilters:
          - all
      - arg: --kubelet-arg=image-gc-low-threshold=99
        nodeFilters:
          - all
      - arg: --disable=traefik
        nodeFilters:
          - server:*
      - arg: --disable=servicelb
        nodeFilters:
          - server:*
      - arg: --disable=metrics-server
        nodeFilters:
          - server:*
      - arg: --disable=local-storage
        nodeFilters:
          - server:*
      - arg: --disable-helm-controller
        nodeFilters:
          - server:*
```

The `all` filter of that item, then `--kubelet-arg=image-gc-low-threshold=99` (with the high threshold of 100 this stops the kubelet deleting unused images, so the imported images stay). The rest apply to the server node only (`server:*`): `--disable=traefik`, `--disable=servicelb`, `--disable=metrics-server`, `--disable=local-storage` and `--disable-helm-controller`.


## 6. Try it yourself

```bash
make tools && .bin/k3d version
```

Prints `k3d version v5.9.0` and `k3s version v1.35.x`.

```bash
make up
kubectl get nodes -o wide
```

One node named `k3d-harden-server-0`, status `Ready`, version `v1.35.8+k3s1`.

```bash
docker ps --filter name=k3d-harden
```

Shows the container that is the node.

```bash
make down && docker ps --filter name=k3d-harden
```

The cluster and its container are gone.

## 7. Mistakes people make

- **Forgetting to import the image.** The pod then sits in `ErrImagePull` because the node cannot see your local Docker images.
- **Running two cluster creations at once.** The host runs out of CPU and both time out; `scripts/cluster-start.sh` takes a lock so only one runs at a time.
- **Relaxing disk protections on a real node.** Only acceptable on a throwaway laptop cluster.
- **Using the wrong kubeconfig.** This project writes `.kube/config` and exports `KUBECONFIG`; a plain `kubectl` in another shell talks to some other cluster.

## 8. Check yourself

1. What is a k3d "node"? *A Docker container running k3s.*
2. Why are `traefik`, `servicelb`, `metrics-server`, `local-storage` and the Helm controller disabled? *Nothing in the lesson needs them and each costs memory and writes to the cluster's database.*
3. Why must the images be imported? *The node has its own image store, separate from the host's Docker.*
4. What makes NetworkPolicy work on this cluster? *k3s's embedded network policy controller.*
5. What would `--disable-network-policy` show? *NetworkPolicy objects accepted and nothing enforced: attack 3 would succeed even when hardened.*

## 9. Further reading

- k3d documentation: https://k3d.io/stable/
- k3d config file (v1alpha5): https://k3d.io/stable/usage/configfile/
- k3s documentation: https://docs.k3s.io/
- k3s server options: https://docs.k3s.io/cli/server
- kubelet eviction: https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/
