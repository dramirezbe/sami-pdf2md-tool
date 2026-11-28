# Agent instructions

## Release versions

The root `VERSION` file is the source for the SAMI release version. The CLI and desktop app share that version. Release tags use the format `v<VERSION>`, and a pushed tag starts the release workflow.

When preparing a release:

1. Update `VERSION` to the requested stable version.
2. Run `python3 scripts/sync_version.py --sync` (on Windows, `python scripts/sync_version.py --sync`). Review and commit the synchronized metadata and installer templates together with `VERSION`. Do not edit their version values independently.
3. Validate the release candidate and merge it into `main`. On the intended release commit, run `python3 scripts/tag_release.py` to check the clean working tree and synchronized metadata and create the annotated tag.
4. Push the resulting tag when the release is authorized. Follow [docs/releasing.md](docs/releasing.md) to verify the release artifacts.

The release workflow checks that the tag matches the committed `VERSION` and that derived metadata is synchronized. It calculates and stamps the wheel checksum during the build.
