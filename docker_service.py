from __future__ import annotations

import socket
from typing import Dict, Optional, List, Tuple

import docker
from docker import DockerClient
from docker.models.containers import Container

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
    ) -> Tuple[str, int]:
        if host_port is None:
            host_port = self._reserve_port()

        ports = {f"{container_port}/tcp": host_port}
        labels = {MANAGED_LABEL: "true", PORT_LABEL: str(container_port)}
        if name:
            labels[NAME_LABEL] = name

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
