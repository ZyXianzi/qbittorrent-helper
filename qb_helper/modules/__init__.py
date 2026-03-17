from qb_helper.modules.stalled_cleanup import StalledCleanupModule
from qb_helper.modules.value_retention_cleanup import ValueRetentionCleanupModule

MODULE_REGISTRY = {
    StalledCleanupModule.name: StalledCleanupModule,
    ValueRetentionCleanupModule.name: ValueRetentionCleanupModule,
}
