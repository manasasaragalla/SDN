# ADR-003: `mininet/` renamed to `testbed/`

The brief's suggested repository layout names the testbed folder
`mininet/` (topology/traffic/experiments). This collides directly with
the third-party `mininet` Python package this project depends on for
`from mininet.net import Mininet`, `from mininet.node import ...`, etc.

Verified concretely: with the project root on `PYTHONPATH` (required for
every `backend.*` import in this codebase), `import mininet.topology.diamond`
resolves to the *installed* `mininet` package first and fails with
`ModuleNotFoundError: No module named 'mininet.topology'`, because the
real package has no such submodule -- Python doesn't merge our local
`mininet/` directory with the installed package's namespace the way one
might hope.

Renamed to `testbed/` (same internal structure: `topology/`, `traffic/`,
`experiments/`) to remove the collision entirely rather than work around
it with `sys.path` tricks or import-time hacks, which would be fragile
and confusing for anyone reading the code later. All references (README,
scripts, docs) use `testbed/` from this point on.
