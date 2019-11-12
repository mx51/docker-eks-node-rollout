# docker-eks-node-rollout
This is a CLI tool that assists with rolling out changes to your EKS workers.

  1. add an EC2 instance to the ASG
  2. drain an instance that is outdated 
  3. terminate the outdated instance
  4. wait for the new instance to be healthy

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
This tool is available as a Docker image: `aarongorka/eks-node-rollout:latest`

docker-compose.yml:
```yml
version: '3.7'
services:
  sonar-poller:
    image: aarongorka/eks-node-rollout:latest
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
