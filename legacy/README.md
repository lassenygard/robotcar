# Recovered references — do not run on the vehicle

These are source-only snapshots recovered from the two Pis on 2026-10-06.
They preserve the latest local work, which was absent from the GitHub main branch.
Models, virtual environments, home images, logs, private maps and credentials are excluded.

- `pi4-2026-01`: `/home/pi/motor_controller` on the motor Pi.
- `pi5-2026-01`: `/home/pi/robotcarClaude` on the camera/LiDAR Pi.

The old scripts may initialise GPIO on import, drive without a bounded lease,
accept unauthenticated commands, or report simulated hardware as working.
They are retained only as historical references. Use the `robotcar` package and
the service units in `deploy/` for the deployed runtime.

Other root-level Python modules predate these snapshots and remain in git history
and the working tree for reference; none are imported by the deployed services.

The old static Flask session secret is replaced by an explicit inactive placeholder in this snapshot.
Trailing whitespace and line endings were normalised without changing the archived control logic.
