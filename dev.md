# Development

The project is managed with [uv](https://docs.astral.sh/uv/). It needs Python 3.14.2 or newer,
the same as Home Assistant 2026.10.

## Setup

```bash
uv sync
```

This creates `.venv/` with Home Assistant, `pytest-homeassistant-custom-component` and `ruff`.

## Tests

```bash
uv run pytest
```

The tests in `tests/` use `pytest-homeassistant-custom-component`, which runs a real Home Assistant
instance in the test process. The `setup_ec` fixture in `tests/conftest.py` sets up Entity
Controllers and moves HA's clock forward with `freezer` and `async_fire_time_changed`, so the tests
don't actually wait for the startup delay or timers. The `calls` fixture fakes `turn_on`/`turn_off`
and applies the new state with the caller's context, the way a real device would.

Known bugs are pinned with `@pytest.mark.xfail(strict=True)`, so fixing one makes its test fail
until the marker is removed.

Each test module must import from `custom_components.entity_controller` at the top. Otherwise, the
plugin's own `testing_config/custom_components` package hides ours and HA reports
"Integration not found".

`tests/legacy/` has the original test suite. It targets a 2018 Home Assistant and is not run. It
stays as a reference for porting the tests.

## Lint

```bash
uv run ruff check custom_components tests scripts
uv run ruff format custom_components tests scripts
```

## Validation

CI also runs hassfest and the HACS validation. To run hassfest locally:

```bash
docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest
```

## Releasing

The version lives in two places, which must match: `pyproject.toml` and
`custom_components/entity_controller/manifest.json`.

1. Bump the version in both files.
2. Add an entry to `CHANGELOG.md`.
3. Commit, then tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin master --tags
   ```

The `Release` workflow checks the tag against both files, builds `entity_controller.zip` and
publishes a GitHub Release with it. HACS installs from that zip.
