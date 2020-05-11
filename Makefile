export IMAGE_NAME ?= mx51io/eks-node-rollout
IMAGE = $(IMAGE_NAME):latest

build:
	./scripts/make.sh build
PHONY: build

test:
	docker-compose run --rm pep8 pep8 --ignore 'E501,E128' eks_node_rollout/eks_node_rollout.py
PHONY: test

release:
	./scripts/make.sh release
PHONY: release

clean:
	docker image rm -f $(IMAGE) 2>/dev/null
PHONY: clean
