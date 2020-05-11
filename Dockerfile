FROM python:3.8.2-alpine3.11

ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache bash curl openssl-dev git libffi-dev build-base && \
    curl -LsO https://storage.googleapis.com/kubernetes-release/release/v1.17.5/bin/linux/amd64/kubectl && \
    mv kubectl /usr/bin/kubectl && \
    chmod +x /usr/bin/kubectl

ENV AWSCLI_VERSION=1.18
RUN pip3 install --upgrade pip && \
    pip3 --no-cache-dir install --upgrade awscli==${AWSCLI_VERSION} && \
    mkdir -p /work
WORKDIR /work

COPY requirements.txt /eks_node_rollout/requirements.txt
RUN pip3 install -r /eks_node_rollout/requirements.txt

COPY /eks_node_rollout /eks_node_rollout
RUN ln -s /eks_node_rollout//eks_node_rollout.py /usr/bin/eks-node-rollout

CMD ["python3", "/eks_node_rollout/eks_node_rollout.py"]
