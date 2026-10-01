# Ghost Trail Switchable UI

The cinematic experience now uses a persistent top navigation inspired by the supplied reference video: selecting a mode transforms the central stage instead of scrolling through empty sections.

Modes:
- Live — camera surveillance stage
- Environment — interactive spatial room stage
- Room Scan — scan/exclusive-camera stage
- Tracking — cross-camera global identity graph
- Analytics — operational telemetry stage

The transition is implemented with Framer Motion `AnimatePresence`, so the stage, title, metadata, and background transform together.

The switchable command interface is integrated directly into the main dashboard. No `/experience` route is required.
