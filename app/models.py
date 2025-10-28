from typing import Optional, Dict, List, Literal
from pydantic import BaseModel, Field
from pydantic import field_validator


class PullImageRequest(BaseModel):
    image: str = Field(
        ..., description="Docker image reference, e.g. 'nginx:latest'"
    )


class ImageInfo(BaseModel):
    id: str
    repo_tags: List[str] = []
    size: int = 0


class RunContainerRequest(BaseModel):
    image: str = Field(
        ..., description="Docker image reference, e.g. 'nginx:latest'"
    )
    container_port: int = Field(
        ..., description="Container port to publish (TCP)"
    )
    host_port: Optional[int] = Field(
        None,
        description=(
            "Host port to bind to; if omitted a random free port "
            "will be chosen"
        ),
    )
    name: Optional[str] = Field(
        None, description="Optional friendly container name"
    )
    env: Optional[Dict[str, str]] = Field(
        default=None,
        description="Environment variables to pass to the container",
    )
    command: Optional[List[str] | str] = Field(
        default=None,
        description="Override the default command/entrypoint",
    )
    auto_remove: bool = Field(
        default=True,
        description="Automatically remove container when stopped",
    )
    detach: bool = Field(
        default=True, description="Run container in detached mode"
    )
    restart_policy: Optional[
        Literal['no', 'on-failure', 'always', 'unless-stopped']
    ] = Field(default='unless-stopped')
    volumes: Optional[List[str]] = Field(
        default=None,
        description=(
            "List of volume bind strings in the form "
            "'host_path:container_path[:ro|rw]'"
        ),
    )
    network: Optional[str] = Field(
        default=None, description="Docker network to attach the container to"
    )
    wait_ready: bool = Field(
        default=False,
        description=(
            "If true, wait until health_path returns 200 on the host port"
        ),
    )
    health_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to probe on the container app (e.g., '/health'). "
            "Only used when wait_ready is true."
        ),
    )
    wait_timeout: int = Field(
        default=30,
        description="Seconds to wait for readiness when wait_ready is true",
    )

    @field_validator("image")
    @classmethod
    def validate_image(cls, v: str) -> str:
        if ":" not in v:
            # default tag
            return f"{v}:latest"
        return v


class ContainerInfo(BaseModel):
    id: str
    name: Optional[str]
    image: str
    status: str
    labels: Dict[str, str] = {}
    host_port: Optional[int] = None
    container_port: Optional[int] = None


class StartStopResponse(BaseModel):
    id: str
    status: str


class ProxyInfo(BaseModel):
    container_id: str
    upstream: str


class ExecRequest(BaseModel):
    command: List[str] | str = Field(
        ..., description="Command to run inside the container"
    )
    workdir: Optional[str] = Field(
        default=None, description="Working directory inside the container"
    )
    env: Optional[Dict[str, str]] = Field(
        default=None, description="Environment vars for the exec session"
    )
    tty: bool = Field(default=False, description="Allocate a TTY for exec")


class ExecResponse(BaseModel):
    id: str
    exit_code: int
    stdout: Optional[str] = None
    stderr: Optional[str] = None
