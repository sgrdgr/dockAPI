from __future__ import annotations

import asyncio
from typing import List, Optional
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, StreamingResponse

from .docker_service import DockerService
from .models import (
    PullImageRequest,
    ImageInfo,
    RunContainerRequest,
    ContainerInfo,
    StartStopResponse,
    ProxyInfo,
    ExecRequest,
    ExecResponse,
)

app = FastAPI(title="dockAPI", version="0.1.0")

# CORS for convenience during dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

docker_service = DockerService()


@app.get("/healthz")
async def healthz() -> dict:
    try:
        docker_service.ping()
        return {"ok": True}
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(e))


# Images
@app.get("/images", response_model=List[ImageInfo])
async def list_images() -> List[ImageInfo]:
    images = docker_service.list_images()
    return [ImageInfo(**i) for i in images]


@app.post("/images/pull")
async def pull_image(payload: PullImageRequest) -> dict:
    try:
        image_id = docker_service.pull_image(payload.image)
        return {"id": image_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Containers
@app.get("/containers", response_model=List[ContainerInfo])
async def list_containers() -> List[ContainerInfo]:
    cs = docker_service.list_containers(all_=True)
    return [ContainerInfo(**c) for c in cs]


@app.post("/containers/run", response_model=ContainerInfo)
async def run_container(payload: RunContainerRequest) -> ContainerInfo:
    try:
        cid, host_port = docker_service.run_container(
            image=payload.image,
            container_port=payload.container_port,
            host_port=payload.host_port,
            name=payload.name,
            env=payload.env,
            command=payload.command,
            auto_remove=payload.auto_remove,
            detach=payload.detach,
            restart_policy=payload.restart_policy,
            volumes=payload.volumes,
            network=payload.network,
        )

        # small wait to ensure network ready
        await asyncio.sleep(0.3)
        if payload.wait_ready and payload.health_path:
            await _wait_ready(
                host_port, payload.health_path, payload.wait_timeout
            )
        info = docker_service.container_info(cid)
        return ContainerInfo(**info)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/containers/{container_id}", response_model=ContainerInfo)
async def get_container(container_id: str) -> ContainerInfo:
    try:
        info = docker_service.container_info(container_id)
        return ContainerInfo(**info)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/containers/{container_id}/stop", response_model=StartStopResponse)
async def stop_container(container_id: str) -> StartStopResponse:
    try:
        docker_service.stop(container_id)
        return StartStopResponse(id=container_id, status="stopped")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/containers/{container_id}/start", response_model=StartStopResponse)
async def start_container(container_id: str) -> StartStopResponse:
    try:
        docker_service.start(container_id)
        return StartStopResponse(id=container_id, status="running")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/containers/{container_id}")
async def delete_container(container_id: str, force: bool = False) -> dict:
    try:
        docker_service.remove(container_id, force=force)
        return {"id": container_id, "removed": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/containers/{container_id}/logs")
async def container_logs(
    container_id: str, tail: Optional[int] = 200, follow: bool = False
):
    try:
        if follow:
            gen = docker_service.get_logs(container_id, tail=tail, follow=True)

            async def streamer():
                # Bridge sync generator from docker API to async without blocking the event loop
                iterator = iter(gen)  # type: ignore
                while True:
                    try:
                        chunk = await asyncio.to_thread(next, iterator)
                    except StopIteration:
                        break
                    data = (
                        chunk
                        if isinstance(chunk, (bytes, bytearray))
                        else bytes(chunk)
                    )
                    yield data

            return StreamingResponse(streamer(), media_type="text/plain")
        else:
            data = docker_service.get_logs(
                container_id, tail=tail, follow=False
            )
            if isinstance(data, (bytes, bytearray)):
                return Response(content=data, media_type="text/plain")
            return Response(
                content=b"".join(list(data)), media_type="text/plain"
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/containers/{container_id}/exec", response_model=ExecResponse)
async def exec_in_container(
    container_id: str, payload: ExecRequest
) -> ExecResponse:
    try:
        code, out, err = docker_service.exec(
            container_id,
            payload.command,
            workdir=payload.workdir,
            env=payload.env,
            tty=payload.tty,
        )
        return ExecResponse(
            id=container_id, exit_code=code, stdout=out, stderr=err
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Reverse proxy to container's published host port
_ALLOWED_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
]


def _filter_headers(headers: httpx.Headers) -> dict:
    hop_by_hop = {
        "connection",
        "proxy-connection",
        "keep-alive",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "host",
    }
    return {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}


@app.get("/proxy/{container_id}", response_model=ProxyInfo)
async def proxy_info(container_id: str) -> ProxyInfo:
    info = docker_service.container_info(container_id)
    host_port = info.get("host_port")
    if not host_port:
        raise HTTPException(
            status_code=400, detail="Container has no published port"
        )
    return ProxyInfo(
        container_id=container_id,
        upstream=f"http://127.0.0.1:{host_port}",
    )


@app.api_route("/proxy/{container_id}/{path:path}", methods=_ALLOWED_METHODS)
async def proxy(container_id: str, path: str, request: Request) -> Response:
    info = docker_service.container_info(container_id)
    host_port = info.get("host_port")
    if not host_port:
        raise HTTPException(
            status_code=400, detail="Container has no published port"
        )

    upstream = f"http://127.0.0.1:{host_port}/"  # ensure trailing slash
    url = urljoin(upstream, path)

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        try:
            req_headers = _filter_headers(request.headers)
            body = await request.body()
            method = request.method.upper()

            upstream_resp = await client.request(
                method,
                url,
                params=request.query_params,
                content=body,
                headers=req_headers,
            )

        except httpx.HTTPError as e:
            return JSONResponse(status_code=502, content={"detail": str(e)})

    # Build response
    resp_headers = _filter_headers(upstream_resp.headers)

    # Stream if possible
    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        media_type=upstream_resp.headers.get("content-type"),
    )


# Entrypoint for uvicorn: `uvicorn app.main:app --reload`


async def _wait_ready(
    host_port: int, health_path: str, timeout_sec: int
) -> None:
    """Poll the container through localhost until it returns 200 or timeout."""
    base = f"http://127.0.0.1:{host_port}"
    url = urljoin(base + "/", health_path.lstrip("/"))
    deadline = asyncio.get_event_loop().time() + timeout_sec
    async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
        while True:
            try:
                r = await client.get(url)
                if 200 <= r.status_code < 300:
                    return
            except Exception:
                pass
            if asyncio.get_event_loop().time() >= deadline:
                raise HTTPException(
                    status_code=504,
                    detail="Container did not become ready within timeout",
                )
            await asyncio.sleep(0.5)
