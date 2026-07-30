"""rigc's own test tree. Layers are DIRECTORIES, not markers:
tests/unit/ (subprocess-free, value-shaped contracts) and
tests/integration/ (the frozen suite, moved here at cutover -- rigc's
own integration coverage). Package-shaped (__init__.py) so pytest and
mypy both derive unique, collision-free module names."""
