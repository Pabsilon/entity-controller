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

1. Bump the version in both files, then run `uv lock` (the lock file records the version, and CI
   checks it with `uv sync --locked`).
2. Add an entry to `CHANGELOG.md`.
3. Commit, then tag and push. The tag is what publishes the release:
   ```bash
   git tag vX.Y.Z
   git push origin master vX.Y.Z
   ```

The `Release` workflow checks the tag against both files, builds `entity_controller.zip` and
publishes a GitHub Release with it. HACS installs from that zip, so a version without a release
can't be installed.

### Pre-releases

Use a [PEP 440](https://peps.python.org/pep-0440/) pre-release version, such as `10.1.0b1` (tag
`v10.1.0b1`), or `a1`/`rc1`. The workflow publishes those as GitHub pre-releases. HACS only
offers them to users who enable **Show beta versions** for the repository, so everyone else stays
on the latest stable release.

## Config entries

Each Entity Controller is a config entry. `config_flow.py` has the create, options and import
flows, and `entity_controller.py` is the platform that `EntityComponent.async_setup_entry` loads
for our own entries.

- **The options are in the YAML shape.** `entry.options` hold what `ENTITY_SCHEMA` (`config.py`)
  accepts, so one schema and one model serve both. `entry.unique_id` is the slug of the name. The
  title is the display name.
- **The forms are built from `SECTIONS`.** Each form key is unique across sections (night-mode
  fields are prefixed with `night_`), because API clients such as MCP servers flatten the
  sections. Sections are optional, since API clients only send the ones with values. Empty and
  default values aren't saved, which keeps the model's `.get()` fallbacks as the only defaults.
- **YAML is import-only.** `async_setup` starts one import flow per YAML key and raises the
  `deprecated_yaml` issue. The import uses the key as the `unique_id` and saves the options
  through `form_to_options(options_to_form(...))`, so they match what the options form would
  save.
- **Entity IDs are kept.** A YAML EC had no unique_id, so HA generated its entity_id from the
  name (`friendly_name`, or the key). The import saves that object id in
  `entry.data["object_id"]`, and the platform sets `entity.entity_id` from it. HA uses it only
  when it first registers the entity. After that, the registry decides.
- **UI and YAML share one ID namespace.** A UI entry whose `unique_id` equals a YAML key makes
  the import abort with `yaml_conflict`, and the `yaml_conflict_<key>` issue is raised. An
  existing entry with `source == import` means the EC was already imported, so a restart does
  nothing.
- **Tests:** `setup_ec` configures YAML, so the whole suite runs through the import.
  `tests/test_import.py` covers the import itself, and `tests/test_config_flow.py` covers the
  forms. An EC set up while HA is running skips the startup delay. `setup_at_boot` simulates a
  boot, so the tests still go through the delay.

## Known issues

Bugs that are known and harmless, deliberately left alone for now.

- **Redundant `turn_off` when a light is switched off by hand.** Entering `idle` runs the
  `on_enter_idle` behaviour (`off` by default) even when the controlled entities are already off.
  With template lights or scripts in `single` mode, HA logs `<name> turn_off: Already running`.
  Found on a real instance testing 10.1.0b1.
- **A one-second `idle` at startup when outside the `start_time`/`end_time` window.** EC goes
  `pending → idle → constrained`, because the constrain is scheduled one second after startup.
  An automation triggering on `to: idle` fires once, and entering `idle` sends `turn_off` to the
  controlled entities. Found on a real instance testing 10.1.0b1.
