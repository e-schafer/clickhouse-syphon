from concurrent.futures import ThreadPoolExecutor

import polars as pl
from loguru import logger
from sqlalchemy import Connection, Engine, create_engine, inspect, text

from config import TableConfig


class Syphon:
    """
    Data synchronization class for copying data between source and target databases.

    Supports both direct parameter initialization and TableConfig-based initialization
    for flexible configuration management.
    """

    def __init__(self, config: TableConfig) -> None:
        """
        Initialize Syphon with a TableConfig object.

        Parameters:
            config (TableConfig): Table configuration containing all sync parameters
        """
        self.config = config
        # Resolve URIs from config or environment variables
        self.source_uri = config.get_resolved_source_uri()
        self.target_uri = config.get_resolved_target_uri()
        self.source_table = config.source_table
        self.target_table = config.target_table
        self.primary_keys = config.primary_keys
        self.sync_mode = config.sync_mode
        self.sync_column = config.sync_column
        self.batch_size = config.batch_size
        self.number_of_workers = config.number_of_workers

        # Create database engines
        self.source_engine = create_engine(self.source_uri)
        self.target_engine = create_engine(self.target_uri)

    @log_execution_time
    def merge_copy(
        self,
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

        pk_columns_str = ", ".join(columns_pk)

        # Use proper parameter binding for table names in the actual query
        merge_query = text(f"""
INSERT INTO {self.target_table}
SELECT * FROM {staging_table_name}
ON CONFLICT ({pk_columns_str}) DO UPDATE SET
    {excluded}
    """)

        logger.debug(f"Executing merge query:\n{merge_query}")
        result = target_conn.execute(merge_query)
        target_conn.commit()
        logger.info(f"Merged {result.rowcount} rows into campagne table")

    @log_execution_time
    def retrieve_checkpoint(self, target_conn: Connection, table: str, column: str):
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
    def copy_data_to_staging(
        self,
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
        # Use configuration values for batch size and workers
        batch_size = self.batch_size
        max_workers = self.number_of_workers

        def write_batch(batch_data: tuple[int, pl.DataFrame]) -> None:
            """
            Write a single DataFrame batch to the target database using a dedicated connection.

            Parameters:
                batch_data (tuple[int, pl.DataFrame]): Tuple containing batch index and DataFrame

            Returns:
                None
            """
            index, df = batch_data

            # Create a dedicated connection for this thread to avoid transaction conflicts
            with target_engine.connect() as conn:
                logger.debug(f"Writing batch {index} with {len(df)} rows to target")
                df.write_database(
                    target_table_name,
                    conn,
                    if_table_exists="append",
                )
                logger.debug(f"Batch {index} completed successfully")

        logger.info(
            f"Reading data from source and writing to target table '{target_table_name}' "
            f"with {max_workers} parallel workers, batch size {batch_size:,}"
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

        logger.info(f"Processing {total_batches} batches of {batch_size:,} rows each")

        # Process batches in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batch write operations
            futures = [executor.submit(write_batch, batch_data) for batch_data in batches]

            # Wait for all batches to complete and handle any exceptions
            completed = 0
            for future in futures:
                try:
                    future.result()  # This will raise any exception that occurred
                    completed += 1
                    if completed % 10 == 0 or completed == total_batches:
                        logger.info(f"Completed {completed}/{total_batches} batches")
                except Exception as e:
                    logger.error(f"Error processing batch: {e}")
                    raise

        logger.info(f"Successfully wrote all {total_batches} batches to target table '{target_table_name}'")

    def truncate_staging(self, staging_table: str, target_conn: Connection) -> None:
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

    def build_source_query(self, table: str, target_conn: Connection) -> str:
        """
        Build a SQL query to select data from a source table with optional checkpoint filtering.

        This function constructs a SELECT query for the specified table. If a checkpoint value
        exists for the given checkpoint column, it adds a WHERE clause to filter records
        that are newer than the checkpoint value.

        Args:
            table (str): The name of the source table to query.
            target_conn (Connection): The database connection to retrieve checkpoint information.

        Returns:
            str: A SQL SELECT query string, optionally filtered by checkpoint value.

        Example:
            Without checkpoint: "SELECT * FROM users"
            With checkpoint: "SELECT * FROM users WHERE created_at > '2023-01-01 00:00:00'"
        """
        checkpoint = self.retrieve_checkpoint(target_conn, table, self.sync_column)
        source_query = f"""SELECT * FROM {table}"""

        if checkpoint and self.sync_mode == "incremental":
            source_query += f" WHERE {self.sync_column} > '{checkpoint}'"
            logger.info(f"Using incremental sync with checkpoint: {checkpoint}")
        elif self.sync_mode == "rewind":
            logger.info("Using rewind mode - processing all data")

        logger.info(f"Source query: {source_query}")
        return source_query

    def copy(self) -> int:
        """
        Main method to perform the data copy from source to target.

        Returns:
            int: Exit code (0 for success, 1 for failure)
        """
        target_conn: Connection = self.target_engine.connect()
        source_conn: Connection = self.source_engine.connect()
        try:
            # Build source query with optional checkpoint filtering using config
            source_query = self.build_source_query(self.source_table, target_conn)

            # Create staging table name
            staging_table = self.target_table + "_staging"
            self.truncate_staging(staging_table, target_conn)

            self.copy_data_to_staging(
                self.source_engine,
                source_query,
                self.target_engine,
                staging_table,
            )
            # Merge from staging to main table using configured primary key
            self.merge_copy(target_conn, staging_table, self.primary_keys)
            return 0
        except Exception as e:
            logger.exception(e)
            return 1
        finally:
            source_conn.close()
            target_conn.close()

    def run(self) -> int:
        """
        Public method to run the synchronization process.

        Returns:
            int: Exit code (0 for success, 1 for failure)
        """
        logger.info(f"Starting synchronization: {self.source_table} -> {self.target_table}")
        logger.info(f"Sync mode: {self.sync_mode}, Sync column: {self.sync_column}")
        logger.info(f"Batch size: {self.batch_size:,}, Workers: {self.number_of_workers}")

        result = self.copy()

        if result == 0:
            logger.info(f"Successfully completed synchronization: {self.source_table} -> {self.target_table}")
        else:
            logger.error(f"Failed synchronization: {self.source_table} -> {self.target_table}")

        return result
