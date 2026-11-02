# kubeconform

## 1. What it is

kubeconform checks that Kubernetes YAML is **valid against the official schema** for a given Kubernetes version, offline and fast. A schema is a machine-readable description of every object: which fields exist, which are required and what types they have. A misspelled field (`replica:` instead of `replicas:`) or a string where a number belongs is reported with the object and path.

## 2. Why this repository uses it

`kubectl apply` would report these mistakes too, but only against a running cluster. kubeconform lets `make lint` and CI catch them without one, for both overlays, against the schemas of the exact Kubernetes line the lesson targets.

## 3. Where it appears

| File | Role |
| --- | --- |
| `scripts/tools.sh` | Downloads kubeconform v0.8.0 into `.bin` and verifies its checksum. |
| `Makefile` | Target `conform`; `lint` depends on it. |
| `.kubeconform-cache/` | Downloaded schemas (ignored by git). |

## 4. How it works underneath

The Makefile pipes the output of `kubectl kustomize <overlay>` into `kubeconform`. For each object it works out the schema file from `apiVersion` and `kind`, downloads it the first time (then reads it from the cache folder given by `-cache`), and validates. `-strict` additionally rejects fields that the schema does not know. `-kubernetes-version 1.35.0` selects the schema set. `-summary` prints a final line such as `Summary: 9 resources found parsing stdin - Valid: 9, Invalid: 0, Errors: 0, Skipped: 0`.

## 5. Walkthrough of this repository's use



## 6. Try it yourself

```bash
make conform
```

Prints one `kubeconform manifests/overlays/<name>` line and one summary per overlay, with `Invalid: 0`.

```bash
kubectl kustomize --load-restrictor=LoadRestrictionsNone manifests/overlays/hardened | sed 's/replicas: 2/replicas: "two"/' | .bin/kubeconform -strict -summary -kubernetes-version 1.35.0
```

Reports the invalid type for `spec.replicas`.

## 7. Mistakes people make

- **Validating against the wrong version.** Fields appear and disappear between releases.
- **Not using `-strict`.** Misspelled fields pass silently otherwise.
- **Expecting it to check behaviour.** It validates shape, not whether the app will run.

## 8. Check yourself

1. What does the schema describe? *Which fields an object may have and their types.*
2. What does `-strict` add? *Rejection of unknown fields.*
3. Why is a cache folder used? *Schemas are downloaded once.*
4. Does it need a cluster? *No.*
5. Where does the YAML come from? *A pipe from `kubectl kustomize`.*

## 9. Further reading

- kubeconform repository: https://github.com/yannh/kubeconform
- Kubernetes API reference: https://kubernetes.io/docs/reference/kubernetes-api/
