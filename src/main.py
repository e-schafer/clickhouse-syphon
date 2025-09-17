import os

from loguru import logger

from clickhouse_syphon.config import Config, TableConfig
from clickhouse_syphon.syphon import Syphon
from clickhouse_syphon.utils import log_execution_time


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
    try:
        from dotenv import load_dotenv

        load_dotenv()
        logger.info("Loaded environment variables from .env file")
        main()
    except ImportError:
        logger.debug("python-dotenv not available, skipping .env file loading")
    except Exception as e:
        logger.debug(f"No .env file found or error loading it: {e}")
