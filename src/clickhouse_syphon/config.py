import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class TableConfig(BaseModel):
    """
    Configuration class for table synchronization settings.

    Contains all necessary parameters to define how a table should be
    synchronized between source and target databases, including connection
    URIs, table mapping, sync modes, and performance settings.
    """

    source_uri: str = Field(default="", description="Source database connection URI (can be empty to use env variable)")
    source_table: str = Field(..., description="Source table name")
    target_uri: str = Field(default="", description="Target database connection URI (can be empty to use env variable)")
    target_table: str = Field(..., description="Target table name")
    primary_keys: list[str] = Field(..., description="Primary keys columns name")
    sync_mode: str = Field(..., description="Synchronization mode (incremental or rewind)")
    sync_column: str = Field(..., description="Column used for synchronization tracking")
    batch_size: int = Field(..., gt=0, description="Number of records per batch")
    number_of_workers: int = Field(..., gt=0, le=16, description="Number of parallel workers")

    @field_validator("source_uri")
    @classmethod
    def validate_source_uri(cls, v: str) -> str:
        """Validate source URI format if provided (empty strings are allowed)."""
        if not v.strip():
            return ""  # Allow empty strings
        return cls._validate_database_uri(v, "Source")

    @classmethod
    def _validate_database_uri(cls, uri: str, uri_type: str) -> str:
        """
        Validate database URI format and content.

        Parameters:
        uri (str): The database URI to validate
        uri_type (str): Type of URI (e.g., "Source", "Target") for error messages

        Returns:
        str: The validated and stripped URI

        Raises:
        ValueError: If URI has invalid format (empty strings are handled by callers)
        """
        cleaned_uri = uri.strip()

        # If empty after stripping, let the caller handle it
        if not cleaned_uri:
            return cleaned_uri

        # Check for protocol presence
        if "://" not in cleaned_uri:
            raise ValueError(
                f"{uri_type} URI must contain a valid protocol (e.g., clickhouse://, postgresql://, mysql://)"
            )

        # Extract protocol and validate it's not empty
        protocol = cleaned_uri.split("://")[0]
        if not protocol:
            raise ValueError(f"{uri_type} URI protocol cannot be empty")

        # Check for common database protocols
        valid_protocols = {
            "clickhouse",
            "postgresql",
            "postgres",
        }

        if protocol.lower() not in valid_protocols:
            raise ValueError(
                f"{uri_type} URI protocol '{protocol}' is not recognized. "
                f"Supported protocols: {', '.join(sorted(valid_protocols))}"
            )

        return cleaned_uri

    @field_validator("source_table")
    @classmethod
    def validate_source_table(cls, v: str) -> str:
        """Validate that source table name is not empty."""
        if not v.strip():
            raise ValueError("Source table name cannot be empty")
        return v.strip()

    @field_validator("target_uri")
    @classmethod
    def validate_target_uri(cls, v: str) -> str:
        """Validate target URI format if provided (empty strings are allowed)."""
        if not v.strip():
            return ""  # Allow empty strings
        return cls._validate_database_uri(v, "Target")

    @field_validator("target_table")
    @classmethod
    def validate_target_table(cls, v: str) -> str:
        """Validate that target table name is not empty."""
        if not v.strip():
            raise ValueError("Target table name cannot be empty")
        return v.strip()

    @field_validator("primary_keys")
    @classmethod
    def validate_primary_keys(cls, v: list[str]) -> list[str]:
        """Validate that primary key column names are not empty."""
        if not v:
            raise ValueError("Primary key column names cannot be empty")

        # Validate each column name in the list
        validated_keys = []
        for key in v:
            if not key.strip():
                raise ValueError("Primary key column name cannot be empty")
            validated_keys.append(key.strip())

        return validated_keys

    @field_validator("sync_mode")
    @classmethod
    def validate_sync_mode(cls, v: str) -> str:
        """Validate that sync mode is one of the allowed values."""
        allowed_modes = {"incremental", "rewind"}
        if v not in allowed_modes:
            raise ValueError(f"Sync mode must be one of: {', '.join(allowed_modes)}")
        return v

    @field_validator("sync_column")
    @classmethod
    def validate_sync_column(cls, v: str) -> str:
        """Validate that sync column name is not empty."""
        if not v.strip():
            raise ValueError("Sync column name cannot be empty")
        return v.strip()

    @field_validator("number_of_workers")
    @classmethod
    def validate_number_of_workers(cls, v: int) -> int:
        """Validate that number of workers is within reasonable limits."""
        if v < 1:
            raise ValueError("Number of workers must be at least 1")
        if v > 16:
            raise ValueError("Number of workers cannot exceed 16 for performance reasons")
        return v

    def get_resolved_source_uri(self) -> str:
        """
        Get the resolved source URI, using environment variable if config URI is empty.

        Returns:
            str: The resolved source URI

        Raises:
            ValueError: If neither config nor environment variable provides a valid URI
        """
        if self.source_uri.strip():
            return self.source_uri

        # Try to get from environment variable
        env_uri = os.getenv("SOURCE_DATABASE_URI", "").strip()
        if not env_uri:
            raise ValueError("Source URI is empty in config and SOURCE_DATABASE_URI environment variable is not set")

        # Validate the environment URI
        return self._validate_database_uri(env_uri, "Source (from environment)")

    def get_resolved_target_uri(self) -> str:
        """
        Get the resolved target URI, using environment variable if config URI is empty.

        Returns:
            str: The resolved target URI

        Raises:
            ValueError: If neither config nor environment variable provides a valid URI
        """
        if self.target_uri.strip():
            return self.target_uri

        # Try to get from environment variable
        env_uri = os.getenv("TARGET_DATABASE_URI", "").strip()
        if not env_uri:
            raise ValueError("Target URI is empty in config and TARGET_DATABASE_URI environment variable is not set")

        # Validate the environment URI
        return self._validate_database_uri(env_uri, "Target (from environment)")


class Config(BaseModel):
    """
    Main configuration class for the ClickHouse Syphon application.

    Contains a list of table configurations that define how data should be
    synchronized between source and target databases.
    """

    tables: list[TableConfig] = Field(..., description="List of table synchronization configurations")

    @field_validator("tables")
    @classmethod
    def validate_tables(cls, v: list[TableConfig]) -> list[TableConfig]:
        """Validate that at least one table configuration is provided."""
        if not v:
            raise ValueError("At least one table configuration must be provided")
        return v

    @classmethod
    def from_yaml_file(cls, file_path: str | Path) -> "Config":
        """
        Load configuration from a YAML file.

        Parameters:
            file_path (str | Path): Path to the YAML configuration file

        Returns:
            Config: Validated configuration object

        Raises:
            FileNotFoundError: If the configuration file doesn't exist
            yaml.YAMLError: If the YAML file is malformed
            ValidationError: If the configuration doesn't match the schema
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML file {file_path}: {e}") from e

        if data is None:
            raise ValueError(f"Configuration file is empty: {file_path}")

        return cls(**data)

    @classmethod
    def from_yaml_string(cls, yaml_content: str) -> "Config":
        """
        Load configuration from a YAML string.

        Parameters:
            yaml_content (str): YAML content as string

        Returns:
            Config: Validated configuration object

        Raises:
            yaml.YAMLError: If the YAML content is malformed
            ValidationError: If the configuration doesn't match the schema
        """
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML content: {e}") from e

        if data is None:
            raise ValueError("YAML content is empty")

        return cls(**data)
