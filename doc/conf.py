"""Sphinx configuration for the btr-shields rigs documentation."""

from __future__ import annotations

project = "btr-shields"
author = "Tobias Kaestner"
copyright = "2026, Tobias Kaestner"

# btr-shields is a Zephyr module, not a Python distribution -- there is no
# installed package to read a version from. The docs track the tree they
# live in, so the version is the tree's own.
release = "0.0.0"
version = "0.0"

extensions = [
    "sphinx.ext.intersphinx",
    "sphinx.ext.graphviz",
    "sphinx_rtd_dark_mode",
]

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
