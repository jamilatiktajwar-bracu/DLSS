# DLSS Fork Upgrade Roadmap

> This repository is a fork/derivative of Likely7/Veyra-NRVideo. Preserve upstream attribution and the GPL-3.0 license. This document tracks proposed improvements for the DLSS fork; it is not a claim that these features are implemented or tested.

## Guiding principles

- Keep upstream functionality intact; develop changes on feature branches and review them before merging.
- Prefer small, testable changes with measurable behavior.
- Do not claim performance gains without reproducible measurements on named hardware and settings.
- Protect user settings and media; never silently modify drivers, system components, or credentials.
- Keep third-party notices, source provenance, and license obligations current.

## Upgrade tracks

### 0 — Baseline and build reproducibility
- Document supported Windows/Qt/CMake/compiler/dependency versions and prerequisites.
- Add a fork-specific build and troubleshooting guide.
- Establish CI checks for whitespace, changed-file validation, and available static checks; full Windows/GPU build remains a separate hardware/dependency-aware job.
- Record baseline launch, playback, capture, and render metrics before optimizations.

### 1 — UX and onboarding
- First-run setup checklist: GPU/backend detection, media/capture source, recommended preset, and a clear skip path.
- Presets with explicit explanations (Quality, Balanced, Low-latency) that only change documented settings.
- Improve settings search and make reset-to-default per section, with confirmation and restore capability.
- Accessibility pass: keyboard navigation, focus visibility, readable contrast, and scalable UI.

### 2 — Diagnostics and stability
- A user-exportable diagnostics report with redaction of usernames, local paths, device identifiers, and tokens by default.
- Clear GPU/backend capability and fallback messages.
- Crash/recovery guidance and bounded log rotation; never upload diagnostics without explicit user action.
- Expand regression tests around source switching, seek, HDR/SDR transitions, capture loss, and device reset.

### 3 — Performance and image quality
- Add a reproducible benchmark mode that reports frame-time percentiles, dropped/duplicated frames, queue depth, and selected pipeline settings.
- Profile CPU/GPU bottlenecks before changing scheduling, memory, or shader code.
- Test image-quality changes against reference clips and preserve color-space/transfer-function correctness.
- Avoid CPU readbacks, blocking waits, and unbounded queues in real-time paths.

### 4 — Packaging and release quality
- Automated version/build metadata and a release checklist.
- Verify packaged files against manifests and checksums.
- Keep optional components clearly separated; document source, license, and installation/update steps.
- Provide rollback instructions for user-facing updates.

## Definition of done

A feature is ready to propose for merge only when: its scope is documented; the change is reviewed for compatibility and license impact; applicable tests/checks are run and their actual results recorded; failure paths are considered; and the user-facing documentation is updated. Untested GPU/device-specific behavior must be labelled unverified.

## First planned deliverable

Start with the reproducible baseline and benchmark/diagnostics design. Then implement a narrowly scoped, low-risk UX or diagnostics improvement based on repository inspection. Do not bundle unrelated refactors.
