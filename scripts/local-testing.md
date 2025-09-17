# Local Testing

## docker-compose

Help you setup a local clickhouse and postgresql instance for testing. See `docker-compose.yaml'
for the exposed ports.

## fill_local_db.py

A script to fill the local clickhouse instance with sample data for testing. You can run it

## run.sh

A script to run the clickhouse-syphon container with the proper volume mount and environment file.

it needs:

-   .env file with the databases connection strings (psql and clickhouse)
-   config/config.yaml file with the synchronization configuration (the path can be changed with CONFIG_PATH env variable in .env file)

```yaml
tables:
    - source_uri: ""
      source_table: "campagne"
      target_uri: ""
      target_table: "campagne"
      primary_keys: ["id", "created_at"]
      sync_mode: "incremental" # options: incremental, rewind
      sync_column: "created_at"
      batch_size: 100000
      number_of_workers: 4
```
