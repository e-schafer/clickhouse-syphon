import os

from loguru import logger
from syphon import Syphon
from utils import log_execution_time

from config import Config, TableConfig


@log_execution_time
def main() -> int:
    """
    Main function to run the ClickHouse Syphon application.
    """

    # Load configuration
    config_path = os.getenv("CONFIG_PATH", "config/config.yaml")
    try:
        config = Config.from_yaml_file(config_path)
        logger.info(f"Configuration loaded from {config_path}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1

    # Process each table in the configuration
    for table_cfg in config.tables:
        if not isinstance(table_cfg, TableConfig):
            logger.error(f"Invalid table configuration: {table_cfg}")
            continue

        logger.info(f"Starting sync for table: {table_cfg.source_table} -> {table_cfg.target_table}")

        try:
            syphon = Syphon(table_cfg)
            syphon.run()
            logger.info(f"Completed sync for table: {table_cfg.source_table} -> {table_cfg.target_table}")
        except Exception as e:
            logger.exception(e)
            logger.error(f"Error during sync for table {table_cfg.source_table}: {e}")

    return 0


if __name__ == "__main__":
    exit(main())
