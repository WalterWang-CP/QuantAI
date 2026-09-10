import json
from pathlib import Path

from app.policy.models import ResearchPolicy


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIRECTORY = PROJECT_ROOT / "config"

DEFAULT_POLICY_FILE = CONFIG_DIRECTORY / "default_policy.json"
ACTIVE_POLICY_FILE = CONFIG_DIRECTORY / "active_policy.json"


def load_policy_from_file(file_path: Path) -> ResearchPolicy:
    with file_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return ResearchPolicy.model_validate(data)


def save_policy_to_file(
    policy: ResearchPolicy,
    file_path: Path,
) -> None:
    CONFIG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    with file_path.open("w", encoding="utf-8") as file:
        json.dump(
            policy.model_dump(mode="json"),
            file,
            indent=4,
        )


def get_active_policy() -> ResearchPolicy:
    if ACTIVE_POLICY_FILE.exists():
        return load_policy_from_file(ACTIVE_POLICY_FILE)

    default_policy = load_policy_from_file(DEFAULT_POLICY_FILE)

    save_policy_to_file(
        default_policy,
        ACTIVE_POLICY_FILE,
    )

    return default_policy


def update_active_policy(
    policy: ResearchPolicy,
) -> ResearchPolicy:
    save_policy_to_file(
        policy,
        ACTIVE_POLICY_FILE,
    )

    return policy