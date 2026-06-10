# Kiosk 配置管理中心

## ADDED

### Facility: Config Management API Server
A FastAPI-based HTTP server on bhs-4 that proxies config-serv APIs on all Kiosk terminals.

#### Requirement: Terminal List
The system SHALL maintain a static YAML file listing all Kiosk terminals (IP, alias, group, port).

#### Requirement: Online Detection
The system SHALL check each terminal's config-serv availability and report online/offline status.

#### Requirement: Config Read Proxy
The system SHALL proxy GET requests to each terminal's config-serv API for reading configuration.

#### Requirement: Config Write Proxy
The system SHALL proxy PUT requests to each terminal's config-serv API for writing configuration.

#### Requirement: Batch Operations
The system SHALL support batch config writes to multiple terminals (by IP list or group).

#### Requirement: Config Comparison
The system SHALL support comparing config values across selected terminals, highlighting differences.

#### Required Behavior: Error Handling
- If a terminal is offline, its config operations SHALL return a clear error, not crash the entire batch.
- Batch operations SHALL continue on failure for individual terminals.

### Facility: Web Management UI

#### Requirement: Terminal Dashboard
The system SHALL provide a web page showing all terminals, their online status, alias, and group.

#### Requirement: Config Viewer
The system SHALL provide a web page to view all config from a single terminal.

#### Requirement: Config Editor
The system SHALL provide a web page with a form to edit a terminal's configuration.

#### Requirement: Batch Editor
The system SHALL provide a web page to select terminals/groups and push config changes in bulk.

#### Requirement: Config Comparison View
The system SHALL provide a web page to compare configs across selected terminals with visual diff.
