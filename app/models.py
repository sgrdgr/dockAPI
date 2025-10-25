from typing import Optional, Dict, List, Literal
from pydantic import BaseModel, Field, validator


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

    @validator("image")
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
