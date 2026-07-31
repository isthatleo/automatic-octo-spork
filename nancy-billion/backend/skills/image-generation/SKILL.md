---
name: image-generation
description: Generate a real image from a text description via the generate_image tool -- posted straight to the shared canvas so the user sees it immediately.
trigger_keywords:
  - generate an image
  - create a picture
  - draw me
  - make an illustration
  - image of
---

Nancy has a real `generate_image` tool (`media_tools.py`) -- dispatches to
whichever image-generation provider is actually configured (fal.ai,
DeepInfra), no hardcoded vendor. Read-only in the sense that it doesn't
touch the filesystem or run code, so no approval gate.

- If no provider is configured (`FAL_API_KEY`/`DEEPINFRA_API_KEY` both
  unset), the tool returns a real error -- say so plainly rather than
  describing an image that wasn't actually made.
- On success the image is posted to the shared canvas automatically AND
  returned to you directly, so you can describe what was actually produced
  rather than assuming the prompt was followed exactly.
- Write a clear, visual prompt -- describe the scene, not the request
  ("a red fox sitting in snow at dusk, watercolor style", not "make an
  image for me please").
