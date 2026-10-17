# resume-pdf-rendering Specification

## Purpose

Defines how the service turns the baseline resume LaTeX source into a PDF on its own host, so later changes can substitute generated TeX without changing the rendering path.

## Requirements

### Requirement: Render baseline resume to PDF
The system SHALL compile the bundled baseline resume TeX source, together with its bundled template files, into a PDF and return the PDF bytes.

#### Scenario: Successful render
- **WHEN** a render is requested
- **THEN** the result begins with the PDF file signature and has at least one page
- **AND** its text content includes the resume owner's name from the source

#### Scenario: Repeated renders
- **WHEN** two renders run in sequence or concurrently
- **THEN** each produces its own complete PDF without interfering with the other

### Requirement: Isolated build workspace
Each render SHALL run in its own temporary directory that is removed afterwards, and SHALL NOT modify the bundled source files.

#### Scenario: Cleanup
- **WHEN** a render finishes, successfully or not
- **THEN** its temporary directory no longer exists
- **AND** the bundled source files are unchanged

### Requirement: Bounded render time
A render SHALL be terminated if it exceeds a fixed time limit, and that outcome SHALL be reported as a render failure.

#### Scenario: Hung compiler
- **WHEN** the compiler does not finish within the limit
- **THEN** the process is killed and a render failure is raised

### Requirement: Offline rendering
Rendering SHALL NOT require network access at request time; all TeX packages and fonts needed by the baseline resume SHALL be present in the deployed image.

#### Scenario: No network
- **WHEN** a render runs in a container with outbound network blocked
- **THEN** the render succeeds

### Requirement: Bundled template assets
The deployed image SHALL contain the baseline TeX source and the custom resume class file it depends on.

#### Scenario: Missing class file
- **WHEN** the class file is absent from the template assets
- **THEN** a render fails and the failure is reported, rather than producing a wrong document
