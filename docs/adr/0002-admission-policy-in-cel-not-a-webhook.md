# 0002. The admission policy is a ValidatingAdmissionPolicy in CEL, not a webhook

Date: 2026-10-27. Status: accepted.

## Context

The lesson asks for an admission policy in CEL, and its sample output shows "admission webhook denied the request". Two designs can produce that behavior.

## Decision

A `ValidatingAdmissionPolicy` with a `ValidatingAdmissionPolicyBinding`, built in to the API server since Kubernetes 1.30. It runs inside the API server (no service to deploy, no certificate to rotate, no network hop), `failurePolicy: Fail` makes it fail closed, and `validationActions: [Deny]` rejects. The binding selects the namespaces that carry the label `platform.example/tenant: "true"`, so a new team namespace is covered by labeling it.

The rejection text is therefore "ValidatingAdmissionPolicy 'approved-registry-and-limits' with binding 'approved-registry-and-limits' denied request: image must come from registry.example.test/platform/, got: ...", not the webhook wording in the lesson. The messages come from `messageExpression`, which names the offending image or container.

The second rule requires a **memory** limit and not a CPU limit. A memory limit is what stops a container from taking its node's memory; CPU limits throttle and are debated, so the policy does not force them.

## Alternatives considered

- **A validating webhook** (a small server, or Kyverno or Gatekeeper). More expressive and what many clusters run, but it needs a deployment, TLS and an availability story, and none of it is the lesson.
- **Parameterizing the registry through `paramKind`.** The prefix is one string used in two messages and an expression; a parameter object would be one more resource to deploy and keep in step. The prefix is stated once in `policy.yaml` and checked by a policy test against the workloads.

## Consequences

The policy does not look at Deployments, only at the Pods they create, so a bad Deployment is accepted and its ReplicaSet fails to create pods (the failure is in the ReplicaSet's events). Init and ephemeral containers: init containers are checked, ephemeral containers are not.
