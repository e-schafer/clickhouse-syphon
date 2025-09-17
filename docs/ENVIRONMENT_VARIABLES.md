# Environment Variable URI Configuration

## Overview

ClickHouse Syphon now supports using environment variables for database connection URIs, providing better security and flexibility for deployment scenarios.

## Configuration Options

### Option 1: Environment Variables (Recommended)

Leave `source_uri` and `target_uri` empty in your config file:

```yaml
tables:
    - source_uri: "" # Will use SOURCE_DATABASE_URI environment variable
      target_uri: "" # Will use TARGET_DATABASE_URI environment variable
      source_table: "users"
      target_table: "users"
      # ... other config ...
```

Set the following environment variables:

```bash
export SOURCE_DATABASE_URI="clickhouse://admin:password@localhost:8123/default"
export TARGET_DATABASE_URI="postgresql://user:password@localhost:5432/target_db"
```

### Option 2: Config File URIs

Specify URIs directly in the configuration file:

```yaml
tables:
    - source_uri: "clickhouse://admin:password@localhost:8123/default"
      target_uri: "postgresql://user:password@localhost:5432/target_db"
      source_table: "users"
      target_table: "users"
      # ... other config ...
```

### Option 3: Mixed Configuration

You can mix both approaches - some tables using environment variables, others using explicit URIs:

```yaml
tables:
    # This table uses environment variables
    - source_uri: ""
      target_uri: ""
      source_table: "users"
      target_table: "users"
      # ... config ...

    # This table uses explicit URIs
    - source_uri: "clickhouse://admin:secret@prod-clickhouse:8123/analytics"
      target_uri: "postgresql://app:secret@prod-postgres:5432/warehouse"
      source_table: "events"
      target_table: "events"
      # ... config ...
```

## Environment Variables

| Variable Name         | Description                        | Example                                               |
| --------------------- | ---------------------------------- | ----------------------------------------------------- |
| `SOURCE_DATABASE_URI` | URI for source database connection | `clickhouse://admin:password@localhost:8123/default`  |
| `TARGET_DATABASE_URI` | URI for target database connection | `postgresql://user:password@localhost:5432/warehouse` |

## Benefits

-   **Security**: Keep sensitive credentials out of config files
-   **Flexibility**: Different environments (dev, staging, prod) can use different credentials
-   **Docker/Kubernetes**: Easy integration with container orchestration secrets
-   **CI/CD**: Seamless integration with deployment pipelines

## Error Handling

If a URI is empty in the config and the corresponding environment variable is not set, the application will raise a clear error message:

```
Source URI is empty in config and SOURCE_DATABASE_URI environment variable is not set
```

## Supported Database URIs

-   **ClickHouse**: `clickhouse://user:password@host:port/database`
-   **PostgreSQL**: `postgresql://user:password@host:port/database`
-   **MySQL**: `mysql://user:password@host:port/database`
