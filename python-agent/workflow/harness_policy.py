"""Freeze feature switches on new runs; legacy checkpoints keep legacy behavior."""
import os

FEATURES = ('acceptance', 'context', 'editing', 'events', 'executor', 'instructions')


def snapshot_policy():
    return {name: os.getenv('HARNESS_' + name.upper() + '_ENABLED', 'false').lower() == 'true'
            for name in FEATURES}


def enabled(state, feature):
    return (state.get('harness_policy') or {}).get(feature) is True
