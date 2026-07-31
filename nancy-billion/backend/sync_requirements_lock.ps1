# Regenerates requirements-lock.txt from whatever's actually installed right
# now, so it never drifts from reality. Run this after installing, upgrading,
# or removing any backend Python package:
#
#   powershell -File sync_requirements_lock.ps1
#
# requirements.txt (the curated, commented file with install instructions
# and index URLs) is what you edit by hand when adding a genuinely new direct
# dependency. This file is the auto-generated exact snapshot -- never hand-edit it.
#
# Targets the backend CONTAINER's pip, not the host's -- confirmed live this
# was previously generated against a host Windows Python environment, which
# both missed real Linux-only packages the container actually runs (e.g.
# playwright's Linux deps) and included Windows-only ones the container
# never installs at all (pywin32, comtypes -- conditional on sys_platform ==
# "win32" in requirements.txt). The container is the real deployment target.

$header = @'
# AUTO-GENERATED -- do not hand-edit. This is the exact, complete, working
# dependency closure (direct + transitive) confirmed running on this machine,
# produced by `pip freeze`. requirements.txt is the curated, commented file
# to actually run `pip install -r` against; this file exists so "what exact
# version of everything is Nancy actually running on" is always answerable
# without re-deriving it from imports.
#
# Regenerate after installing/upgrading anything (inside the backend
# container, which is the real deployment target -- a host-machine pip
# freeze would include unrelated Windows-only packages and miss Linux-only
# ones):
#   docker compose exec backend pip freeze > backend/requirements-lock.txt
'@

$header | Out-File -FilePath requirements-lock.txt -Encoding utf8
docker compose exec backend pip freeze | Out-File -FilePath requirements-lock.txt -Append -Encoding utf8

Write-Host "requirements-lock.txt regenerated from the running backend container."
