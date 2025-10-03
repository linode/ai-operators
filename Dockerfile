FROM python:3.13

# Install helm and kubectl
RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/

ADD /pyproject.toml .
ADD /README.md .
ADD /src /src
ADD /dependencies/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt && pip install .

ENV OPERATOR_MODULE=ml_operator
# Copy agent chart only for ai-operator
COPY agent /app/agent

CMD kopf run -m ai_operator.${OPERATOR_MODULE}
