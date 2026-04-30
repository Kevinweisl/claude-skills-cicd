---
name: hello
description: |
  A dummy test skill that echoes back its input. Use only for platform health
  checks, smoke testing the invoke pipeline, or demonstrating the request/response
  flow. This skill exists to verify gateway → Postgres queue → worker → result
  end-to-end without external dependencies.
allowed-tools: ""
worker_target: ci
---

# Hello Skill

This skill is a dummy used to verify the platform's invoke pipeline is working
end-to-end. It does not call any external service.

## Input
```json
{"message": "string"}
```

## Output
```json
{"echo": "string", "timestamp": "ISO-8601 datetime"}
```
