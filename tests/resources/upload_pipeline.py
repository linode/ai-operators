from kfp import dsl

@dsl.component(
    base_image='python:3.11',
    packages_to_install=['psycopg2-binary', 'kubernetes']
)
def mock_doc_ingest_component(
    url: str,
    table_name: str,
    embedding_model: str,
    embedding_api_base: str,
    embed_dim: int,
    embed_batch_size: int,
    secret_name: str,
    secret_namespace: str
) -> None:
    """Mock document ingestion component for testing - only checks database connectivity"""
    print(">>> mock_doc_ingest_component")
    print(f"Processing URL: {url}")
    print(f"Table name: {table_name}")
    print(f"Embedding model: {embedding_model}")
    print(f"Embedding API base: {embedding_api_base}")
    print(f"Embed dimension: {embed_dim}")
    print(f"Batch size: {embed_batch_size}")

    # Mock document loading
    print("Mock: Loading documents from URL...")
    print("Mock: Generated 5 test documents")

    # Mock embeddings generation
    print(f"Mock: Generating embeddings with dimension {embed_dim}...")
    print("Mock: Embeddings generated successfully")

    # Test database connectivity
    import base64
    from kubernetes import client, config

    def get_secret_credentials():
        try:
            config.load_incluster_config()
            v1 = client.CoreV1Api()
            secret = v1.read_namespaced_secret(name=secret_name, namespace=secret_namespace)

            username = base64.b64decode(secret.data['username']).decode('utf-8')
            password = base64.b64decode(secret.data['password']).decode('utf-8')
            host_raw = base64.b64decode(secret.data['host']).decode('utf-8')
            port = int(base64.b64decode(secret.data['port']).decode('utf-8'))
            dbname = base64.b64decode(secret.data['dbname']).decode('utf-8')

            host = f"{host_raw}.{secret_namespace}.svc.cluster.local"

            print(f"Database connection: {username}@{host}:{port}/{dbname}")
            return username, password, host, port, dbname
        except Exception as e:
            print(f"Error reading secret: {e}")
            raise

    username, password, host, port, database = get_secret_credentials()

    print(f"Testing connection to database: {host}:{port}/{database}")

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=username,
            password=password
        )

        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"Database connection successful! PostgreSQL version: {version[0]}")

        cursor.execute("SELECT * FROM pg_extension WHERE extname = 'vector';")
        vector_ext = cursor.fetchone()
        if vector_ext:
            print("pgvector extension is installed")
        else:
            print("pgvector extension not found")

        cursor.close()
        conn.close()

        print(f"Mock pipeline completed successfully for table: {table_name}")

    except Exception as e:
        print(f"Database connection failed: {e}")
        raise


@dsl.pipeline(name='mock-doc-ingest-pipeline')
def mock_doc_ingest_pipeline(
    url: str,
    table_name: str,
    embedding_model: str,
    embedding_api_base: str,
    embed_dim: int,
    embed_batch_size: int,
    secret_name: str,
    secret_namespace: str
) -> None:
    """Mock document ingestion pipeline for testing ML-Operator"""
    mock_doc_ingest_component(
        url=url,
        table_name=table_name,
        embedding_model=embedding_model,
        embedding_api_base=embedding_api_base,
        embed_dim=embed_dim,
        embed_batch_size=embed_batch_size,
        secret_name=secret_name,
        secret_namespace=secret_namespace
    )


def upload_test_pipeline(kfp_endpoint: str, pipeline_name: str = "mock-doc-ingest-pipeline"):
    from kfp import Client

    print(f"Connecting to Kubeflow Pipelines at: {kfp_endpoint}")
    client = Client(host=kfp_endpoint)

    try:
        existing_pipeline = client.get_pipeline(pipeline_name)
        print(f"Found existing pipeline: {existing_pipeline.pipeline_id}")

        version_upload = client.upload_pipeline_version_from_pipeline_func(
            pipeline_func=mock_doc_ingest_pipeline,
            pipeline_id=existing_pipeline.pipeline_id,
        )

        print(f"✅ Pipeline version uploaded successfully!")
        print(f"Version ID: {version_upload.pipeline_version_id}")
        print(f"Version Name: {version_upload.display_name}")

    except Exception:
        print("Pipeline doesn't exist, creating new one...")
        pipeline_upload = client.upload_pipeline_from_pipeline_func(
            pipeline_func=mock_doc_ingest_pipeline,
            pipeline_name=pipeline_name,
            description="Mock document ingestion pipeline for ML-Operator testing"
        )



if __name__ == "__main__":
    import sys

    kfp_endpoint = "http://localhost:3000"  # os.getenv("KUBEFLOW_ENDPOINT")
    if not kfp_endpoint:
        print("KUBEFLOW_ENDPOINT environment variable not set")
        print("Set it with: export KUBEFLOW_ENDPOINT=http://ml-pipeline-ui.kfp.svc.cluster.local")
        sys.exit(1)

    upload_test_pipeline(kfp_endpoint)
