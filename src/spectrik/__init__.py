"""spectrik - A generic specification and blueprint pattern for declarative configuration-as-code tools."""

from .blueprints import Blueprint as Blueprint
from .context import Context as Context
from .projects import Project as Project
from .spec import Specification as Specification
from .spec import spec as spec
from .specop import Absent as Absent
from .specop import Ensure as Ensure
from .specop import Present as Present
from .specop import SpecOp as SpecOp
from .workspace import Workspace as Workspace
