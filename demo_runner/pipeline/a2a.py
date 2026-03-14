"""Minimal A2A (Agent-to-Agent) protocol types and in-memory task store."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

TaskState = Literal["submitted", "working", "completed", "failed"]


@dataclass
class Task:
    id: str
    state: TaskState
    input: dict
    output: dict | None = None
    error: str | None = None


@dataclass
class AgentCard:
    name: str
    description: str
    url: str
    capabilities: list[str] = field(default_factory=list)


# One TaskStore per worker name, keyed by task_id
# Cleared at the start of each pipeline run
task_stores: dict[str, dict[str, Task]] = {
    "ocr": {},
    "json": {},
    "browser": {},
}


def create_task(worker: str, input_data: dict) -> Task:
    task = Task(id=str(uuid.uuid4()), state="submitted", input=input_data)
    task_stores[worker][task.id] = task
    return task


def get_task(worker: str, task_id: str) -> Task | None:
    return task_stores[worker].get(task_id)


def clear_all() -> None:
    for store in task_stores.values():
        store.clear()
