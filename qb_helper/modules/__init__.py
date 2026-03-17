from qb_helper.modules.disk_space_cleanup import DiskSpaceCleanupModule
from qb_helper.modules.stalled_cleanup import StalledCleanupModule
from qb_helper.modules.tag_share_limit import TagShareLimitModule
from qb_helper.modules.value_retention_cleanup import ValueRetentionCleanupModule

MODULE_REGISTRY = {
    DiskSpaceCleanupModule.name: DiskSpaceCleanupModule,
    StalledCleanupModule.name: StalledCleanupModule,
    TagShareLimitModule.name: TagShareLimitModule,
    ValueRetentionCleanupModule.name: ValueRetentionCleanupModule,
}
