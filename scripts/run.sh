#!/bin/bash

# Run the container with proper volume mount and environment file
echo "Running ClickHouse Syphon with config.yaml..."
docker run --rm \
  --network host \
  --env-file .env \
  --memory=4g \
  --cpus=4 \
  -v "$(pwd)/config/config.yaml:/app/config/config.yaml:ro" \
  clickhouse-syphon:latest 
