[![CI](https://img.shields.io/github/actions/workflow/status/Pabsilon/entity-controller/ci.yml?branch=master&style=flat-square&label=CI)](https://github.com/Pabsilon/entity-controller/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Pabsilon/entity-controller?style=flat-square)](https://github.com/Pabsilon/entity-controller/releases)
[![HACS](https://img.shields.io/badge/HACS-custom-orange?style=flat-square)](https://hacs.xyz/docs/faq/custom_repositories/)
[![License](https://img.shields.io/github/license/Pabsilon/entity-controller.svg?style=flat-square)](https://github.com/Pabsilon/entity-controller/blob/master/COPYING)

> This is a maintained fork of [danobot/entity-controller](https://github.com/danobot/entity-controller), updated for current Home Assistant releases (2026.10 and newer).

# 🤖 AI Notice: The maintenance done on this fork is assisted with Claude (Opus 5.5 mainly). I work as a Python developer and I'm using this as a way to practice and test new things.

# :wave: Introduction
Entity Controller (EC) is an implementation of "When This, Then That for x amount of time" using a finite state machine that ensures basic automations do not interfere with the rest of your home automation setup. This component encapsulates common automation scenarios into a neat package that can be configured easily and reused throughout your home. Traditional automations would need to be duplicated _for each instance_ in your config. The use cases for this component are endless because you can use any entity as input and outputs (there is no restriction to motion sensors and lights).

[Entity Controller Documentation](https://danobot.github.io/ec-docs/)

## Installation

This fork should be a direct drop-in replacement of the original.

Install through HACS as a custom repository:

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/Pabsilon/entity-controller` with the type **Integration**.
3. Install **Entity Controller** and restart Home Assistant.

## Setup
Each Entity Controller is set up in the UI:

1. Go to **Settings** > **Devices & services** > **Helpers** > **Create helper** and choose **Entity Controller**.
2. Give it a name, pick the sensors (such as a motion sensor) and the controlled entities (such as a light), and set the delay.
3. Submit. The controller starts right away! No restart needed!

Every option is in the form, grouped in sections. Empty fields use their defaults. To change an Entity Controller later, select it in the **Helpers** tab, or under **Settings** > **Devices & services** > **Entity Controller**, and choose **Configure**. Changes apply without a restart. Create one Entity Controller for each use case.

The [Entity Controller documentation](https://danobot.github.io/ec-docs/) describes every option with YAML examples. The option names in the documentation still match the ones the form saves, so it still applies.

Entity Controller waits 70 seconds after Home Assistant starts before it begins reacting to sensors. A controller created or reconfigured while Home Assistant is running starts immediately.

## Migrating from YAML
YAML configuration is deprecated. If you have an `entity_controller:` section in `configuration.yaml`, Entity Controller imports it on the first start after the upgrade:

- Each controller under `entity_controller:` becomes an entry in the UI, named after its `friendly_name`, or after its key if it has none.
- **Entity IDs stay the same**, so your automations, scripts and dashboards keep working.
- The options are imported as they are. Legacy spellings are saved under their current names (`sensor` as `sensors`, `entity` as `entities`, `override` as `overrides`, and `sensor_type_duration: true` as `sensor_type: duration`). Unknown options and options set to their default are left out: they had no effect.
- A Repairs issue asks you to remove the `entity_controller:` section. Remove it and restart once you've checked the imported controllers.

The import happens once per controller. After that, the UI is the source of truth:

- **Later changes to the YAML are ignored.** Use **Configure** instead.
- **A controller you delete comes back** on the next restart while its YAML is still there. Remove the YAML first, or along with it.
- **A name already used in the UI blocks the import.** If you created a controller in the UI whose name gives the same ID as a YAML key (for example "Motion Light" and `motion_light:`), the YAML one isn't imported and doesn't run. A Repairs issue names both. Rename the YAML key and restart to import it, or remove it from YAML if the UI controller replaces it.

## :clapper: Video Demo
The original author made the following video to give a high-level overview of all EC features, how they work and how you can configure them for your use cases.

[![Video](images/video_thumbnail.png)](https://youtu.be/HJQrA6sFlPs)

## Credits
Entity Controller was created by [Daniel Mason (danobot)](https://github.com/danobot). If you'd like to support the original author:

[![donate paypal](https://img.shields.io/badge/donate-PayPal-blue.svg?style=flat-square)](https://paypal.me/danielb160)
[![donate gofundme](https://img.shields.io/badge/donate-GoFundMe-orange?style=flat-square)](https://gofund.me/7a2487d5)

# Contributions
All contributions are welcome, including raising [issues](https://github.com/Pabsilon/entity-controller/issues). See [dev.md](dev.md) for the development setup.
