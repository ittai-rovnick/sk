from dataclasses import dataclass, field
from typing import List


@dataclass
class RequestContext:
    ms_object_id: str
    ms_group_ids: List[str]
    user_id: str
    is_superadmin: bool = False
