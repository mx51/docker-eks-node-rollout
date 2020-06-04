FROM python:3.8-alpine3.12

ARG KUBECTL_VERSION=v1.18.2
ADD https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl /usr/local/bin/
RUN chmod +x /usr/local/bin/kubectl && \
    kubectl version --client

ENV PYTHONUNBUFFERED=1
RUN apk add --no-cache bash openssl-dev git libffi-dev build-base py3-pip

ENV AWSCLI_VERSION=1.18
RUN pip3 install --upgrade pip && \
    pip3 --no-cache-dir install --upgrade awscli==${AWSCLI_VERSION} && \
    mkdir -p /work
WORKDIR /work

COPY requirements.txt /eks_node_rollout/requirements.txt
RUN pip3 install -r /eks_node_rollout/requirements.txt

COPY /eks_node_rollout /eks_node_rollout
RUN ln -s /eks_node_rollout/eks_node_rollout.py /usr/bin/eks-node-rollout

CMD ["python3", "/eks_node_rollout/eks_node_rollout.py"]
