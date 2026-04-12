"""Doctor check registry."""
from __future__ import annotations
from cosinabox.doctor.checks import (
    Check, PersonalityThinCheck, StakeholdersEmptyCheck, CostRunawayCheck,
    ToolLoopExcessCheck, PrepNoiseCheck, BriefingDriftCheck,
    SecretInTrackedFileCheck, StaleFollowupsCheck, OAuthExpiringCheck,
    SchemaOutdatedCheck,
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
