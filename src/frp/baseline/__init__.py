"""Wan 2.1 I2V single-condition *baseline* contracts and a mock-tested execution boundary.

This subpackage is distinct from the A/B/C/D conditioning ablation (``frp.manifest``,
``frp.planner``, ``frp.results``), whose schema, run ids and invariants are unchanged. It adds a
separately versioned manifest, plan and result contract for one unaltered condition (Experiment
003), a ``BaselineExecutor`` interface, a fail-closed Wan 2.1 executor that talks to an injected
backend, and a lazily loaded upstream backend that is **disabled** in this release.

Importing anything here loads no model, imports no ML or GPU library, opens no network
connection and discovers no checkpoint. Nothing in this package authorises GPU use, a weight
download or the processing of any person's data.
"""
