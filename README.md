# dockAPI

A simple Python API to run and control Docker containers and optionally proxy requests to a container's published port.

Built with FastAPI and the Docker SDK for Python.

## Features

- Pull Docker images
- Run containers with a selected container port published to a host port (auto-assign or specify)
- List, inspect, start, stop, and remove containers (labeled as managed by this API)
- Reverse-proxy endpoint to interact with the container's API via this service
- CORS enabled for easy local testing

## Requirements

- Windows with Docker Desktop (or any OS with a working Docker engine)
- Python 3.10+

## Install and run

PowerShell commands (pwsh):

```powershell
# From the repo root
cd dockAPI

# Create and activate a virtual environment (recommended)
python -m venv .venv
. .venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start the API (http://127.0.0.1:8000)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the interactive docs: <http://127.0.0.1:8000/docs>

## API overview

- GET `/healthz` — Docker connectivity check
- GET `/images` — List images
- POST `/images/pull` — Pull an image
- GET `/containers` — List managed containers
- POST `/containers/run` — Run a container and publish a port
- GET `/containers/{id}` — Inspect container
- POST `/containers/{id}/stop` — Stop
- POST `/containers/{id}/start` — Start
- DELETE `/containers/{id}` — Remove
- GET `/containers/{id}/logs` — View logs (tail, follow)
- POST `/containers/{id}/exec` — Run a command inside the container
- GET `/proxy/{id}` — Show the upstream URL for the container
- ANY `/proxy/{id}/{path}` — Reverse-proxy to the container's published host port

All containers created by this API are labeled with `dockapi.managed=true`.

Quick links:

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

## Quickstart example: run and interact with an image

Below runs the official `nginx:latest` image, publishing container port 80 to an auto-assigned local host port, then accesses it via the proxy.

```powershell
# 1) Run a container
$body = @{
  image = "nginx:latest"
  container_port = 80
  # host_port = 8080   # optional: force a host port
  name = "my-nginx"   # optional
} | ConvertTo-Json

Invoke-RestMethod -Method POST `
  -Uri http://127.0.0.1:8000/containers/run `
  -ContentType 'application/json' `
  -Body $body

# Response example
# {
#   "id": "<container-id>",
#   "name": "my-nginx",
#   "image": "nginx:latest",
#   "status": "running",
#   "labels": {"dockapi.managed":"true","dockapi.name":"my-nginx","dockapi.container_port":"80"},
#   "host_port": 52347,
#   "container_port": 80
# }

# 2) Discover the upstream URL
Invoke-RestMethod -Uri http://127.0.0.1:8000/proxy/<container-id>
# => { "container_id":"<container-id>", "upstream":"http://127.0.0.1:<host_port>" }

# 3) Access the container through the dockAPI proxy
Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/proxy/<container-id>/ `
  -Method GET
```

You can also call the container directly at `http://127.0.0.1:<host_port>/...` using the `host_port` in the run response.

## Run container: request body

POST `/containers/run`

```json
{
  "image": "org/image:tag",
  "container_port": 8080,
  "host_port": 0,
  "name": "optional-name",
  "env": {"KEY":"VALUE"},
  "command": ["optional", "override"],
  "auto_remove": true,
  "detach": true,
  "restart_policy": "unless-stopped"
  ,
  "volumes": ["C:/host/data:/data:ro"],
  "network": "my-network",
  "wait_ready": true,
  "health_path": "/healthz",
  "wait_timeout": 30
}
```

Notes:

- If `host_port` is omitted or set to 0, the API auto-assigns a free localhost port.
- Only the specified `container_port` (TCP) is published.
- The reverse proxy routes requests to `http://127.0.0.1:<host_port>` using the same method, headers (minus hop-by-hop), query, and body.
- If `wait_ready` is true and `health_path` is provided, the API polls `http://127.0.0.1:<host_port><health_path>` until it returns 2xx or timeout.

### Using cURL instead of PowerShell

```bash
curl -X POST \
  http://127.0.0.1:8000/containers/run \
  -H 'content-type: application/json' \
  -d '{
        "image": "nginx:latest",
        "container_port": 80,
        "host_port": 0,
        "name": "nginx-demo",
        "wait_ready": true,
        "health_path": "/"
      }'
```

### Volume mounts (Windows)

```powershell
$body = @{
  image = "nginx:latest"
  container_port = 80
  volumes = @("C:/host/data:/usr/share/nginx/html:ro")
} | ConvertTo-Json

Invoke-RestMethod -Method POST `
  -Uri http://127.0.0.1:8000/containers/run `
  -ContentType 'application/json' `
  -Body $body
```

### Reverse proxy usage

- Allowed methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
- Headers: Hop-by-hop headers (Connection, TE, etc.) are stripped; Host header is set by the proxy.
- Path joining: `/proxy/{id}/{path}` maps to `http://127.0.0.1:<host_port>/{path}`

Examples:

```bash
# GET with query string
curl "http://127.0.0.1:8000/proxy/<container-id>/api/items?page=1&limit=20"

# POST JSON body to container via proxy
curl -X POST \
  "http://127.0.0.1:8000/proxy/<container-id>/api/items" \
  -H 'content-type: application/json' \
  -d '{"name":"demo"}'
```

### Logs endpoint

- GET `/containers/{id}/logs?tail=200&follow=false`
- `tail`: number of lines from the end (optional)
- `follow`: if true, streams logs (text/plain)

```bash
# Last 100 lines
curl "http://127.0.0.1:8000/containers/<container-id>/logs?tail=100"

# Stream logs (press Ctrl+C to stop)
curl -N "http://127.0.0.1:8000/containers/<container-id>/logs?follow=true&tail=100"
```

### Exec endpoint

- POST `/containers/{id}/exec`

Request:

```json
{
  "command": ["ls", "-la", "/"],
  "workdir": "/",
  "env": {"DEMO": "1"},
  "tty": false
}
```

Response:

```json
{
  "id": "<container-id>",
  "exit_code": 0,
  "stdout": "...",
  "stderr": null
}
```

PowerShell tip: Arrays are easy with `ConvertTo-Json`. If you prefer a single string command, the API accepts that too, e.g. `"command": "ls -la /"`.

## Error handling

- 400 Bad Request — invalid parameters, image not found, port conflicts, invalid volume format
- 404 Not Found — container not found
- 500 Internal Server Error — unexpected Docker/engine error
- 502 Bad Gateway — upstream (proxied container) request failed
- 504 Gateway Timeout — readiness check timed out when `wait_ready=true`

Common causes:

- Docker is not running or not reachable (start Docker Desktop)
- Image requires authentication (log into registry in Docker Desktop or CLI)
- Host port already in use (choose another port or set `host_port: 0`)
- Volume path doesn’t exist or is not shared with Docker on Windows

## Troubleshooting

- Windows volume bind: ensure your drive is shared in Docker Desktop Settings → Resources → File Sharing.
- WSL2 networking: mapped ports are reachable from Windows at 127.0.0.1 by default.
- Private registries: `docker login` with the same daemon this API uses.
- Slow pull: large images over slow networks can delay `/images/pull` and `/containers/run`.
- Health path wrong: if `wait_ready=true` and you get 504, open the upstream URL from `/proxy/{id}` and verify the `health_path`.

## Windows & Docker Desktop tips

- Ensure Docker Desktop is running and the engine is set to expose localhost ports
- If you run Docker in WSL2, published ports are also reachable from Windows at 127.0.0.1

## Develop this API

```powershell
cd dockAPI
. .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/docs>.

## License

MIT
