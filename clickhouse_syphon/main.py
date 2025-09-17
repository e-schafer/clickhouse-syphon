import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import Any, Callable

import polars as pl
from loguru import logger
from sqlalchemy import Connection, Engine, create_engine, inspect, text


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
    source_conn: Connection,
    table_name: str,
    target_conn: Connection,
    columns_pk: list[str],
) -> None:
    """
    Create target table if it doesn't exist based on source database schema.
    Adds primary key constraint on specified columns.

    Parameters:
        source_uri (str): Database URI for source connection
        table_name (str): Name of the target table to create
        target_conn (Connection): SQLAlchemy connection for target database
        columns_pk (list[str]): List of column names to set as primary key

    Returns:
        None
    """
    inspector = inspect(target_conn)

    if not inspector.has_table(table_name):
        logger.info(f"Creating target table '{table_name}' as it doesn't exist")

        # Create table using polars schema
        # First write to a temporary table to get the structure, then rename
        pl.read_database(
            query="SELECT * FROM " + table_name + " WHERE 1=0",
            connection=source_conn,
        ).write_database(
            table_name,
            target_conn,
            if_table_exists="replace",
        )
        logger.info(f"Created table '{table_name}' with schema from source")

        # Add primary key constraint
        pk_columns = ", ".join(columns_pk)
        alter_query = text(f"ALTER TABLE {table_name} ADD PRIMARY KEY ({pk_columns})")
        target_conn.execute(alter_query)
        target_conn.commit()
        logger.info(f"Added primary key on columns ({pk_columns}) to table '{table_name}'")
    else:
        target_conn.execute(text("TRUNCATE TABLE " + table_name))
        target_conn.commit()
        logger.info(f"Truncated existing table '{table_name}'")


@log_execution_time
def merge_copy(
    target_conn: Connection,
    staging_table_name: str,
    columns_pk: list[str],
) -> None:
    """
    Merge data from staging table into target table using upsert logic.

    Parameters:
        target_conn (Connection): SQLAlchemy connection for target database
        staging_table_name (str): Name of the staging table to merge from
        columns_pk (list[str]): List of primary key column names for conflict resolution

    Returns:
        None
    """
    schema = pl.read_database(
        query=f"SELECT * FROM {staging_table_name} WHERE 1=0",
        connection=target_conn,
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
    result = target_conn.execute(merge_query)
    target_conn.commit()
    logger.info(f"Merged {result.rowcount} rows into campagne table")


@log_execution_time
def retrieve_checkpoint(target_conn: Connection, table: str, column: str):
    """
    Retrieve the maximum value of a specified column from a target table.

    Parameters:
        target_engine (Engine): SQLAlchemy engine for target database
        table (str): Name of the target table to query
        column (str): Column name to retrieve the maximum value from

    Returns:
        Any: Maximum value from the specified column, or None if no data found
    """
    query = text(f"SELECT MAX({column}) AS max_value FROM {table}")
    result = target_conn.execute(query).fetchone()
    if result is None:
        logger.info(f"No data found in {table}.{column}")
        return None
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
    Copy data from source database to target database using polars with batch processing and parallelization.

    Parameters:
        source_engine (Engine): SQLAlchemy engine for source database
        source_query (str): SQL query to fetch data from source
        target_engine (Engine): SQLAlchemy engine for target database
        target_table_name (str): Name of the target table to write data into

    Returns:
        None
    """
    batch_size = 100000  # Optimized batch size for parallel processing
    max_workers = 4  # Number of parallel threads

    @log_execution_time
    def write_batch(batch_data: tuple[int, pl.DataFrame]) -> None:
        """
        Write a single DataFrame batch to the target database using a dedicated connection.

        Parameters:
            batch_data (tuple[int, pl.DataFrame]): Tuple containing batch index and DataFrame

        Returns:
            None
        """
        index, df = batch_data
        logger.debug(f"Writing batch {index} with {len(df)} rows to target")
        df.write_database(target_table_name, target_engine, if_table_exists="append")

    logger.info(
        f"Reading data from source and writing to target table '{target_table_name}' with {max_workers} parallel workers"
    )

    # Read data in batches from source
    iterator = pl.read_database(
        query=source_query,
        connection=source_engine,
        iter_batches=True,
        batch_size=batch_size,
    )

    # Convert iterator to list of tuples (index, dataframe) for parallel processing
    batches = [(index, batch) for index, batch in enumerate(iterator)]
    total_batches = len(batches)

    logger.info(f"Processing {total_batches} batches of {batch_size} rows each")

    # Process batches in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batch write operations
        futures = [executor.submit(write_batch, batch_data) for batch_data in batches]

        # Wait for all batches to complete and handle any exceptions
        for index, future in enumerate(futures):
            try:
                future.result()  # This will raise any exception that occurred
                if (index + 1) % 10 == 0 or (index + 1) == total_batches:
                    logger.info(f"Completed {index + 1}/{total_batches} batches")
            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                raise

    logger.info(f"Successfully wrote all {total_batches} batches to target table '{target_table_name}'")


def truncate_staging(staging_table: str, target_conn: Connection) -> None:
    """
    Truncate the staging table if it exists.

    Parameters:
        staging_table (str): Name of the staging table to truncate
        target_conn (Connection): SQLAlchemy connection for target database
    Returns:
        None
    """
    inspector = inspect(target_conn)
    if inspector.has_table(staging_table):
        logger.info(f"Truncating existing staging table '{staging_table}'")
        target_conn.execute(text(f"TRUNCATE TABLE {staging_table}"))
        target_conn.commit()
        logger.info(f"Staging table '{staging_table}' truncated successfully")
    else:
        logger.info(f"Staging table '{staging_table}' does not exist, no need to truncate")


def build_source_query(table: str, column_checkpoint: str, target_conn: Connection) -> str:
    """
    Build a SQL query to select data from a source table with optional checkpoint filtering.

    This function constructs a SELECT query for the specified table. If a checkpoint value
    exists for the given checkpoint column, it adds a WHERE clause to filter records
    that are newer than the checkpoint value.

    Args:
        table (str): The name of the source table to query.
        column_checkpoint (str): The name of the column used for checkpoint comparison.
        target_conn (Connection): The database connection to retrieve checkpoint information.

    Returns:
        str: A SQL SELECT query string, optionally filtered by checkpoint value.

    Example:
        Without checkpoint: "SELECT * FROM users"
        With checkpoint: "SELECT * FROM users WHERE created_at > '2023-01-01 00:00:00'"
    """

    checkpoint = retrieve_checkpoint(target_conn, table, column_checkpoint)
    source_query = f"""SELECT * FROM {table}"""
    if checkpoint:
        source_query += f" WHERE {column_checkpoint} > '{checkpoint}'"
    logger.info(f"Source query: {source_query}")
    return source_query


@log_execution_time
def main() -> int:
    """
    Main function that orchestrates the data synchronization process between source and target databases.

    This function performs an incremental data copy operation by:
    1. Establishing connections to source and target databases using environment variables
    2. Building a source query with optional checkpoint filtering for incremental updates
    3. Truncating the staging table to prepare for new data
    4. Copying data from source to staging table
    5. Merging data from staging table to the main target table using primary keys

    Environment Variables:
        SOURCE_URI: Connection string for the source ClickHouse database
        TARGET_URI: Connection string for the target database

    Returns:
        int: 0 on successful completion, 1 if an exception occurs

    Raises:
        Exception: Any database connection or operation errors are logged and handled gracefully

    Note:
        Database connections are properly closed in the finally block to ensure resource cleanup.
    """
    # Database connection configurations
    click_source_url = os.environ["SOURCE_URI"]
    target_url = os.environ["TARGET_URI"]
    table = "campagne"
    staging_table = "campagne_copy"
    column_unique_id = "id"
    column_checkpoint = "created_at"
    columns_pk = [column_unique_id, column_checkpoint]
    # Create engines with optimized connection pool settings
    source_engine = create_engine(
        click_source_url,
        pool_size=10,  # Number of connections to maintain in pool
        max_overflow=20,  # Additional connections beyond pool_size
        pool_timeout=30,  # Seconds to wait for connection from pool
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_pre_ping=True,  # Validate connections before use
    )

    target_engine = create_engine(
        target_url,
        pool_size=15,  # Larger pool for target (more write operations)
        max_overflow=25,  # Additional connections for concurrent writes
        pool_timeout=30,  # Seconds to wait for connection from pool
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_pre_ping=True,  # Validate connections before use
    )

    source_conn = source_engine.connect()
    target_conn: Connection = target_engine.connect()
    try:
        # Build source query with optional checkpoint filtering
        source_query = build_source_query(table, column_checkpoint, target_conn)

        create_target_table_if_not_exists(
            source_conn,
            table,
            target_conn,
            columns_pk,
        )
        truncate_staging(staging_table, target_conn)

        copy_data(
            source_engine,
            source_query,
            target_engine,
            staging_table,
        )

        # Merge from staging to main table
        merge_copy(target_conn, staging_table, columns_pk)
        return 0
    except Exception as e:
        logger.exception(e)
        return 1
    finally:
        source_conn.close()
        target_conn.close()


if __name__ == "__main__":
    exit(main())
