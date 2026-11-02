# Kubernetes

## 1. What it is

Kubernetes is a system that runs containers (see `docker.md`) across one or more computers and keeps them running the way you described. You do not tell it "start this program"; you give it a **desired state** ("two copies of this image, each with at most 128 MiB of memory") and Kubernetes keeps working until reality matches, and keeps checking afterwards. This repository runs Kubernetes 1.35.8 (k3s).

Words used throughout:

- **Cluster**: the whole Kubernetes system. **Node**: one computer (here one container pretending to be a computer) in it. The **control plane** is the part that stores the desired state and makes decisions; the **API server** is its front door, the thing `kubectl` talks to.
- **Object**: one stored description, written in YAML (`yaml.md`): a Deployment, a Service, a ConfigMap, a Secret or a ServiceAccount. Every object has `apiVersion`, `kind`, `metadata` (name, labels) and usually a `spec` (what you want).
- **Pod**: the smallest thing that runs: one or more containers that share a network address. **Namespace**: a named folder that groups objects; this project uses `team-a` and `team-b`.
- **Label**: a key and value stuck on an object (`app: web`). A **selector** finds objects by their labels.
- **Deployment**: keeps N identical pods running and replaces them safely when you change the template. **Service**: a stable name and address that spreads traffic over the pods matching a selector. **ConfigMap** and **Secret**: key/value data given to pods (Secrets are for sensitive values). **ServiceAccount**: the identity a pod uses when it talks to the API server. **PodDisruptionBudget**: a promise about how many pods may be down during a voluntary disruption such as a node drain.
- **kubectl**: the command-line client.

## 2. Why this repository uses it

The lesson is about *isolating tenants* on one cluster. Kubernetes already has the pieces (RBAC, Pod Security, NetworkPolicy, quotas, admission policy); this project deploys two teams' identical workloads, shows six attacks succeeding against a careless setup, and shows each one stopped by exactly one control. The base manifests in this file are the workload both teams run: a Postgres database and a two-replica web service.

## 3. Where it appears

| File | Contents |
| --- | --- |
| `manifests/base/namespace.yaml` | The namespace object and the tenant label the admission policy selects. |
| `manifests/base/serviceaccounts.yaml` | One service account per workload. |
| `manifests/base/db.yaml` | The database Deployment and Service. |
| `manifests/base/web.yaml` | The web Deployment, Service and PodDisruptionBudget. |
| `manifests/controls/`, `manifests/platform/` | The five controls (see `rbac.md`, `pod-security.md`, `network-policy.md`, `quota.md`, `admission-policy.md`). |
| `attacks/*.yaml` | Manifests an attacker applies (see `attacks.md`). |
| `scripts/*.sh` | Call `kubectl` (see `bash.md`). |

## 4. How it works underneath

You send an object to the API server (`kubectl apply`). The API server checks it and stores it. **Controllers** are loops that compare stored desired state with what exists and act. The Deployment controller creates a **ReplicaSet** (a set of identical pods) and the ReplicaSet controller creates Pod objects. The **scheduler** picks a node for each pod that has none, using the pod's resource **requests** (the amount it asks to reserve). On the chosen node the **kubelet** (the node's agent) asks the container runtime to pull the image and start the containers, then keeps reporting the pod's status.

Resources: a **request** is what the scheduler reserves; a **limit** is the ceiling. Going over the memory limit makes the kernel kill the container (reason `OOMKilled`, exit code 137). Going over the CPU limit slows it down instead.

**Probes** are checks the kubelet runs. A *liveness* probe failing makes the kubelet restart the container. A *readiness* probe failing removes the pod from the Service's list of **endpoints** (the addresses that receive traffic) without restarting it. That distinction is the heart of this lesson.

Typical pod problems have named states. `ImagePullBackOff`: the image could not be fetched. `CrashLoopBackOff`: the container keeps exiting and Kubernetes waits longer between restarts. `Pending`: no node can take the pod. `Running` but not `Ready`: started, readiness failing.

A Service gets a cluster-internal address and a DNS name (`db` inside the `team-a` namespace, fully `db.team-a.svc.cluster.local`). `port` is what clients call; `targetPort` is the container port the traffic is forwarded to.

## 5. Walkthrough of this repository's use

### `manifests/base/namespace.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: tenant
  labels:
    app.kubernetes.io/part-of: tenant
    # The admission policy applies to namespaces that carry this label.
    platform.example/tenant: "true"
```

`apiVersion: v1` and `kind: Namespace` say what this is. `metadata.name: tenant` is a placeholder name; each team's overlay sets the real namespace (`team-a`, `team-b`). Two labels: `app.kubernetes.io/part-of: tenant` is a plain tag; `platform.example/tenant: "true"` marks the namespace as a tenant namespace. The comment says why: the admission policy (see `admission-policy.md`) applies to namespaces that carry it. Note there are no Pod Security labels here: the baseline is deliberately unprotected.

### `manifests/base/serviceaccounts.yaml`

```yaml
# One account per workload. The RBAC control turns off token mounting; the careless baseline leaves it on.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: web
  labels:
    app.kubernetes.io/name: web
    app.kubernetes.io/part-of: tenant
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: db
  labels:
    app.kubernetes.io/name: db
    app.kubernetes.io/part-of: tenant
```

Two ServiceAccounts separated by `---`: `web` and `db`, each with labels. The comment explains the RBAC control switches off token mounting for them, while the careless baseline leaves the default (token mounted) in place.

### `manifests/base/db.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: db
  labels:
    app: db
    app.kubernetes.io/name: db
    app.kubernetes.io/part-of: tenant
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: db
  template:
    metadata:
      labels:
        app: db
        app.kubernetes.io/name: db
        app.kubernetes.io/part-of: tenant
    spec:
      serviceAccountName: db
      enableServiceLinks: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 70
        runAsGroup: 70
```

A Deployment named `db` with labels (`app: db` is the one the selectors use). `replicas: 1`; `strategy: type: Recreate` stops the old pod before starting a new one, because two Postgres pods must not share one data directory. The selector and the pod template carry the same labels. The pod spec: `serviceAccountName: db`, `enableServiceLinks: false` (no injected Service variables), and `securityContext:` with `runAsNonRoot: true`, `runAsUser: 70`, `runAsGroup: 70` (the number of the `postgres` user in the Alpine image).

```yaml
        fsGroup: 70
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: postgres
          image: registry.example.test/platform/postgres:17-alpine
          ports:
            - name: postgres
              containerPort: 5432
          env:
            - name: POSTGRES_DB
              value: app
            - name: POSTGRES_USER
              value: app
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: password
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
```

`fsGroup: 70` makes mounted volumes group-owned by 70 so Postgres can write them; `seccompProfile: RuntimeDefault` applies the runtime's default list of allowed system calls. The container `postgres` uses `registry.example.test/platform/postgres:17-alpine`: the name is under the approved registry prefix (no registry exists; the image is imported into the node under this name, which is what the admission policy checks). The port is named `postgres`. `env` sets `POSTGRES_DB` and `POSTGRES_USER` to `app`, takes `POSTGRES_PASSWORD` from the Secret `db-credentials` key `password` (`secretKeyRef`) and sets `PGDATA` to a sub-folder of the data mount (Postgres refuses a data directory that is a mount point itself). `resources`: request 100 millicores and 128 MiB; limits 500m and 256 MiB.

```yaml
          readinessProbe:
            exec:
              command: ["pg_isready", "-U", "app", "-d", "app"]
            periodSeconds: 5
            timeoutSeconds: 3
          livenessProbe:
            exec:
              command: ["pg_isready", "-U", "app", "-d", "app"]
            initialDelaySeconds: 20
            periodSeconds: 10
            timeoutSeconds: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
            - name: run
              mountPath: /var/run/postgresql
            - name: tmp
              mountPath: /tmp
            - name: init
              mountPath: /docker-entrypoint-initdb.d
              readOnly: true
      volumes:
        # Teaching simplification: the data lives as long as the pod. A real database gets a PersistentVolumeClaim.
```

The readiness probe runs `pg_isready -U app -d app` (a Postgres tool that asks the server whether it accepts connections) every 5 seconds with a 3-second timeout; the liveness probe runs the same every 10 seconds after 20 seconds. The container `securityContext`: no privilege escalation, a read-only root file system, all capabilities dropped. `volumeMounts`: `data` at `/var/lib/postgresql/data` (the database files), `run` at `/var/run/postgresql` (the server's socket and process-id file), `tmp` at `/tmp`, and `init` at `/docker-entrypoint-initdb.d` read-only (the SQL scripts the image runs on first start). Because the root file system is read-only, every place Postgres writes needs its own volume. The comment in `volumes:` is an honest simplification: data lives only as long as the pod; a real database would use a PersistentVolumeClaim.

```yaml
        - name: data
          emptyDir:
            sizeLimit: 256Mi
        - name: run
          emptyDir:
            sizeLimit: 8Mi
        - name: tmp
          emptyDir:
            sizeLimit: 32Mi
        - name: init
          configMap:
            name: db-init
---
apiVersion: v1
kind: Service
metadata:
  name: db
  labels:
    app.kubernetes.io/name: db
    app.kubernetes.io/part-of: tenant
spec:
  selector:
    app: db
  ports:
    - name: postgres
      port: 5432
      targetPort: postgres
```

The volumes are `emptyDir` scratch folders with size limits (256 MiB, 8 MiB, 32 MiB), and `init` is a `configMap` volume from `db-init`, generated by Kustomize from the two SQL files. After `---` the Service `db`: selects `app: db` and publishes port 5432 forwarding to the named container port `postgres`.

### `manifests/base/web.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  labels:
    app: web
    app.kubernetes.io/name: web
    app.kubernetes.io/part-of: tenant
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
        app.kubernetes.io/name: web
        app.kubernetes.io/part-of: tenant
    spec:
      serviceAccountName: web
      # Kubernetes injects an environment variable for every Service in the namespace (the Service db would
      # set DB_PORT=tcp://10.43.0.1:5432, which is the name this app reads its port from). The app finds the
```

The Deployment `web`: two replicas, a `RollingUpdate` with `maxSurge: 1` and `maxUnavailable: 0` (a rollout never removes a ready pod before a new one is ready), selector and labels as for the database, `serviceAccountName: web`. The comment begins explaining why Service links are off.

```yaml
      # database through DNS, so the injection is switched off.
      enableServiceLinks: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: registry.example.test/platform/tenant-web:0.1.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: TEAM_NAME
              value: tenant
            - name: DB_HOST
              value: db
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: password
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
```

It continues: the `db` Service would set `DB_PORT=tcp://10.43.0.1:5432` and the app reads its port from `DB_PORT` as a number; the app finds the database through DNS, so `enableServiceLinks: false`. Pod `securityContext`: non-root user 10001, default seccomp. Container `web` uses `registry.example.test/platform/tenant-web:0.1.0` (approved prefix), names port 8080 `http`, and sets `TEAM_NAME=tenant` (each team's identity component replaces it), `DB_HOST=db` and `DB_PASSWORD` from the Secret. Requests: 50m CPU, 64 MiB.

```yaml
            limits:
              cpu: 250m
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 3
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 2
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 16Mi
```

Limits 250m and 128 MiB. Readiness: HTTP GET `/readyz` every 5 s (3 s timeout); liveness: HTTP GET `/healthz` every 10 s after 5 s. The same three container hardening lines as the database. `/tmp` is an `emptyDir` of 16 MiB (gunicorn's heartbeat files).

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: web
  labels:
    app.kubernetes.io/name: web
    app.kubernetes.io/part-of: tenant
spec:
  selector:
    app: web
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web
  labels:
    app.kubernetes.io/name: web
    app.kubernetes.io/part-of: tenant
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: web
```

After `---`: the Service `web` (selects `app: web`, publishes port 80 forwarding to the container port `http`). After the next `---`, a PodDisruptionBudget (`policy/v1`) named `web`: `maxUnavailable: 1` allows at most one web pod to be taken away voluntarily (for example while draining a node) and the `selector` says which pods it protects.


## 6. Try it yourself

```bash
make up
kubectl -n team-a get deploy,svc,pdb
```

Lists `deployment.apps/db` (1/1), `deployment.apps/web` (2/2), the two Services and the PodDisruptionBudget `web`.

```bash
kubectl -n team-a describe pod -l app=web | sed -n '1,40p'
```

Shows the image, the resource requests and limits, the probes and the events.

```bash
kubectl -n team-a get pods -o wide && kubectl -n team-b get pods -o wide
```

Two namespaces, each with its own `db` and two `web` pods.

```bash
kubectl -n team-a get secret db-credentials -o jsonpath='{.data.password}' | wc -c
```

Prints a number (the base64 text of the password has 44 characters); the secret exists only in the cluster.

## 7. Mistakes people make

- **No resource requests or limits.** The scheduler cannot place pods sensibly, and the quota and admission policy here depend on them.
- **Running as root with all capabilities.** The pods drop every capability and run as a number-only non-root user.
- **A Service selector that does not match the pod labels.** The Service then has no endpoints.
- **Treating `kubectl apply` success as "it works".** It only means the API server stored the object.
- **Putting the database password in a manifest.** It lives in a Secret created by a script.

## 8. Check yourself

1. What is the difference between a request and a limit? *The scheduler reserves the request; the limit is the ceiling enforced at run time.*
2. Why is the database `Recreate`? *Two Postgres pods must never run against the same data at once.*
3. Why `enableServiceLinks: false`? *Kubernetes would inject `DB_PORT=tcp://...`, overwriting the app's own `DB_PORT` setting.*
4. Why does the base namespace carry no Pod Security labels? *The baseline must be careless; the pod-security control adds them.*
5. What label does the admission policy select on? *`platform.example/tenant: "true"` on the namespace.*

## 9. Further reading

- Kubernetes documentation (v1.35): https://kubernetes.io/docs/home/
- Deployments: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Resource management: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- Debugging pods: https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/
