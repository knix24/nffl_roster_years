# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it by opening a GitHub issue.

Since this tool:
- Only reads data from the public Sleeper API
- Does not handle authentication credentials
- Does not store sensitive user data
- Runs entirely locally on your machine

The attack surface is minimal. However, if you find something concerning, please let us know.

## Security Considerations

- The tool caches player data locally in `~/.cache/sleeper-tenure-tracker/`
- No personal data is transmitted beyond your Sleeper username (which is public)
- All API calls are made over HTTPS to Sleeper's official API
