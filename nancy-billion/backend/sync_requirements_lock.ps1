# Regenerates requirements-lock.txt from whatever's actually installed right
# now, so it never drifts from reality. Run this after installing, upgrading,
# or removing any backend Python package:
#
#   powershell -File sync_requirements_lock.ps1
#
# requirements.txt (the curated, commented file with install instructions
# and index URLs) is what you edit by hand when adding a genuinely new direct
# dependency. This file is the auto-generated exact snapshot -- never hand-edit it.

$header = @'
# AUTO-GENERATED -- do not hand-edit. This is the exact, complete, working
# dependency closure (direct + transitive) confirmed running on this machine,
# produced by `pip freeze`. requirements.txt is the curated, commented file
# to actually run `pip install -r` against; this file exists so "what exact
# version of everything is Nancy actually running on" is always answerable
# without re-deriving it from imports.
#
# Regenerate after installing/upgrading anything:
#   powershell -File sync_requirements_lock.ps1
# (or just: pip freeze > requirements-lock.txt)
'@

$header | Out-File -FilePath requirements-lock.txt -Encoding utf8
pip freeze | Out-File -FilePath requirements-lock.txt -Append -Encoding utf8

Write-Host "requirements-lock.txt regenerated from the current environment."
