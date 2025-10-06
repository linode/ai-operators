# Akamai ML-Operator

## Prerequisites

Install `uv` to set up the project. `uv venv` sets up the virtual environment.
All dependencies should be exclusively managed using this tool. Also
`pre-commit install` should be run initially, for ensuring consistent
formatting.

## Scripts

A few utility commands are set up using `poe`. Outside the virtual environment,
`poe` can be invoked using `uv run poe <utility>`.

* `test`: runs all tests
* `lint`: checks on formatting
* `format`: fixes formatting
* `fix`: fixes formatting and other rules, e.g. import sorting
* `export-deps`: regenerates the requirements.txt in `dependencies/`
* `dev`: Run the operator locally

## Structure

```
ml-operator
├── chart         # Helm chart for deployment
├── dependencies  # Generated requirements.txt for image generation
├── src           # ml-operator package
└── tests         # pytest modules and resources
```

## Testing agent-operator

The agent-operator can be deployed using two different providers:
- **Linode/K8s Provider** (`PROVIDER=linode`): Uses `kubectl` to deploy agents directly
- **APL Provider** (`PROVIDER=apl`): Uses ArgoCD to deploy agents

### Testing with Linode/K8s Provider

**1. Create Kind cluster**
```bash
kind create cluster --name agent-operator-test
kubectl wait --for=condition=Ready nodes --all --timeout=300s
```

**2. Create test namespace**
```bash
kubectl create namespace team-demo
```

**3. Build and deploy agent-operator**
```bash
# Generate requirements.txt
uv run poe export-deps

# Build Docker image with agent chart included
docker build \
  --build-arg OPERATOR_MODULE=agent_operator \
  -t agent-operator:local .

# Load image into Kind cluster
kind load docker-image agent-operator:local --name agent-operator-test

# Deploy the agent-operator with Linode provider
helm install -n team-demo agent-operator ./chart \
  --set operator.name=agent-operator \
  --set image.repository=agent-operator \
  --set image.tag=local \
  --set image.pullPolicy=Never \
  --set env.PROVIDER=linode \
  --wait \
  --timeout=5m
```

**4. Create required secrets**
```bash
# Create pgvector database secret (required for knowledge base tools)
kubectl create secret generic pgvector-app -n team-demo \
  --from-literal=username=app \
  --from-literal=password=your-password-here \
  --from-literal=host=pgvector-cluster-rw.team-demo.svc.cluster.local \
  --from-literal=port=5432
```

**5. Test the operator**
```bash
# Create a test foundation model service (required for agent deployment)
kubectl create service clusterip llama-service --tcp=8000:8000 -n team-demo
kubectl label service llama-service modelType=foundation modelName=llama -n team-demo

# Create a test agent resource
kubectl apply -f tests/resources/kb-crd.yaml
kubectl apply -f tests/resources/agent-cr.yaml

# Check the agent resource
kubectl get akamaiagents -n team-demo

# Watch operator logs
kubectl logs -l app.kubernetes.io/name=agent-operator -n team-demo -f
```

### Testing with APL/ArgoCD Provider

**1. Create Kind cluster**
```bash
kind create cluster --name agent-operator-test
kubectl wait --for=condition=Ready nodes --all --timeout=300s
```

**2. Install ArgoCD**
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl wait --for=condition=Ready pods --all -n argocd --timeout=600s
```

**3. Create test namespace**
```bash
kubectl create namespace team-demo
```

**4. Build and deploy agent-operator**
```bash
# Generate requirements.txt
uv run poe export-deps

# Build Docker image with agent chart included
docker build \
  --build-arg OPERATOR_MODULE=agent_operator \
  --no-cache \
  -t agent-operator:local .

# Load image into Kind cluster
kind load docker-image agent-operator:local --name agent-operator-test
````

```bash

# Deploy the agent-operator with APL provider
helm install -n team-demo agent-operator ./chart \
  --set operator.name=agent-operator \
  --set image.repository=agent-operator \
  --set image.tag=local \
  --set image.pullPolicy=Never \
  --set env.PROVIDER=apl \
  --set env.AGENT_CHART_REPO_URL=https://github.com/linode/ai-operators.git \
  --set env.AGENT_CHART_REPO_REVISION=main \
  --set env.AGENT_CHART_PATH=agent \
  --wait \
  --timeout=5m
```

**5. Create required secrets**
```bash
# Create pgvector database secret (required for knowledge base tools)
kubectl create secret generic pgvector-app -n team-demo \
  --from-literal=username=app \
  --from-literal=password=your-password-here \
  --from-literal=host=pgvector-cluster-rw.team-demo.svc.cluster.local \
  --from-literal=port=5432
```

**6. Test the operator**
```bash
# Create a test foundation model service (required for agent deployment)
kubectl create service clusterip llama-service --tcp=8000:8000 -n team-demo
kubectl label service llama-service modelType=foundation modelName=llama -n team-demo

# Create a test agent resource
kubectl apply -f tests/resources/kb-crd.yaml
kubectl apply -f tests/resources/agent-cr.yaml

# Check the agent resource
kubectl get akamaiagents -n team-demo

# Check ArgoCD application created
kubectl get applications -n argocd

# Watch operator logs
kubectl logs -l app.kubernetes.io/name=agent-operator -n team-demo -f
```

**7. Cleanup**
```bash
# Delete the Kind cluster
kind delete cluster --name agent-operator-test
```



## Testing ml-operator

### Local Development Setup with Kind

For testing the ML-Operator locally, you can set up a Kind cluster with Kubeflow Pipelines using the following steps:

#### Prerequisites
```bash
# Install Kind (if not already installed)
brew install kind

# Install uv (if not already installed)
brew install uv

# Install Helm (if not already installed)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

#### Step-by-Step Setup

Follow these steps to create your test environment:

**1. Create Kind cluster**
```bash
kind create cluster --name ml-operator-test
kubectl wait --for=condition=Ready nodes --all --timeout=300s
```

**2. Add Helm repositories**
```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo add minio https://charts.min.io/
helm repo update
```

**3. Clone chart repositories**
```bash
rm -rf /tmp/apl-core /tmp/apl-charts
git clone https://github.com/linode/apl-core.git /tmp/apl-core
git clone https://github.com/linode/apl-charts.git /tmp/apl-charts
```

**4. Create namespaces**
```bash
kubectl create namespace kfp
kubectl create namespace cnpg-system
kubectl create namespace team-kb
```

**5. Install CloudNative-PG Operator**
```bash
helm install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system \
  --wait \
  --timeout=5m
```

**6. Install PostgreSQL cluster with pgvector**
```bash
helm install pgvector-cluster /tmp/apl-charts/pgvector-cluster \
  --namespace team-kb \
  --set imageName=ghcr.io/cloudnative-pg/postgresql:17.5 \
  --set apl.networkpolicies.create=false \
  --wait \
  --timeout=10m
```

**7. Install MinIO for artifact storage**
```bash
helm install minio minio/minio \
  --namespace kfp \
  --set rootUser=otomi-admin \
  --set rootPassword=supersecretkey \
  --set defaultBuckets="kubeflow-pipelines" \
  --set resources.requests.memory=256Mi \
  --set resources.limits.memory=512Mi \
  --set mode=standalone \
  --set replicas=1 \
  --wait \
  --timeout=10m
```

**8. Create Kubeflow Pipelines secrets**
```bash
kubectl create secret generic mlpipeline-minio-artifact \
  --from-literal=accesskey=otomi-admin \
  --from-literal=secretkey=supersecretkey \
  --namespace kfp

kubectl label secret mlpipeline-minio-artifact app=kubeflow-pipelines -n kfp
```

**9. Install Kubeflow Pipelines**
```bash
helm install kubeflow-pipelines /tmp/apl-core/charts/kubeflow-pipelines \
  --namespace kfp \
  --set objectStorage.endpoint=minio.kfp.svc.cluster.local \
  --set objectStorage.bucket=kubeflow-pipelines \
  --set objectStorage.region=us-east-1 \
  --set objectStorage.port=9000 \
  --set objectStorage.secure=false \
  --set objectStorage.type=minio \
  --wait \
  --timeout=10m
```

**10. Wait for all services to be ready**
```bash
kubectl wait --for=condition=Ready pods --all -n kfp --timeout=600s
kubectl wait --for=condition=Ready pods --all -n cnpg-system --timeout=300s
kubectl wait --for=condition=Ready pods --all -n team-kb --timeout=600s
```

**11. Upload test pipeline to Kubeflow**
```bash
# Port-forward to access Kubeflow Pipelines API
kubectl port-forward -n kfp service/ml-pipeline 3000:80 &

# Upload the test pipeline
python tests/resources/upload-pipeline.py
```

**12. Set up test pipeline source config**

First copy .secrets.template to .secrets, and follow the instructions to create and set a token
```sh
kubectl create ns ml-operator
kubectl create configmap pipelines -n ml-operator --from-literal=default='{"url": "https://api.github.com/repos/linode/ml-pipelines/actions/artifacts/4055865221/zip", "authType": "bearer", "authSecretName": "pipelines", "authSecretKey": "gh-token"}'  <!--- pragma: allowlist secret --->
kubectl create secret pipelines -n ml-operator --from-env-file .secrets
```

**13. Build and deploy ML-Operator**
```bash
# Generate requirements.txt
uv run poe export-deps

# Build Docker image
docker build -t ml-operator:local .

# Load image into Kind cluster
kind load docker-image ml-operator:local --name ml-operator-test

# Deploy the ML-Operator
helm install -n ml-operator ml-operator ./chart \
  --set image.repository=ml-operator \
  --set image.tag=local \
  --set image.pullPolicy=Never \
  --set env.KUBEFLOW_ENDPOINT=http://ml-pipeline-ui.kfp.svc.cluster.local \
  --wait \
  --timeout=5m
```

#### Testing the Operator

Once the environment is set up, the operator is already running in the cluster. You can test it:

```bash
# Create a test knowledge base resource
kubectl apply -f tests/resources/test-knowledge-base.yaml
```

```bash
# Check the knowledge base resource
kubectl get akamaiknowledgebases

# Watch operator logs
kubectl logs -l app.kubernetes.io/name=akamai-ml-operator -f
```

#### Development Workflow

For iterative development:

```bash
# Make code changes, then rebuild and redeploy
uv run poe export-deps
docker build -t ml-operator:local .
kind load docker-image ml-operator:local --name ml-operator-test

# Restart the operator deployment
kubectl rollout restart deployment ml-operator

# Watch the updated logs
kubectl logs -l app.kubernetes.io/name=akamai-ml-operator -f
```

#### Cleanup

```bash
# Delete the Kind cluster
kind delete cluster --name ml-operator-test
```
