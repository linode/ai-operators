FROM python:3.13

ARG HELM_VERSION=3.19.0
ARG KUBECTL_VERSION=1.34.1
ARG TARGETARCH=amd64

# Install helm and kubectl (required for agent-operator)
RUN curl -fsSL https://get.helm.sh/helm-v${HELM_VERSION}-linux-${TARGETARCH}.tar.gz | tar xz && \
    mv linux-${TARGETARCH}/helm /usr/local/bin/helm && \
    rm -rf linux-${TARGETARCH} && \
    curl -fsSLO "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${TARGETARCH}/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

ADD /pyproject.toml .
ADD /README.md .
ADD /src /src
ADD /dependencies/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt && pip install .

ENV OPERATOR_MODULE=${OPERATOR_MODULE}
# Copy agent chart only for ai-operator
COPY agent /app/agent

# Default command - can be overridden in deployment
CMD ["kopf", "run", "-m", "ai_operators.kb_operator.main"]
