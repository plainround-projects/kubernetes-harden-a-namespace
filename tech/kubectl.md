# kubectl

## 1. What it is

`kubectl` is the command-line client for Kubernetes (`kubernetes.md`). Every command is a request to the cluster's API server; the answer is printed. It reads the address and credentials from a **kubeconfig** file (the `KUBECONFIG` environment variable names it).

## 2. Why this repository uses it

The lesson is about *who may do what* in a cluster, and every attack and every defence is observed through `kubectl`. The scripts and tests call it constantly, always with `KUBECONFIG` pointing at the project's own file so the user's other clusters are never touched.

## 3. Where it appears

Every script in `scripts/` and `attacks/`, the `Makefile` (`conform`), the CI diagnostics step, and `tests/e2e/kube.py`, `tests/policy/conftest.py`.

## 4. How it works underneath

The commands used here, in plain words:

- `kubectl get <kind>` lists objects; `-o wide` adds columns, `-o json` prints the full object, `-o jsonpath=...` prints one field, `-o custom-columns=...` builds a table, `-l key=value` filters by label, `-n name` picks the namespace, `-A` means all namespaces.
- `kubectl describe <kind> <name>` prints one object in detail, ending with its **events**, the cluster's short log of what happened to it.
- `kubectl logs <pod>` prints a container's output; `--previous` prints the output of the instance that crashed.
- `kubectl apply -f file` or `-k folder` creates or updates objects from files; `-k` first runs Kustomize.
- `kubectl kustomize <folder>` only renders, without sending.
- `kubectl rollout status deployment/web` waits until an update finishes; `rollout undo` goes back to the previous version.
- `kubectl wait --for=condition=Ready nodes --all` waits for a condition.
- `kubectl port-forward svc/web 18080:80` opens a tunnel from a local port to a Service.
- `kubectl top pods` shows actual CPU and memory (needs the metrics server).
- `kubectl create secret generic` creates a Secret from literal values.
- `kubectl --as=alice --as-group=team-a-humans ...` runs any command as another identity (impersonation); `kubectl auth can-i <verb> <resource>` asks whether an action would be allowed.
- `kubectl exec deploy/web -- cmd` runs a command inside a pod; `-i` keeps standard input open.
- `kubectl label namespace x key=value` adds a label; `key-` removes it.
- `kubectl delete ... -l key` deletes objects by label.
- `kubectl apply --server-side --force-conflicts` lets the API server merge the change and take over fields another manager owns.

## 5. Walkthrough of this repository's use

The scripts that use these commands are explained line by line in `bash.md`, and the tests in `tests-e2e.md`.



## 6. Try it yourself

```bash
export KUBECONFIG=$PWD/.kube/config
kubectl get nodes
kubectl -n counter get pods -o wide
kubectl -n team-a get events --sort-by=.lastTimestamp | tail
kubectl -n team-a logs deploy/web --tail 5
```

A node `Ready`; three pods in team A (`db` and two `web`); recent events (each line has a Reason such as `Scheduled`, `Pulled`, `Started`); the last five log lines as JSON.

## 7. Mistakes people make

- **Forgetting `-n team-a`.** The pods are not in the default namespace.
- **Talking to the wrong cluster.** Check `kubectl config current-context` or set `KUBECONFIG` explicitly.
- **Using `describe` without reading the events at the bottom.** That is where the cause usually is.
- **Reading logs of the new container when the old one crashed.** Use `--previous`.

## 8. Check yourself

1. Where does kubectl find the cluster? *In the file named by `KUBECONFIG`.*
2. What is `describe` best for? *Reading events about one object.*
3. What does `logs --previous` show? *The last crashed instance's output.*
4. What does `apply -k` do beyond `apply -f`? *It renders a Kustomize folder first.*
5. How do you filter by label? *`-l app=web`.*

## 9. Further reading

- kubectl reference: https://kubernetes.io/docs/reference/kubectl/
- Cheat sheet: https://kubernetes.io/docs/reference/kubectl/quick-reference/
- JSONPath support: https://kubernetes.io/docs/reference/kubectl/jsonpath/
- Debugging running pods: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
