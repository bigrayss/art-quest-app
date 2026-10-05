"""ArtQuest — Stage 1 PC prototype of the AI art-education game.

Core loop: Quest -> Intent -> Draw -> stroke/event logging -> 9-dim score -> AI
text feedback -> one revision -> save before/after.

The process logs (strokes.jsonl / events.jsonl) are the primary data; canvas
screenshots are an aid. See DESIGN.md "数据结构" for the on-disk schema.
"""
__version__ = "0.2.0"
