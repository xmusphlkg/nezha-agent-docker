name: Build and Push Docker Image

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:
    inputs:
      force_build:
        description: 'Force rebuild even if no new version is found (true/false)'
        required: false
        default: 'false'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - name: Check out the repo
      uses: actions/checkout@v2

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v1

    - name: Log in to DockerHub
      uses: docker/login-action@v1
      with:
        username: ${{ secrets.DOCKER_USERNAME }}
        password: ${{ secrets.DOCKER_PASSWORD }}

    - name: Check for Nezha Agent updates
      id: check
      run: |
        LATEST_VERSION=$(curl -s https://api.github.com/repos/nezhahq/agent/releases/latest | grep tag_name | cut -d '"' -f 4)
        echo "LATEST_VERSION=$LATEST_VERSION" >> $GITHUB_ENV
        echo "version=$LATEST_VERSION" >> $GITHUB_ENV_FILE

    - name: Build and push
      if: env.LATEST_VERSION != env.CURRENT_VERSION || github.event.inputs.force_build == 'true'
      uses: docker/build-push-action@v2
      with:
        context: .
        file: ./Dockerfile
        push: true
        tags: ${{ secrets.DOCKER_USERNAME }}/nezha-agent:${{ env.LATEST_VERSION }}
        build-args: VERSION=${{ env.LATEST_VERSION }}

    - name: Update current version
      if: env.LATEST_VERSION != env.CURRENT_VERSION || github.event.inputs.force_build == 'true'
      run: echo "CURRENT_VERSION=${{ env.LATEST_VERSION }}" >> $GITHUB_ENV
