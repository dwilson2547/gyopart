"""The fix suggester (docs/matching-v2-design.md §3.4): one model call per group, everything else in code.

For each kind of group: gather the evidence and the candidates (each already previewed) into a bundle, render it
as chat messages for a local model with a versioned prompt, and check the model's JSON reply before anything is
filed. The model only ever picks among candidates the code put in front of it.
"""
