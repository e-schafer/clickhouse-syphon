import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Any, Callable

import polars as pl
from loguru import logger
from sqlalchemy import Engine, create_engine, inspect, text


def log_execution_time(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to log the execution time of a function.

    Parameters:
        func: The function to be decorated.

    Returns:
        The wrapped function that logs execution time.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        logger.info(f"'{func.__name__}' executed in {duration:.4f} seconds")
        return result

    return wrapper


def create_target_table_if_not_exists(
    source_uri: str,
    table_name: str,
    target_engine: Engine,
    columns_pk: list[str],
) -> None:
    """
    Create target table if it doesn't exist based on source DataFrame schema.
    Adds primary key constraint on specified columns.

    Parameters:
        source_df: Source DataFrame to infer schema from
        table_name: Name of the target table to create
        target_engine: SQLAlchemy engine for target database
        columns_pk: List of column names to set as primary key
    """
    inspector = inspect(target_engine)

    if not inspector.has_table(table_name):
        logger.info(f"Creating target table '{table_name}' as it doesn't exist")

        # Create table using polars schema
        # First write to a temporary table to get the structure, then rename
        pl.read_database_uri(
            query="SELECT * FROM " + table_name + " WHERE 1=0",
            uri=source_uri,
            engine="connectorx",
        ).write_database(
            table_name,
            target_engine,
            if_table_exists="replace",
        )
        logger.info(f"Created table '{table_name}' with schema from source")

        # Add primary key constraint
        pk_columns = ", ".join(columns_pk)
        alter_query = text(f"ALTER TABLE {table_name} ADD PRIMARY KEY ({pk_columns})")
        with target_engine.connect() as conn:
            conn.execute(alter_query)
            conn.commit()
            logger.info(f"Added primary key on columns ({pk_columns}) to table '{table_name}'")
    else:
        with target_engine.connect() as conn:
            conn.execute(text("TRUNCATE TABLE " + table_name))
            conn.commit()
            logger.info(f"Truncated existing table '{table_name}'")


@log_execution_time
def merge_copy(
    target_engine: Engine,
    staging_table_name: str,
    columns_pk: list[str],
) -> None:
    """
    Merge data from source DataFrame into target table using upsert logic.

    Parameters:
        source_df: Source DataFrame to merge
        target_engine: SQLAlchemy engine for target database
        table_name: Name of the target table to merge into
    """
    schema = pl.read_database(
        query=f"SELECT * FROM {staging_table_name} WHERE 1=0",
        connection=target_engine,
    ).columns
    [schema.remove(col) for col in columns_pk if col in schema]
    excluded = ",\n    ".join([f"{col} = EXCLUDED.{col}" for col in schema])

    # Build the target table name safely
    target_table = staging_table_name.rstrip("_copy")
    pk_columns_str = ", ".join(columns_pk)

    # Use proper parameter binding for table names in the actual query
    merge_query = text(f"""
INSERT INTO {target_table}
SELECT * FROM {staging_table_name}
ON CONFLICT ({pk_columns_str}) DO UPDATE SET
    {excluded}
    """)

    logger.debug(f"Executing merge query:\n{merge_query}")
    with target_engine.connect() as conn:
        result = conn.execute(merge_query)
        conn.commit()
        logger.info(f"Merged {result.rowcount} rows into campagne table")


@log_execution_time
def retrieve_checkpoint(target_engine: Engine, table: str, column: str):
    """
    Retrieve the maximum value of a specified column from a target table.

    Parameters:
        target_engine: SQLAlchemy engine for target database
        table: Name of the target table to query
        column: Column name to retrieve the maximum value from"""
    query = text(f"SELECT MAX({column}) AS max_value FROM {table}")
    with target_engine.connect() as conn:
        result = conn.execute(query).fetchone()
        logger.info(f"value: {result.max_value} from {table}.{column}")
        return result.max_value


@log_execution_time
def copy_data(
    source_engine: Engine,
    source_query: str,
    target_engine: Engine,
    target_table_name: str,
) -> None:
    """
    Copy data from source database to target database using polars.

    Parameters:
        source_engine: SQLAlchemy engine for source database
        source_query: SQL query to fetch data from source
        target_engine: SQLAlchemy engine for target database
        target_table_name: Name of the target table to write data into
    """
    logger.info(f"Reading data from source and writing to target table '{target_table_name}'")

    iterator = pl.read_database(
        query=source_query,
        connection=source_engine,
        iter_batches=True,
        batch_size=50000,
    )

    def write_batch(df: pl.DataFrame) -> None:
        """Write a single DataFrame batch to the target database."""
        df.write_database(
            target_table_name,
            target_engine,
            if_table_exists="append",
        )

    # Use ThreadPoolExecutor to parallelize the writes
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(write_batch, df) for df in iterator]
        # Wait for all writes to complete
        for future in futures:
            future.result()


@log_execution_time
def main():
    """
    Read a table from source database and write it to target database.
    Using polars as middleman for data transfer operations.
    Handles table creation and upsert operations automatically.


    """
    # Database connection configurations
    click_source_url = os.environ["SOURCE_URI"]
    target_url = os.environ["TARGET_URI"]
    table = "campagne"
    staging_table = "campagne_copy"
    column_unique_id = "id"
    column_checkpoint = "created_at"
    columns_pk = [column_unique_id, column_checkpoint]

    source_engine: Engine = create_engine(click_source_url)
    target_engine: Engine = create_engine(target_url)

    checkpoint = retrieve_checkpoint(target_engine, table, column_checkpoint)

    # Build source query with optional checkpoint filtering
    source_query = f"""SELECT * FROM {table}"""
    if checkpoint:
        logger.info(f"Using checkpoint to filter source data: {checkpoint}")
        source_query += f" WHERE {column_checkpoint} > '{checkpoint}'"
    logger.info(f"Source query: {source_query}")

    copy_data(
        source_engine,
        source_query,
        target_engine,
        staging_table,
    )

    # Merge from staging to main table
    merge_copy(target_engine, staging_table, columns_pk)


if __name__ == "__main__":
    exit(main())
