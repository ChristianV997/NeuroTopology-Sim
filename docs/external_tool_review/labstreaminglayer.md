# Review: LabStreamingLayer

- admission_status: admitted_optional
- integration_mode: emulate
- review_date: 2026-09-05

## Role
Optional live acquisition inlet for EEG and event markers.

## Evidence
https://labstreaminglayer.org/ and MIT-licensed pylsl.

## Constraints
Tests must not open multicast sockets or require lab hardware. Replay XDF or
in-memory fixtures only. Do not run LSL inside API routes.
