import os
import random
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import wraps
from typing import Any

from loguru import logger
from sqlalchemy import Connection, create_engine, text

"""
Script to create and populate a ClickHouse table with N million records.
Each ID (0-200) has daily records with realistic access patterns.
"""

NUMBER_OF_CAMPAIGNS = 3000
NUMBER_OF_RECORDS = 10300004
TABLE_NAME = "campagne"


def create_table(connection: Connection) -> None:
    """
    Create the campagne table in ClickHouse.

    Args:
        client: ClickHouse client connection
    """
    create_table_query = """
    CREATE TABLE IF NOT EXISTS campagne (
        id UInt32,
        created_at DateTime,
        count_access UInt32,
        count_read UInt32,
        avg_access_per_day Float32
    ) ENGINE = MergeTree()
    ORDER BY (id, created_at)
    """
    connection.execute(text(create_table_query))
    connection.commit()
    logger.info(f"Table '{TABLE_NAME}' created successfully")


def generate_data(connection: Connection, id: int):
    bulk = []

    for day in range(NUMBER_OF_RECORDS // NUMBER_OF_CAMPAIGNS):
        count_access = random.randint(50, 300)
        count_read = random.randint(30, min(count_access, 250))
        avg_access_per_day = round(count_access + random.uniform(-20, 20), 1)

        record = {
            "id": id,
            "created_at": (datetime.now() - timedelta(days=day)),
            "count_access": count_access,
            "count_read": count_read,
            "avg_access_per_day": max(0, avg_access_per_day),
        }
        bulk.append(record)
    connection.execute(
        text(
            "INSERT INTO campagne (id, created_at, count_access, count_read, avg_access_per_day) "
            "VALUES (:id, :created_at, :count_access, :count_read, :avg_access_per_day)"
        ),
        bulk,
    )

    connection.commit()


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


@log_execution_time
def main() -> None:
    """
    Main function to create table and populate with N records.
    """
    # Connection parameters
    source_url = os.environ["SOURCE_URI"]

    # Create engine and connection for initial setup
    engine = create_engine(source_url)
    with engine.connect() as connection:
        # Truncate the table at the start
        connection.execute(text(f"TRUNCATE TABLE IF EXISTS {TABLE_NAME}"))
        connection.commit()
        logger.info(f"Table '{TABLE_NAME}' truncated successfully")

        # Create the table
        create_table(connection)
    import concurrent.futures

    # Create a thread-local storage for database connections
    thread_local = threading.local()

    def get_connection():
        """Get or create a database connection for the current thread."""
        if not hasattr(thread_local, "connection"):
            engine = create_engine(source_url)
            thread_local.connection = engine.connect()
        return thread_local.connection

    def process_campaign(campaign_id: int) -> None:
        """Process a single campaign with thread-local connection."""
        conn = get_connection()
        generate_data(conn, campaign_id)

    # Use ThreadPoolExecutor with 5 workers for parallel execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        # Submit all campaign processing tasks
        futures = [executor.submit(process_campaign, campaign_id) for campaign_id in range(NUMBER_OF_CAMPAIGNS)]

        # Wait for all tasks to complete
        concurrent.futures.wait(futures)
    logger.info(f"Inserted {NUMBER_OF_RECORDS} records into '{TABLE_NAME}' table")


if __name__ == "__main__":
    main()
