#!/bin/bash

set -e

###
# GLOBALS
###

BUILD_ARTEFACT_PATH="artefacts/"

###
# FUNCTIONS
###

source_version_value() {
  # Check for GITHUB_REF value
  if [ ! -z "$GITHUB_REF" ]; then
    echo " * Using GITHUB_REF to source docker tag name"
    BRANCH_NAME="${GITHUB_REF}"
    BRANCH_NAME=${BRANCH_NAME##"refs/tags/"}
    BRANCH_NAME=${BRANCH_NAME##"refs/heads/"}
  else
    echo " * Using 'git rev-parse' to source docker tag name"
    set +e
    BRANCH_NAME=$( git rev-parse --symbolic-full-name --abbrev-ref HEAD 2>/dev/null )
    echo
  fi

  # Check branch name value exists and is valid
  if [ -z "$BRANCH_NAME" ] || [ "$BRANCH_NAME" == "HEAD" ]; then
    echo "error: git project not detected, or not initalised properly"
    echo "expecting valid tag/branch name (value was either HEAD or not present)."
    exit 1
  fi

  # Apply name fix
  #BRANCH_NAME=${BRANCH_NAME##"heads/"}
  BRANCH_NAME=$( echo $BRANCH_NAME | tr '/' '-' )

  # Strip 'version-' string if present
  export DOCKER_TAG_NAME=${BRANCH_NAME##"version-"}
}

generate_build_props() {
  # Check path for generated artefacts
  if [ ! -d "$BUILD_ARTEFACT_PATH" ]; then
    echo "error: folder for build artefacts does not exist: $BUILD_ARTEFACT_PATH"
    exit 1
  fi

  # Generate build-time info
  echo "{\"version\":\"$DOCKER_TAG_NAME\"}" > $BUILD_ARTEFACT_PATH/version.json

  # Curious what our build system will produce here ...
  echo "{\"build_timestamp\":\"$( date +%Y-%m-%d:%H:%M:%S )\",
\"build_platform\":\"$( uname )\",
\"build_hostname\":\"$( uname -n )\",
\"build_kernel_version\":\"$( uname -v )\",
\"build_kernel_release\":\"$( uname -r )\",
\"build_architecture\":\"$( uname -m )\"}" > $BUILD_ARTEFACT_PATH/build.json
}

build() {
  # Prepare build artefacts
  generate_build_props

  # Build image
  echo " * Building image ..."
  docker build -t $IMAGE_NAME:latest .
  echo

  # Tag image
  echo " * Tagging image: $IMAGE_NAME:$DOCKER_TAG_NAME"
  docker tag $IMAGE_NAME:latest $IMAGE_NAME:$DOCKER_TAG_NAME
  echo
}

release() {
  echo " * Pushing image: $IMAGE_NAME:latest ..."
  docker push $IMAGE_NAME:latest
  echo

  echo " * Pushing image: $IMAGE_NAME:$DOCKER_TAG_NAME ..."
  docker push $IMAGE_NAME:$DOCKER_TAG_NAME
  echo
}



###
# MAIN
###
TASK="$1"
echo

# Source image name
if [ -z "$IMAGE_NAME" ]; then
  echo "error: env var not set: IMAGE_NAME"
  exit 1
fi

# Source tag name from git
if [ -z "$DOCKER_TAG_NAME" ]; then
  source_version_value
fi

echo " * Using tag name: $DOCKER_TAG_NAME"
echo

# Perform build or release
if [ "$TASK" == "release" ]; then
  release
else
  build
fi

echo " * Done."
echo
