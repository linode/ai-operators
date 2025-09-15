from ml_operator.resource import AkamaiKnowledgeBase, KBData, KBIndexing

# Global test objects, reused in tests
SAMPLE_KB_DICT = {
    "data": {"url": "https://example.com/kb-data"},
    "indexing": {
        "embeddingModelEndpoint": "model.model-namespace.svc.cluster.local",
        "embeddingModelName": "e5-mistral-7b",
        "embeddingDimension": 4096,
        "embeddingPipeline": "pipeline",
        "dbHostReadWrite": "pgvector-rw.team-demo.svc.cluster.local",
        "dbHostRead": "pgvector-r.team-demo.svc.cluster.local",
        "dbName": "app",
        "dbPort": 5432,
        "dbSecretName": "pgvector-app",
    },
}

SAMPLE_KB_OBJECT = AkamaiKnowledgeBase(
    data=KBData(url="https://example.com/kb-data"),
    indexing=KBIndexing(
        embedding_model_endpoint="model.model-namespace.svc.cluster.local",
        embedding_model_name="e5-mistral-7b",
        embedding_dimension=4096,
        embedding_pipeline="pipeline",
        db_host_read_write="pgvector-rw.team-demo.svc.cluster.local",
        db_host_read="pgvector-r.team-demo.svc.cluster.local",
        db_name="app",
        db_port=5432,
        db_secret_name="pgvector-app",
    ),
)
