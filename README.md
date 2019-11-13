# eks-node-rollout
eks-node-rollout is a CLI tool that assists with rolling updates to your EKS workers.

## Justification
When updating an Auto Scaling Group with a tool like Terraform, no functionality exists to automatically terminate the old instances and launch new ones. This poses a problem in automated deployments (especially CI/CD pipelines): you will deploy updates, but not receieve any feedback on whether or not those changes actually worked. Only by manually terminating instances or scaling up/down can you find out if your changes are working. Performing blue/green deployments of ASGs does not help either, as you have no way of knowing when the workers in the new ASG have succesfully launched.

## Overview of Steps
  1. add an EC2 instance to the ASG
  2. wait for the new instance to be healthy
  3. drain an instance that is outdated
  4. terminate the outdated instance

## Usage
```
Usage: eks_node_rollout.py [OPTIONS]

  Retrieve all outdated workers and perform a rolling update on them.

Options:
  --asg-name TEXT           ASG name to roll
  --dry-run / --no-dry-run  Run with read-only API calls.
  --help                    Show this message and exit.
```

The tool also accepts environment variables with the prefix `EKS_NODE_ROLLOUT_*` e.g. `EKS_NODE_ROLLOUT_ASG_NAME`.

## Docker Image
This tool is available as a Docker image: `cmdlabs/eks-node-rollout:0.1.0`

docker-compose.yml:
```yml
version: '3.7'
services:
  eks-node-rollout:
    image: cmdlabs/eks-node-rollout:0.1.0
    env_file: .env
    volumes:
      - .:/work
    working_dir: /work
```

Update your `.env` file with the following:

```
EKS_NODE_ROLLOUT_ASG_NAME
EKS_NODE_ROLLOUT_DRY_RUN
```

Then it can be called as such:

```bash
docker-compose run --rm eks-node-rollout
```
