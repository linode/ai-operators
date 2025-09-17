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

## Testing

### Local Development Setup with Kind

For testing the ML-Operator locally, you can set up a Kind cluster with Kubeflow Pipelines using the following steps:

#### Prerequisites
```bash
# Install Kind (if not already installed)
# On macOS:
brew install kind

# On Linux:
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Install Helm (if not already installed)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

#### Setup Script

Create and run this setup script to create your test environment:

```bash
#!/bin/bash
set -e

echo "🚀 Setting up Kind cluster with Kubeflow Pipelines for ML-Operator testing..."

# Create Kind cluster
echo "📦 Creating Kind cluster..."
kind create cluster --name ml-operator-test

# Wait for cluster to be ready
echo "⏳ Waiting for cluster to be ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=300s

# Add Helm repositories
echo "🔧 Adding Helm repositories..."
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update

# Clone the chart repositories
echo "📥 Cloning chart repositories..."
git clone https://github.com/linode/apl-core.git /tmp/apl-core
git clone https://github.com/linode/apl-charts.git /tmp/apl-charts

# Create namespaces
kubectl create namespace kfp
kubectl create namespace cnpg-system
kubectl create namespace team-kb

# Install CloudNative-PG Operator
echo "🗃️ Installing CloudNative-PG Operator..."
helm install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system \
  --wait \
  --timeout=5m

# Install pgvector cluster
echo "🔢 Installing PostgreSQL cluster with pgvector..."
helm install pgvector-cluster /tmp/apl-charts/pgvector-cluster \
  --namespace team-kb \
  --set imageName=ghcr.io/cloudnative-pg/postgresql:17.5 \
  --set apl.networkpolicies.create=false \
  --wait \
  --timeout=10m

# Install MinIO for object storage
echo "📦 Installing MinIO for artifact storage..."
helm repo add minio https://charts.min.io/
helm repo update

helm install minio minio/minio \
  --namespace kfp \
  --set auth.rootUser=otomi-admin \
  --set auth.rootPassword=changeme \
  --set defaultBuckets="kubeflow-pipelines" \
  --set resources.requests.memory=256Mi \
  --set resources.limits.memory=512Mi \
  --set mode=standalone \
  --set replicas=1 \
  --wait \
  --timeout=10m

# Create secrets for Kubeflow Pipelines
echo "🔐 Creating secrets for Kubeflow Pipelines..."

# MySQL secret
kubectl create secret generic kfp-mysql-secret \
  --from-literal=username=root \
  --from-literal=password=changeme \
  --namespace kfp

kubectl label secret kfp-mysql-secret app=kubeflow-pipelines -n kfp

# MinIO artifact store secret
kubectl create secret generic mlpipeline-minio-artifact \
  --from-literal=accesskey=otomi-admin \
  --from-literal=secretkey=changeme \
  --namespace kfp

kubectl label secret mlpipeline-minio-artifact app=kubeflow-pipelines -n kfp

# Install Kubeflow Pipelines with MinIO configuration
echo "🔧 Installing Kubeflow Pipelines..."
helm install kubeflow-pipelines /tmp/apl-core/charts/kubeflow-pipelines \
  --namespace kfp \
  --set objectStorage.endpoint=minio.kfp.svc.cluster.local:9000 \
  --set objectStorage.bucket=kubeflow-pipelines \
  --set objectStorage.region=us-east-1 \
  --wait \
  --timeout=10m

# Wait for all pods to be ready
echo "⏳ Waiting for all services to be ready..."
kubectl wait --for=condition=Ready pods --all -n kfp --timeout=600s
kubectl wait --for=condition=Ready pods --all -n cnpg-system --timeout=300s
kubectl wait --for=condition=Ready pods --all -n team-kb --timeout=600s

# Build and load the ML-Operator image
echo "🔨 Building ML-Operator image..."
uv run poe export-deps  # Generate requirements.txt
docker build -t ml-operator:local .

echo "📦 Loading image into Kind cluster..."
kind load docker-image ml-operator:local --name ml-operator-test

# Deploy the ML-Operator using Helm chart
echo "🚀 Deploying ML-Operator..."
helm install ml-operator ./chart \
  --set image.repository=ml-operator \
  --set image.tag=local \
  --set image.pullPolicy=Never \
  --set env.KUBEFLOW_ENDPOINT=http://ml-pipeline-ui.kfp.svc.cluster.local \
  --wait \
  --timeout=5m
```

#### Quick Start

1. Save the above script as `setup-test-env.sh`
2. Make it executable: `chmod +x setup-test-env.sh`
3. Run it: `./setup-test-env.sh`

#### Testing the Operator

Once the environment is set up, the operator is already running in the cluster. You can test it:

```bash
# Check operator status
kubectl get pods -l app.kubernetes.io/name=akamai-ml-operator

# Watch operator logs
kubectl logs -l app.kubernetes.io/name=akamai-ml-operator -f

# Create a test knowledge base resource
kubectl apply -f tests/resources/test-knowledge-base.yaml

# Check the knowledge base resource
kubectl get akamaiknowledgebases

# Check database cluster status
kubectl get clusters -n team-kb
kubectl get pods -n team-kb

# Check pipeline status in Kubeflow (optional UI access)
kubectl port-forward -n kfp service/ml-pipeline-ui 8888:80
# Then visit http://localhost:8888

# Connect to PostgreSQL database (for debugging)
kubectl exec -it -n team-kb pgvector-cluster-1 -- psql -U postgres
# Then you can run: \l to list databases, \c <dbname> to connect, \dt to list tables
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

