build:
	docker build -t cmdlabs/eks-node-rollout:testing .

test:
	docker-compose run --rm eks-node-rollout tox

styleTest:
	docker-compose run --rm pep8 pep8 --ignore 'E501,E128' eks_node_rollout/eks_node_rollout.py

tag:
	git tag $(VERSION)
	git push origin $(VERSION)
