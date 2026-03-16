from qb_helper.modules.disk_space_cleanup import DiskSpaceCleanupModule
from qb_helper.modules.stalled_cleanup import StalledCleanupModule

MODULE_REGISTRY = {
    DiskSpaceCleanupModule.name: DiskSpaceCleanupModule,
    StalledCleanupModule.name: StalledCleanupModule,
}
