# SAMI Desktop releases

The Git tag selects a release. The root `VERSION` file records the matching SAMI version in the commit. The CLI and desktop release use the same version.

## Prepare a release

1. Change only `VERSION` to the intended stable version, such as `0.4.3`.
2. Run `python3 scripts/sync_version.py --sync` (on Windows, `python scripts/sync_version.py --sync`). This updates the npm metadata, runtime manifest, and installer templates. Review and commit the resulting changes.
3. Validate the candidate and merge it into `main`. On the intended release commit, run `python3 scripts/tag_release.py`. This checks that the working tree is clean and the derived version metadata is synchronized before creating the annotated tag. Push the tag with the command it prints.

The tag workflow independently rejects a tag that does not match the committed `VERSION`, or a commit with out-of-sync derived metadata. A tag pushed directly with Git can exist even when validation fails, but it will not produce a release. The release workflow calculates the wheel checksum when building and stamps it into the installer assets and runtime manifest.

## Validate a candidate

From `ui/`, run `npm ci`, `npm test`, `npm run build`, and `npm run test:desktop` with Node.js 24. On headless Linux, run the desktop test under `xvfb-run -a`. With `SAMI_TEST_REAL_CLI_HOME` pointing at a ready CLI installation, the desktop test runs its batch against that CLI.

The release workflow builds and smoke-tests the Windows x64 installer and Linux x64 AppImage, and builds the Linux x64 deb package. It creates a draft release with these packages, installers, the Python wheel, runtime manifest, and checksums. Verify the draft assets and platform installation behavior before publishing it.
