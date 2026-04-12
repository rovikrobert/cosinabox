"""Doctor check registry."""

from __future__ import annotations

from cosinabox.doctor.checks import (
    BriefingDriftCheck,
    Check,
    CostRunawayCheck,
    OAuthExpiringCheck,
    PersonalityThinCheck,
    PrepNoiseCheck,
    SchemaOutdatedCheck,
    SecretInTrackedFileCheck,
    StakeholdersEmptyCheck,
    StaleFollowupsCheck,
    ToolLoopExcessCheck,
)

REGISTRY: list[Check] = [
    PersonalityThinCheck(),
    StakeholdersEmptyCheck(),
    CostRunawayCheck(),
    ToolLoopExcessCheck(),
    PrepNoiseCheck(),
    BriefingDriftCheck(),
    SecretInTrackedFileCheck(),
    StaleFollowupsCheck(),
    OAuthExpiringCheck(),
    SchemaOutdatedCheck(),
]
