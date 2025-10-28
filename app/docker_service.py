from __future__ import annotations

import socket
from typing import Dict, Optional, List, Tuple, Generator

import docker
from docker import DockerClient
from docker.models.containers import Container
# intentionally no specific docker.errors import to avoid unused warnings

MANAGED_LABEL = "dockapi.managed"
NAME_LABEL = "dockapi.name"
PORT_LABEL = "dockapi.container_port"


class DockerService:
    def __init__(self) -> None:
        self.client: DockerClient = docker.from_env()

    def ping(self) -> bool:
        self.client.ping()
        return True

    # Images
    def list_images(self) -> List[Dict]:
        images = self.client.images.list()
        result: List[Dict] = []
        for img in images:
            result.append(
                {
                    "id": img.short_id.replace("sha256:", ""),
                    "repo_tags": img.tags or [],
                    "size": getattr(img, "attrs", {}).get("Size", 0),
                }
            )
        return result

    def pull_image(self, image: str) -> str:
        img = self.client.images.pull(image)
        return img.id

    # Containers
    def _find_container(self, container_id_or_name: str) -> Container:
        return self.client.containers.get(container_id_or_name)

    def _reserve_port(self) -> int:
        # Bind to port 0 to let OS choose a free port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def run_container(
        self,
        *,
        image: str,
        container_port: int,
        host_port: Optional[int] = None,
        name: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        command: Optional[List[str] | str] = None,
        auto_remove: bool = True,
        detach: bool = True,
        restart_policy: Optional[str] = "unless-stopped",
        volumes: Optional[List[str]] = None,
        network: Optional[str] = None,
    ) -> Tuple[str, int]:
        if host_port is None or int(host_port) == 0:
            host_port = self._reserve_port()

        ports = {f"{container_port}/tcp": host_port}
        labels = {MANAGED_LABEL: "true", PORT_LABEL: str(container_port)}
        if name:
            labels[NAME_LABEL] = name

        vol_spec: Optional[Dict[str, Dict[str, str]]]
        vol_spec = self._parse_volumes(volumes) if volumes else None

        container: Container = self.client.containers.run(
            image=image,
            command=command,
            environment=env or {},
            name=name,
            ports=ports,
            detach=detach,
            auto_remove=auto_remove,
            labels=labels,
            restart_policy=(
                {"Name": restart_policy} if restart_policy else None
            ),
            volumes=vol_spec,
            network=network,
        )
        return container.id, int(host_port)

    def list_containers(self, all_: bool = False) -> List[Dict]:
        containers = self.client.containers.list(
            all=all_, filters={"label": MANAGED_LABEL}
        )
        result: List[Dict] = []
        for c in containers:
            info = self._container_info(c)
            result.append(info)
        return result

    def container_info(self, container_id: str) -> Dict:
        c = self._find_container(container_id)
        return self._container_info(c)

    def _container_info(self, c: Container) -> Dict:
        c.reload()
        attrs = c.attrs
        container_port = None
        try:
            container_port = (
                int(c.labels.get(PORT_LABEL))
                if c.labels.get(PORT_LABEL)
                else None
            )
        except Exception:
            container_port = None
        host_port = None
        if container_port:
            key = f"{container_port}/tcp"
            ports_map = attrs.get("NetworkSettings", {}).get("Ports", {})
            bindings = ports_map.get(key)
            if bindings:
                host_port = int(bindings[0].get("HostPort"))
        return {
            "id": c.id,
            "name": c.name,
            "image": attrs.get("Config", {}).get("Image"),
            "status": c.status,
            "labels": c.labels or {},
            "host_port": host_port,
            "container_port": container_port,
        }

    def start(self, container_id: str) -> None:
        c = self._find_container(container_id)
        c.start()

    def stop(self, container_id: str, timeout: int = 10) -> None:
        c = self._find_container(container_id)
        c.stop(timeout=timeout)

    def remove(self, container_id: str, force: bool = False) -> None:
        c = self._find_container(container_id)
        c.remove(force=force)

    # Helpers
    def _parse_volumes(
        self, volumes: List[str]
    ) -> Dict[str, Dict[str, str]]:
        """
        Convert a list like ["C:/data:/data:ro", "/host/logs:/container/logs"]
        into docker-py volumes dict:
        {
          "C:/data": {"bind": "/data", "mode": "ro"},
          "/host/logs": {"bind": "/container/logs", "mode": "rw"}
        }
        """
        result: Dict[str, Dict[str, str]] = {}
        for item in volumes:
            # Split from the right to better support Windows drive letters like C:\
            parts = item.rsplit(":", maxsplit=2)
            if len(parts) < 2:
                # skip invalid, but keep going
                continue
            if len(parts) == 2:
                host, cont = parts
                mode = "rw"
            else:
                host, cont, mode = parts
            mode = (mode or "rw").lower()
            if mode not in {"ro", "rw"}:
                mode = "rw"
            result[host] = {"bind": cont, "mode": mode}
        return result

    # Logs
    def get_logs(
        self,
        container_id: str,
        *,
        tail: Optional[int] = None,
        follow: bool = False,
    ) -> Generator[bytes, None, None] | bytes:
        c = self._find_container(container_id)
        if follow:
            stream = c.logs(stream=True, tail=tail)

            def _gen() -> Generator[bytes, None, None]:
                for chunk in stream:
                    yield chunk

            return _gen()
        else:
            return c.logs(stream=False, tail=tail)

    # Exec
    def exec(
        self,
        container_id: str,
        command: List[str] | str,
        *,
        workdir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        tty: bool = False,
    ) -> Tuple[int, str, Optional[str]]:
        c = self._find_container(container_id)
        res = c.exec_run(
            cmd=command,
            workdir=workdir,
            environment=env,
            tty=tty,
            demux=True,  # returns (stdout, stderr)
        )
        exit_code = res.exit_code if hasattr(res, "exit_code") else 0
        stdout, stderr = (
            res.output if isinstance(res.output, tuple) else (res.output, None)
        )
        # Ensure str output
        out_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        err_str = stderr.decode("utf-8", errors="replace") if stderr else None
        return exit_code, out_str, err_str
