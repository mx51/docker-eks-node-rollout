FROM python:3.7.5-alpine3.10
ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache curl openssl-dev libffi-dev build-base && \
    curl -LsO https://storage.googleapis.com/kubernetes-release/release/v1.14.0/bin/linux/amd64/kubectl && \
    mv kubectl /usr/bin/kubectl && \
    chmod +x /usr/bin/kubectl
COPY requirements.txt /eks_node_rollout/requirements.txt
RUN pip3 install -r /eks_node_rollout/requirements.txt
COPY /eks_node_rollout /eks_node_rollout
RUN ln -s /eks_node_rollout//eks_node_rollout.py /usr/bin/eks-node-rollout
CMD ["python3", "/eks_node_rollout/eks_node_rollout.py"]
