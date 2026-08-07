Building the documentation
============================

The documentation dependencies are not part of the workspace Python
environment a Zephyr build uses — ``btr-shields`` is a Zephyr module, not
a Python distribution, so there is nothing to ``pip install -e``. Use a
throwaway virtual environment.

Install the tooling
---------------------

.. code-block:: console

   $ python3 -m venv .docvenv
   $ .docvenv/bin/pip install sphinx sphinx-rtd-theme sphinx-rtd-dark-mode

Build once
------------

Build the HTML docs with warnings treated as errors — the same command
that gates a documentation change:

.. code-block:: console

   $ .docvenv/bin/sphinx-build -W --keep-going -b html doc doc/_build/html

``-W`` is not optional. A broken ``:doc:`` link, an unresolved ``:term:``,
or a page missing from a toctree is a build failure, which is what keeps
:doc:`../explanation/documentation-guidelines`'s "no orphan pages, no
dangling references" rule true rather than aspirational.

Then open ``doc/_build/html/index.html``.

Live preview while editing
----------------------------

.. code-block:: console

   $ .docvenv/bin/pip install sphinx-autobuild
   $ .docvenv/bin/sphinx-autobuild doc doc/_build/html

Then open the URL it prints (typically ``http://127.0.0.1:8000``).

Checking cross-project links
------------------------------

References into the Zephyr documentation resolve through intersphinx
against a live ``docs.zephyrproject.org``. Those are deliberately not
fatal, so the build still works offline; references *within* this tree
always are.
