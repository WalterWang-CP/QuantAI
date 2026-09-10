from enum import Enum

from pydantic import BaseModel, Field, model_validator


class RankingFrequency(str, Enum):
    YEARLY = "yearly"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"


class UniverseSettings(BaseModel):
    main_universe_size: int = Field(
        gt=0,
        description="Number of companies in the main research universe",
    )

    ranking_frequency: RankingFrequency


class EliteTrackingSettings(BaseModel):
    enabled: bool

    threshold: int = Field(
        gt=0,
        description="Global rank required to trigger elite tracking",
    )

    historical_backfill_years: int = Field(
        ge=0,
        description="Number of historical years to reconstruct for elite companies",
    )


class DropoutTrackingSettings(BaseModel):
    enabled: bool

    tracking_years: int = Field(
        ge=0,
        description="Years to continue tracking a company after it leaves the main universe",
    )


class ResearchPolicy(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )

    universe: UniverseSettings
    elite_tracking: EliteTrackingSettings
    dropout_tracking: DropoutTrackingSettings

    @model_validator(mode="after")
    def validate_policy(self):
        if (
            self.elite_tracking.enabled
            and self.elite_tracking.threshold
            > self.universe.main_universe_size
        ):
            raise ValueError(
                "Elite threshold cannot be larger than the main universe size."
            )

        return self