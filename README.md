[![CI](https://img.shields.io/github/actions/workflow/status/Pabsilon/entity-controller/ci.yml?branch=master&style=flat-square&label=CI)](https://github.com/Pabsilon/entity-controller/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Pabsilon/entity-controller?style=flat-square)](https://github.com/Pabsilon/entity-controller/releases)
[![HACS](https://img.shields.io/badge/HACS-custom-orange?style=flat-square)](https://hacs.xyz/docs/faq/custom_repositories/)
[![License](https://img.shields.io/github/license/Pabsilon/entity-controller.svg?style=flat-square)](https://github.com/Pabsilon/entity-controller/blob/master/COPYING)

> This is a maintained fork of [danobot/entity-controller](https://github.com/danobot/entity-controller), updated for current Home Assistant releases (2026.10 and newer).

# :wave: Introduction
Entity Controller (EC) is an implementation of "When This, Then That for x amount of time" using a finite state machine that ensures basic automations do not interfere with the rest of your home automation setup. This component encapsulates common automation scenarios into a neat package that can be configured easily and reused throughout your home. Traditional automations would need to be duplicated _for each instance_ in your config. The use cases for this component are endless because you can use any entity as input and outputs (there is no restriction to motion sensors and lights).

[Entity Controller Documentation](https://danobot.github.io/ec-docs/)

## Installation
Install through HACS as a custom repository:

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/Pabsilon/entity-controller` with the type **Integration**.
3. Install **Entity Controller** and restart Home Assistant.

Then add the following to your `configuration.yaml`, replacing the values for `sensor` and `entity` with your own. Restart Home Assistant again and you should have a motion controlled light that turns off after 5 seconds.
```yaml
entity_controller:
  motion_light:
    sensor: binary_sensor.living_room_motion
    entity: light.tv_led
    delay: 5
```

Entity Controller waits 70 seconds after Home Assistant starts before it begins reacting to sensors.

## :clapper: Video Demo
The original author made the following video to give a high-level overview of all EC features, how they work and how you can configure them for your use cases.

[![Video](images/video_thumbnail.png)](https://youtu.be/HJQrA6sFlPs)

## Credits
Entity Controller was created by [Daniel Mason (danobot)](https://github.com/danobot). If you'd like to support the original author:

[![donate paypal](https://img.shields.io/badge/donate-PayPal-blue.svg?style=flat-square)](https://paypal.me/danielb160)
[![donate gofundme](https://img.shields.io/badge/donate-GoFundMe-orange?style=flat-square)](https://gofund.me/7a2487d5)

# Contributions
All contributions are welcome, including raising [issues](https://github.com/Pabsilon/entity-controller/issues). See [dev.md](dev.md) for the development setup.
