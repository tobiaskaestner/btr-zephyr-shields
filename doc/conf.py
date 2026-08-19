"""Sphinx configuration for the btr-shields rigs documentation."""

from __future__ import annotations

import os
import sys

# autodoc IMPORTS the expander to read its docstrings, so scripts/ (the
# parent of the `rigc` package) has to be importable. Every rigc module
# imports cleanly with no Zephyr tree present and no ZEPHYR_BASE set --
# the `devicetree` imports are all deferred into function bodies
# (dtsio.get_dtlib and friends) -- so a docs build needs nothing but the
# Sphinx packages. If that ever stops being true, the symptom is an
# autodoc import error under -W, not a silently empty page.
sys.path.insert(0, os.path.abspath(os.path.join("..", "scripts")))

project = "btr-shields"
author = "Tobias Kaestner"
copyright = "2026, Tobias Kaestner"

# btr-shields is a Zephyr module, not a Python distribution -- there is no
# installed package to read a version from. The docs track the tree they
# live in, so the version is the tree's own.
release = "0.0.0"
version = "0.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.graphviz",
    "sphinx_rtd_dark_mode",
]

# The API reference (doc/reference/api/) is one `automodule` per rigc
# module and nothing else -- these options are what make that enough, so
# a page never repeats what the source already says.
#
# undoc-members is ON deliberately: a reference is complete or it
# misleads, and the dataclasses carrying this project's vocabulary
# (model.py) document their fields in trailing comments that autodoc
# cannot see. Without it those fields would silently vanish from the
# rendered class.
#
# private-members is OFF, equally deliberately: the API reference
# describes the surface one module offers another. A private helper is
# documented where it lives, in the source, often at more length than
# anything public here.
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "member-order": "bysource",
}

# sphinx_rtd_dark_mode: start in light mode, toggle in the sidebar
default_dark_mode = False

graphviz_output_format = "svg"

intersphinx_mapping = {
    "zephyr": ("https://docs.zephyrproject.org/latest/", None),
}

# Cross-project references are resolved at build time against a live
# docs.zephyrproject.org. A build without network access must not fail on
# that alone, so intersphinx misses are warnings, not errors -- every
# reference INSIDE this tree still fails the build under -W.
intersphinx_disabled_reftypes = ["*"]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "logo_only": False,
    "navigation_depth": 3,
}

# Devicetree blocks name the "devicetree" Pygments lexer explicitly. The
# default stays "none" so a block that names no language is never guessed
# at -- a wrong guess is a -W build failure, not a cosmetic problem.
highlight_language = "none"
