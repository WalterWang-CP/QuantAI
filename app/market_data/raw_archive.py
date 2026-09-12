import hashlib
import uuid
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]


RAW_DATA_ROOT = (
    PROJECT_ROOT
    / "data"
    / "raw"
)


def sanitize_path_component(
    value: str,
) -> str:
    return "".join(
        character
        if character.isalnum()
        or character in {"-", "_", "."}
        else "_"
        for character in value
    )


def archive_raw_response(
    ingestion_run_id: uuid.UUID,
    provider_name: str,
    dataset_name: str,
    symbol: str,
    body: bytes,
) -> dict:
    checksum = hashlib.sha256(
        body
    ).hexdigest()

    safe_provider = sanitize_path_component(
        provider_name
    )

    safe_dataset = sanitize_path_component(
        dataset_name
    )

    safe_symbol = sanitize_path_component(
        symbol.upper()
    )

    directory = (
        RAW_DATA_ROOT
        / safe_provider
        / safe_dataset
        / safe_symbol
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path = (
        directory
        / f"{ingestion_run_id}.json"
    )

    file_path.write_bytes(
        body
    )

    relative_path = file_path.relative_to(
        PROJECT_ROOT
    )

    return {
        "storage_path":
            relative_path.as_posix(),
        "sha256":
            checksum,
        "byte_count":
            len(body),
    }