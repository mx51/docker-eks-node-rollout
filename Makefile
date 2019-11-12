build:
	docker build -t cmdlabs/eks-node-rollout:testing .

test:
	docker-compose run --rm eks-node-rollout tox

tag:
	git tag $(VERSION)
	git push origin $(VERSION)
