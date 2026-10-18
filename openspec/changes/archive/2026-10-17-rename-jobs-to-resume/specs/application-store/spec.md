## REMOVED Requirements

### Requirement: Excluded from output retention
**Reason**: The service no longer runs retention cleanup, so nothing in the output directory is deleted automatically. Output storage's "Company folder naming" requirement keeps resume folders from colliding with the store file.
**Migration**: None needed. The store file is still never deleted by the service.
