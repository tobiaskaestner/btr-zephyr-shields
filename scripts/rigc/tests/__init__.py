"""rigc's own test tree. Layers are DIRECTORIES, not markers:
tests/unit/ (subprocess-free, value-shaped contracts) and
tests/integration/ (empty until cutover -- the frozen rigexp suite under
RIG_EXPAND_COMPILE=rigc is rigc's integration coverage). Package-shaped
(__init__.py) so pytest and mypy both derive unique, collision-free
module names alongside the frozen rigexp suite's own top-level ones."""
