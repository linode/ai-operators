FROM python:3.13
ADD /pyproject.toml .
ADD /README.md .
ADD /src /src
ADD /dependencies/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt && pip install .

ENV OPERATOR_MODULE=ml_operator
# Copy agent chart only for ai-operator
COPY agent /app/agent

CMD kopf run -m ${OPERATOR_MODULE}
