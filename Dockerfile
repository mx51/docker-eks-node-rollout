FROM python:3-alpine
ENV PYTHONUNBUFFERED=1
WORKDIR /work
RUN apk add --no-cache openssl-dev libffi-dev build-base
COPY requirements.txt /app/requirements.txt
RUN pip3 install -r requirements.txt
COPY /eks_node_rollout /eks_node_rollout
CMD ["python3", "/eks_node_rollout/eks_node_rollout.py"]
