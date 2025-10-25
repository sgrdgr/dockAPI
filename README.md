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
- GET `/proxy/{id}` — Show the upstream URL for the container
- ANY `/proxy/{id}/{path}` — Reverse-proxy to the container's published host port

All containers created by this API are labeled with `dockapi.managed=true`.

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
}
```

Notes:

- If `host_port` is omitted or set to 0, the API auto-assigns a free localhost port.
- Only the specified `container_port` (TCP) is published.
- The reverse proxy routes requests to `http://127.0.0.1:<host_port>` using the same method, headers (minus hop-by-hop), query, and body.

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