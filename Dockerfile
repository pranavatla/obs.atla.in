FROM public.ecr.aws/lambda/python:3.11

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHROMA_PATH=/tmp/atlaops_chroma_db

COPY requirements-lambda.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements-lambda.txt

COPY app1.py ${LAMBDA_TASK_ROOT}/
COPY index.html ${LAMBDA_TASK_ROOT}/
COPY docs ${LAMBDA_TASK_ROOT}/docs
COPY knowledge_base ${LAMBDA_TASK_ROOT}/knowledge_base

CMD ["app1.handler"]
