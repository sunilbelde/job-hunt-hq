# Spec Delta

## MODIFIED Requirements

### Requirement: Offline rendering
Rendering SHALL NOT require network access at request time. All TeX packages and fonts needed by the baseline resume SHALL be present in the service's local TeX cache after installation.

#### Scenario: No network
- **WHEN** a render runs on the installed Mac mini with outbound network blocked
- **THEN** the render succeeds

#### Scenario: Cache warmed at install
- **WHEN** the install script completes successfully
- **THEN** one render has already succeeded under the service's user and cache directory

### Requirement: Bundled template assets
The repository's `data/` directory, which the installed service reads its templates from, SHALL contain the baseline TeX source and the custom resume class file it depends on.

#### Scenario: Missing class file
- **WHEN** the class file is absent from the template assets
- **THEN** a render fails and the failure is reported, rather than producing a wrong document
