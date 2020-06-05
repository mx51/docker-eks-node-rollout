#!/usr/bin/env make

include Makehelp.mk

export IMAGE_NAME ?= mx51io/eks-node-rollout
IMAGE = $(IMAGE_NAME):latest

###Build

## Compile code and create docker image
build:
	./scripts/make.sh build
PHONY: build


## Runs a simple test against the built image
test:
	docker-compose run --rm pep8 pep8 --ignore 'E501,E128' eks_node_rollout/eks_node_rollout.py
	@echo "All tests completed successfully"
PHONY: test


## Tag and push new docker image to docker hub
release:
	./scripts/make.sh release
PHONY: release


## Deletes docker image locally
clean:
	docker image rm -f $(IMAGE) 2>/dev/null
PHONY: clean


###Devtool

## Create and push new Git tag
tag:
	./scripts/vtag.sh
PHONY: tag


## Create an interactive shell on local docker instance
interact:
	docker run --rm -it --entrypoint=/bin/bash $(IMAGE)
PHONY: interact
